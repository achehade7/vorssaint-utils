// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import Combine

/// One in-memory draft owns every operation. Only Save publishes to the vault.
/// Collection mode and presentation never finalize or replace the draft.
final class NotchQuickCaptureService: ObservableObject {
    static let shared = NotchQuickCaptureService()
    typealias Store = NotchQuickCaptureStore
    struct Attachment: Identifiable {
        let id: UUID
        let image: CGImage
        let file: URL?
        let capturedAt: Date
    }
    struct MeetingChoice: Identifiable {
        let id: String
        let title: String
        let input: MeetingNoteInput
    }
    typealias MeetingLoader = (Date, @escaping (Result<[MeetingChoice], Error>) -> Void) -> Void
    typealias NoteResolver = (MeetingChoice, @escaping (Result<URL?, Error>) -> Void) -> Void
    typealias Recognizer = (CGImage, @escaping (Result<String, Error>) -> Void) -> Void

    @Published var text = ""
    @Published var label = ""
    @Published private(set) var images: [Attachment] = []
    @Published private(set) var extracts: [Store.TextExtract] = []
    @Published private(set) var meeting: Store.Meeting?
    @Published private(set) var meetingChoices: [MeetingChoice] = []
    @Published private(set) var needsMeetingChoice = false
    @Published private(set) var pendingCount = 0
    @Published private(set) var saving = false
    @Published private(set) var publishing = false
    @Published private(set) var capturingGroup = false
    @Published private(set) var error: CaptureError?
    enum CaptureError { case save, screenshot, ocr, meeting, uncertain }

    private let store: Store
    private let now: () -> Date
    private let io: DispatchQueue
    private let loadMeetings: MeetingLoader
    private let resolveNote: NoteResolver
    private let recognize: Recognizer
    private var draftID: UUID?
    private var startedAt: Date?
    private var operations = Set<UUID>()
    private var meetingToken: UUID?
    private var transcriptStarts: [String: Date] = [:]
    private var selectedMeeting: MeetingChoice?
    private var meetingFailed = false
    private var fileSession: Store.Session?
    private var fileBusy = false
    private var failedImages = Set<UUID>()
    private struct OCRWork {
        let image: CGImage
        let capturedAt: Date
        var token: UUID?
        var failed = false
    }
    private var ocrWork: [UUID: OCRWork] = [:]
    private var ocrOrder: [UUID] = []
    private var undoIDs: [UUID] = []
    private var undoPending: UUID?
    private enum FileMutation { case remove(UUID), reorder(UUID, UUID) }
    private var failedMutation: FileMutation?
    private var snapshot: Store.Snapshot?
    private var attempt: Store.AppendAttempt?
    private var selection: ScreenshotSelectionController?
    private var selectionToken: UUID?
    private let textActionsOwner = UUID()
    private var dragIsText = false
    private var editorHidden = false
    private var groupGeneration = UUID()
    private let keys = NotchQuickCaptureKeyTracker()
    private var cleanup: DispatchSourceTimer?

    init(store: Store = .personal, now: @escaping () -> Date = Date.init,
         io: DispatchQueue? = nil, loadMeetings: MeetingLoader? = nil,
         resolveNote: NoteResolver? = nil, recognize: Recognizer? = nil) {
        self.store = store
        self.now = now
        let queue = io ?? DispatchQueue(label: "com.vorssaint.quick-capture.files", qos: .utility)
        self.io = queue
        self.loadMeetings = loadMeetings ?? NotchQuickCaptureMeetings.load
        self.resolveNote = resolveNote ?? { choice, completion in
            queue.async {
                let result = Result { try NotchQuickCaptureMeetings.existingNote(for: choice, vault: store.vault) }
                DispatchQueue.main.async { completion(result) }
            }
        }
        self.recognize = recognize ?? ScreenTextService.recognizeCaptureText
    }

    var imageCount: Int { images.count }
    var isSelecting: Bool { selection != nil }
    var canEdit: Bool { !saving && attempt == nil }
    var canDiscard: Bool { !publishing }
    var hasFailedAttachments: Bool { !failedImages.isEmpty || ocrWork.values.contains(where: \.failed) }
    var hasFailedWork: Bool { meetingFailed || hasFailedAttachments || failedMutation != nil }
    private var hasContent: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !images.isEmpty
            || extracts.contains { !Store.multiline($0.text).isEmpty }
            || !ocrWork.isEmpty || selection?.isAcquiring == true
    }
    var canSave: Bool { !saving && hasContent && !hasFailedWork && !needsMeetingChoice }
    var canUndoScreenshot: Bool {
        canEdit && !fileBusy && undoIDs.last.map { id in images.contains { $0.id == id } } == true
    }

    func start() {
        guard cleanup == nil else { return }
        let store = store
        let timer = DispatchSource.makeTimerSource(queue: io)
        timer.schedule(deadline: .now(), repeating: 24 * 60 * 60, leeway: .seconds(60))
        timer.setEventHandler { try? store.removeExpiredScreenshots() }
        cleanup = timer
        timer.resume()
    }

    func stop() {
        cancelTextActions()
        cleanup?.cancel(); cleanup = nil
        cancelSelection()
        keys.stop()
    }

    /// Called only when opening/resuming, never for an asynchronous result.
    func open() {
        editorHidden = false
        ensureDraft()
        keys.start(ownsWindow: { [weak self] window in
            guard let self, let window else { return false }
            if window.windowNumber > 0,
               self.selection?.protectedWindowIDs.contains(CGWindowID(window.windowNumber)) == true { return true }
            return NotchService.shared.showingQuickCapture && window === NotchService.shared.presentationWindow
        }, handleEvent: { [weak self] event in
            guard let self else { return false }
            let selecting = event.windowNumber > 0
                && self.selection?.protectedWindowIDs.contains(CGWindowID(event.windowNumber)) == true
            return self.handleKey(event, selecting: selecting)
        })
    }

    private func ensureDraft() {
        guard draftID == nil else { return }
        draftID = UUID(); startedAt = now()
        readMeetings()
    }

    private func beginOperation() -> UUID {
        let token = UUID()
        operations.insert(token); pendingCount = operations.count
        return token
    }

    @discardableResult private func finishOperation(_ token: UUID, draft: UUID) -> Bool {
        guard draftID == draft, operations.remove(token) != nil else { return false }
        pendingCount = operations.count
        return true
    }

    private func invalidateMeetingWork() {
        if let meetingToken { operations.remove(meetingToken) }
        meetingToken = nil; pendingCount = operations.count
    }

    private func readMeetings() {
        guard let draft = draftID, let startedAt else { return }
        invalidateMeetingWork()
        meetingFailed = false
        let token = beginOperation(); meetingToken = token
        loadMeetings(startedAt) { [weak self] result in
            guard let self, self.finishOperation(token, draft: draft), self.meetingToken == token else { return }
            self.meetingToken = nil
            switch result {
            case .success(let choices):
                self.meetingChoices = choices
                self.needsMeetingChoice = choices.count > 1
                if choices.count == 1 { self.selectMeeting(choices[0]) }
            case .failure:
                self.meetingFailed = true; self.error = .meeting
            }
            self.advanceSave()
        }
    }

    func chooseMeeting(_ id: String?) {
        guard !publishing, attempt == nil else { return }
        invalidateMeetingWork()
        needsMeetingChoice = false; meetingFailed = false
        selectedMeeting = nil; meeting = nil
        if let id, let choice = meetingChoices.first(where: { $0.id == id }) { selectMeeting(choice) }
        if error == .meeting { error = nil }
        advanceSave()
    }

    private func selectMeeting(_ choice: MeetingChoice) {
        guard let draft = draftID else { return }
        selectedMeeting = choice
        let title = MeetingNoteStore.suggestedTopic(choice.input)
        meeting = .init(title: title, start: choice.input.start, note: nil, transcriptStart: transcriptStarts[transcriptKey(choice)])
        let token = beginOperation(); meetingToken = token
        resolveNote(choice) { [weak self] result in
            guard let self, self.finishOperation(token, draft: draft), self.meetingToken == token else { return }
            self.meetingToken = nil
            switch result {
            case .success(let file): self.meeting = .init(title: title, start: choice.input.start, note: file, transcriptStart: self.meeting?.transcriptStart)
            case .failure: self.meetingFailed = true; self.error = .meeting
            }
            self.advanceSave()
        }
    }

    private func transcriptKey(_ choice: MeetingChoice) -> String {
        choice.id + "|" + String(choice.input.start.timeIntervalSince1970)
    }

    func setTranscriptStart(_ date: Date?) {
        guard canEdit, let choice = selectedMeeting, meeting != nil else { return }
        transcriptStarts[transcriptKey(choice)] = date
        meeting?.transcriptStart = date
    }

    func recordingStartedNow() { setTranscriptStart(now()) }

    func hide() {
        cancelTextActions()
        editorHidden = true
        pauseSelection()
        keys.stop()
        NotchService.shared.collapse()
    }

    /// Old file work may finish in its old folder. Its invalidated token cannot
    /// modify a new draft or request publication.
    func discard() {
        guard canDiscard else { return }
        resetDraft()
        NotchService.shared.collapse()
    }

    private func resetDraft() {
        cancelTextActions()
        draftID = nil
        cancelSelection(); keys.stop()
        operations.removeAll(); pendingCount = 0; meetingToken = nil
        text = ""; label = ""; images = []; extracts = []; meeting = nil; meetingChoices = []
        needsMeetingChoice = false; selectedMeeting = nil; meetingFailed = false
        fileSession = nil; fileBusy = false; failedImages = []; ocrWork = [:]; ocrOrder = []
        undoIDs = []; undoPending = nil; failedMutation = nil; snapshot = nil; attempt = nil
        saving = false; publishing = false; error = nil; startedAt = nil
    }

    func save() {
        guard canSave else { return }
        ensureDraft()
        pauseSelection()
        saving = true
        if error != .uncertain { error = nil }
        advanceSave()
    }

    func showTextActions(in window: NSWindow, editor: NSTextView) {
        guard !editorHidden, draftID != nil, canEdit, window.isVisible, window.attachedSheet == nil,
              editor.window === window, !editor.isFieldEditor, !editor.hasMarkedText() else { return }
        let source = editor.string as NSString
        let range = editor.selectedRange()
        let snapshot = range.length > 0 && range.location != NSNotFound && NSMaxRange(range) <= source.length
            ? source.substring(with: range) : editor.string
        guard !snapshot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        SharedToolActions.present(content: .text(snapshot), title: String(snapshot.prefix(80)),
                                  from: window, owner: textActionsOwner)
    }

    func cancelTextActions() { SharedToolActions.cancel(owner: textActionsOwner) }

    private func advanceSave() {
        guard saving, !publishing else { return }
        if hasFailedWork || needsMeetingChoice { saving = false; return }
        guard operations.isEmpty, let draft = draftID, let startedAt else { return }
        guard images.allSatisfy({ $0.file != nil }), ocrWork.isEmpty else {
            saving = false; error = .save; return
        }
        if snapshot == nil {
            snapshot = Store.Snapshot(id: draft, startedAt: startedAt, label: label, text: text,
                meeting: meeting,
                images: images.map { .init(id: $0.id, capturedAt: $0.capturedAt, file: $0.file!) },
                extracts: extracts.filter { !Store.multiline($0.text).isEmpty })
        }
        guard let snapshot else { return }
        let store = store, retry = attempt
        // Discard is disabled before the append is queued.
        publishing = true
        io.async { [weak self] in
            let result = store.publish(snapshot, retry: retry)
            if case .committed = result { try? store.removeExpiredScreenshots() }
            DispatchQueue.main.async {
                guard let self, self.draftID == draft else { return }
                self.publishing = false; self.saving = false
                switch result {
                case .committed:
                    self.resetDraft()
                    if NotchService.shared.showingQuickCapture { NotchService.shared.collapse() }
                    NotchService.shared.signalQuickCapture(success: true)
                case .notCommitted:
                    self.snapshot = nil; self.attempt = nil; self.error = .save
                    NotchService.shared.signalQuickCapture(success: false)
                case .uncertain(let attempt):
                    self.attempt = attempt; self.error = .uncertain
                    NotchService.shared.signalQuickCapture(success: false)
                }
            }
        }
    }

    func retryFailedWork() {
        guard canEdit else { if attempt != nil { save() }; return }
        if meetingFailed {
            meetingFailed = false
            if let selectedMeeting { selectMeeting(selectedMeeting) } else { readMeetings() }
        }
        let failedOCR = ocrWork.filter { $0.value.failed }.map(\.key)
        failedImages.removeAll()
        error = nil
        for id in failedOCR { recognizeExtract(id) }
        persistNextImage()
        retryFileMutation()
    }

    private func retryFileMutation() {
        guard !fileBusy, images.allSatisfy({ $0.file != nil }), let mutation = failedMutation else { return }
        failedMutation = nil
        switch mutation {
        case .remove(let id): removeImage(id)
        case .reorder(let id, let target): _ = moveImage(id, to: target)
        }
    }

    func removeFailedAttachments() {
        guard canEdit else { return }
        for id in failedImages { images.removeAll { $0.id == id }; undoIDs.removeAll { $0 == id } }
        failedImages.removeAll()
        for id in ocrWork.filter({ $0.value.failed }).map(\.key) { removeExtract(id) }
        error = meetingFailed ? .meeting : nil
    }

    // MARK: - Accepted content and serial file mutations

    func receiveImage(_ image: CGImage, capturedAt: Date) {
        receiveImage(image, capturedAt: capturedAt, accepted: false)
    }

    private func receiveImage(_ image: CGImage, capturedAt: Date, accepted: Bool) {
        guard canEdit || (accepted && saving && !publishing && attempt == nil) else { return }
        ensureDraft()
        let id = UUID()
        images.append(.init(id: id, image: image, file: nil, capturedAt: capturedAt))
        undoIDs.append(id)
        persistNextImage()
    }

    private func persistNextImage() {
        guard !fileBusy, let draft = draftID,
              let attachment = images.first(where: { $0.file == nil && !failedImages.contains($0.id) }) else { return }
        if fileSession == nil {
            fileSession = .init(startedAt: startedAt ?? now(), label: label.isEmpty ? meeting?.title ?? "" : label)
        }
        guard let session = fileSession else { return }
        let store = store, token = beginOperation()
        fileBusy = true
        io.async { [weak self] in
            let result = Result { try store.saveSessionScreenshot(Self.png(attachment.image), session: session, at: attachment.capturedAt) }
            DispatchQueue.main.async {
                guard let self, self.finishOperation(token, draft: draft) else { return }
                self.fileBusy = false
                switch result {
                case .success(let updated):
                    self.fileSession = updated
                    if let index = self.images.firstIndex(where: { $0.id == attachment.id }), let folder = updated.folder {
                        self.images[index] = .init(id: attachment.id, image: Self.thumbnail(attachment.image),
                            file: folder.appendingPathComponent(String(format: "%02d.png", updated.count)), capturedAt: attachment.capturedAt)
                    }
                case .failure:
                    self.failedImages.insert(attachment.id); self.error = .save
                    self.pauseGroupCapture()
                }
                if let id = self.undoPending {
                    self.undoPending = nil
                    self.removeImage(id, accepted: true)
                }
                self.persistNextImage(); self.retryFileMutation()
                self.continueGroupCapture(); self.advanceSave()
            }
        }
    }

    func receiveTextImage(_ image: CGImage, capturedAt: Date) {
        receiveTextImage(image, capturedAt: capturedAt, accepted: false)
    }

    private func receiveTextImage(_ image: CGImage, capturedAt: Date, accepted: Bool) {
        guard canEdit || (accepted && saving && !publishing && attempt == nil) else { return }
        ensureDraft()
        let id = UUID()
        ocrOrder.append(id)
        ocrWork[id] = .init(image: image, capturedAt: capturedAt)
        recognizeExtract(id)
    }

    private func recognizeExtract(_ id: UUID) {
        guard let draft = draftID, var work = ocrWork[id], work.token == nil else { return }
        let token = beginOperation()
        work.token = token; work.failed = false; ocrWork[id] = work
        recognize(work.image) { [weak self] result in
            guard let self, self.finishOperation(token, draft: draft), self.ocrWork[id]?.token == token else { return }
            switch result {
            case .success(let text) where !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty:
                self.ocrWork.removeValue(forKey: id)
                self.extracts.append(.init(id: id, capturedAt: work.capturedAt, text: text))
                self.extracts.sort { (self.ocrOrder.firstIndex(of: $0.id) ?? 0) < (self.ocrOrder.firstIndex(of: $1.id) ?? 0) }
            default:
                self.ocrWork[id]?.token = nil; self.ocrWork[id]?.failed = true
                self.error = .ocr; self.pauseGroupCapture()
            }
            self.continueGroupCapture(); self.advanceSave()
        }
    }

    func updateExtract(_ id: UUID, text: String) {
        guard canEdit, let index = extracts.firstIndex(where: { $0.id == id }) else { return }
        let extract = extracts[index]
        extracts[index] = .init(id: extract.id, capturedAt: extract.capturedAt, text: text)
    }

    func removeExtract(_ id: UUID) {
        guard canEdit else { return }
        if let token = ocrWork[id]?.token { operations.remove(token); pendingCount = operations.count }
        ocrWork.removeValue(forKey: id); ocrOrder.removeAll { $0 == id }; extracts.removeAll { $0.id == id }
        if !hasFailedWork && error == .ocr { error = nil }
    }

    func undoLastScreenshot() {
        if fileBusy && !saving && attempt == nil { undoPending = undoIDs.last; return }
        guard canUndoScreenshot, let id = undoIDs.last else { return }
        removeImage(id)
    }

    func removeImage(_ id: UUID) {
        removeImage(id, accepted: false)
    }

    private func removeImage(_ id: UUID, accepted: Bool) {
        guard (canEdit || (accepted && saving && !publishing)), !fileBusy,
              let attachment = images.first(where: { $0.id == id }) else { return }
        failedMutation = nil
        guard let file = attachment.file else {
            images.removeAll { $0.id == id }; undoIDs.removeAll { $0 == id }; failedImages.remove(id)
            if !hasFailedWork { error = nil }
            return
        }
        guard let session = fileSession, let draft = draftID,
              let number = Int(file.deletingPathExtension().lastPathComponent) else { return }
        detachSelection()
        let token = beginOperation(), store = store
        fileBusy = true
        io.async { [weak self] in
            let result = Result { try store.removeSessionScreenshot(session, number: number) }
            DispatchQueue.main.async {
                guard let self, self.finishOperation(token, draft: draft) else { return }
                self.fileBusy = false
                switch result {
                case .success(let updated):
                    self.fileSession = updated
                    self.images.removeAll { $0.id == id }; self.undoIDs.removeAll { $0 == id }
                    self.renumberImages()
                case .failure:
                    self.failedMutation = .remove(id); self.error = .save; self.pauseGroupCapture()
                }
                self.continueGroupCapture(); self.advanceSave()
            }
        }
    }

    func moveImage(_ id: UUID, to target: UUID) -> Bool {
        guard canEdit, !fileBusy, !isSelecting, !capturingGroup, id != target,
              let draft = draftID, let session = fileSession,
              images.allSatisfy({ $0.file != nil }),
              let from = images.firstIndex(where: { $0.id == id }),
              let to = images.firstIndex(where: { $0.id == target }) else { return false }
        var reordered = images
        reordered.insert(reordered.remove(at: from), at: to)
        let order = reordered.compactMap { Int($0.file!.deletingPathExtension().lastPathComponent) }
        let resultImages = reordered, token = beginOperation(), store = store
        failedMutation = nil
        fileBusy = true
        io.async { [weak self] in
            let result = Result { try store.reorderSession(session, order: order) }
            DispatchQueue.main.async {
                guard let self, self.finishOperation(token, draft: draft) else { return }
                self.fileBusy = false
                switch result {
                case .success: self.images = resultImages; self.renumberImages()
                case .failure: self.failedMutation = .reorder(id, target); self.error = .save
                }
                self.advanceSave()
            }
        }
        return true
    }

    private func renumberImages() {
        guard let folder = fileSession?.folder else { return }
        var number = 0
        images = images.map { item in
            guard item.file != nil else { return item }
            number += 1
            return .init(id: item.id, image: item.image,
                         file: folder.appendingPathComponent(String(format: "%02d.png", number)), capturedAt: item.capturedAt)
        }
    }

    // MARK: - Selection and keys

    func captureGroup() {
        guard canEdit else { return }
        if capturingGroup { pauseGroupCapture(); return }
        guard !isSelecting, !fileBusy, !hasFailedWork, !ScreenshotSelectionController.isSessionOnScreen else { return }
        open()
        capturingGroup = true; groupGeneration = UUID()
        beginSelection(textOnly: false, repeated: true)
    }

    func captureRegion() {
        guard canEdit, !fileBusy, !isSelecting, !hasFailedWork, !ScreenshotSelectionController.isSessionOnScreen else { return }
        capturingGroup = false; groupGeneration = UUID()
        open(); beginSelection(textOnly: false, repeated: false)
    }

    func captureText() {
        guard AppFeature.screenOCR.isAvailable, canEdit, !fileBusy, !isSelecting, !hasFailedWork,
              !ScreenshotSelectionController.isSessionOnScreen else { return }
        capturingGroup = false; groupGeneration = UUID()
        open(); beginSelection(textOnly: true, repeated: false)
    }

    private func continueGroupCapture() {
        guard capturingGroup, !saving, !fileBusy, !isSelecting, ocrWork.isEmpty, !hasFailedWork else { return }
        let generation = groupGeneration, draft = draftID
        DispatchQueue.main.async { [weak self] in
            guard let self, self.draftID == draft, self.groupGeneration == generation, self.capturingGroup,
                  !self.saving, !self.fileBusy, !self.isSelecting else { return }
            self.beginSelection(textOnly: false, repeated: true)
        }
    }

    func pauseGroupCapture() {
        let wasCapturing = capturingGroup || isSelecting
        pauseSelection()
        if wasCapturing && !editorHidden && !saving { NotchService.shared.openQuickCapture() }
    }

    /// Mouse-up accepted the region before its pixels arrive. Save and Hide
    /// preserve that operation; only Discard/teardown invalidate it.
    private func pauseSelection() {
        capturingGroup = false; groupGeneration = UUID()
        if selection?.isAcquiring != true { detachSelection() }
    }

    private func detachSelection() {
        let controller = selection
        selection = nil
        if let selectionToken { operations.remove(selectionToken); pendingCount = operations.count }
        selectionToken = nil
        controller?.cancel()
    }

    func cancelSelection() {
        if draftID != nil, selection?.isAcquiring == true { saving = false; error = .screenshot }
        capturingGroup = false; groupGeneration = UUID()
        detachSelection()
    }

    private func beginSelection(textOnly: Bool, repeated: Bool) {
        guard let draft = draftID else { return }
        guard !ScreenshotSelectionController.isSessionOnScreen else {
            capturingGroup = false; groupGeneration = UUID()
            return
        }
        guard Permissions.shared.screenRecording else {
            Permissions.shared.requestScreenRecording(); error = .screenshot; pauseGroupCapture(); return
        }
        let token = beginOperation(); selectionToken = token
        dragIsText = textOnly
        let strings = NotchQuickCaptureStrings.localized(L10n.shared.language)
        let purpose = repeated
            ? String(format: strings.count, imageCount, extracts.count) + " · ⌘ " + strings.captureText + " · ⌘Z · Esc"
            : strings.title
        let controller = ScreenshotSelectionController(
            freeze: !repeated, includePointer: false, showLastRegion: false, hideVorssaintWindows: true,
            protectedWindowIDs: { NotchService.shared.captureChromeWindowIDs },
            purpose: purpose, requiresDraggedRegion: true,
            freezeOnCommand: repeated && AppFeature.screenOCR.isAvailable,
            onSelectionBegan: { [weak self] modifiers in
                guard let self else { return }
                self.dragIsText = textOnly || (repeated && modifiers.contains(.command) && AppFeature.screenOCR.isAvailable)
            })
        selection = controller
        NotchService.shared.collapse()
        controller.begin { [weak self, weak controller] outcome in
            guard let self, let controller, self.selection === controller,
                  self.finishOperation(token, draft: draft) else { return }
            self.selection = nil; self.selectionToken = nil
            switch outcome {
            case .captured(let capture):
                if self.dragIsText { self.receiveTextImage(capture.image, capturedAt: capture.capturedAt, accepted: true) }
                else { self.receiveImage(capture.image, capturedAt: capture.capturedAt, accepted: true) }
            case .cancelled: self.capturingGroup = false; self.groupGeneration = UUID()
            default: self.capturingGroup = false; self.error = .screenshot; self.saving = false
            }
            if !self.capturingGroup && !self.editorHidden && !self.saving { NotchService.shared.openQuickCapture() }
            self.advanceSave()
        }
    }

    static func isUndoScreenshot(_ event: NSEvent) -> Bool {
        let modifiers = event.modifierFlags.intersection([.command, .control, .option, .shift])
        return event.type == .keyDown && event.keyCode == 6 && !event.isARepeat
            && (modifiers == .command || modifiers == [.command, .control])
    }

    func handleKey(_ event: NSEvent, selecting: Bool) -> Bool {
        guard event.type == .keyDown, !event.isARepeat, event.window?.attachedSheet == nil else { return false }
        let modifiers = event.modifierFlags.intersection([.command, .control, .option, .shift])
        if Self.isUndoScreenshot(event), selecting || modifiers.contains(.control) { undoLastScreenshot(); return true }
        if selecting {
            if modifiers.isEmpty && [53, 5, 1].contains(event.keyCode) { pauseGroupCapture(); return true }
            if modifiers == .command && event.keyCode == 5 { pauseGroupCapture(); return true }
            return false
        }
        if event.keyCode == 53 { hide(); return true }
        let typing = event.window?.firstResponder is NSText
        guard modifiers == .command || (modifiers.isEmpty && !typing) else { return false }
        switch event.keyCode {
        case 5: captureGroup()
        case 15: captureRegion()
        case 17: captureText()
        case 1 where modifiers == .command: save()
        case 2 where modifiers == .command, 13 where modifiers == .command: discard()
        default: return false
        }
        return true
    }

    private static func png(_ image: CGImage) throws -> Data {
        guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else { throw Store.Failure.write }
        return data
    }

    private static func thumbnail(_ image: CGImage) -> CGImage {
        let scale = min(1, 176.0 / Double(max(image.width, image.height)))
        let width = max(1, Int(Double(image.width) * scale)), height = max(1, Int(Double(image.height) * scale))
        guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return image }
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage() ?? image
    }
}
