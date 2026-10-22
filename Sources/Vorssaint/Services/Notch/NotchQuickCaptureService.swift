// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import Combine

/// Drafts survive presentation changes. Session images save as they are taken;
/// the vault receives one summary only when the session finishes.
final class NotchQuickCaptureService: ObservableObject {
    static let shared = NotchQuickCaptureService()
    static let sessionIdleTimeout: TimeInterval = 30 * 60
    struct Attachment: Identifiable {
        let id: UUID
        let image: CGImage
        let file: URL?
        init(id: UUID = UUID(), image: CGImage, file: URL? = nil) { self.id = id; self.image = image; self.file = file }
    }
    @Published var text = ""
    @Published var sessionLabel = ""
    @Published private(set) var images: [Attachment] = []
    @Published private(set) var session: NotchQuickCaptureStore.Session?
    @Published private(set) var pendingSessionImage: CGImage?
    @Published private(set) var saving = false
    @Published private(set) var error: CaptureError?
    enum CaptureError { case save, screenshot }

    private let store: NotchQuickCaptureStore
    private let now: () -> Date
    init(store: NotchQuickCaptureStore = .personal, now: @escaping () -> Date = Date.init) {
        self.store = store
        self.now = now
    }
    private let io = DispatchQueue(label: "com.vorssaint.quick-capture.files", qos: .utility)
    private var cleanup: DispatchSourceTimer?
    private var sessionTimer: Timer?
    private var pendingCaptureAt: Date?
    private var selection: ScreenshotSelectionController?
    var isSelecting: Bool { selection != nil }
    private(set) var capturingGroup = false
    private var groupGeneration = UUID()
    private var captureUndoIDs: [UUID] = []
    private var undoPending = false
    var canUndoScreenshot: Bool {
        session != nil && !saving && pendingSessionImage == nil
            && captureUndoIDs.last.map { id in images.contains { $0.id == id } } == true
    }
    private var groupEscapeMonitor: Any?
    private var groupGlobalEscapeMonitor: Any?

    /// Escape pauses selection, not the group. The same action resumes its numbering.
    func captureGroup() {
        closeSessionIfIdle()
        guard !saving, !isSelecting, !ScreenshotSelectionController.isSessionOnScreen else { return }
        if session == nil { startSession() }
        guard session != nil else { return }
        endGroupCapture()
        capturingGroup = true
        groupGeneration = UUID()
        groupEscapeMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard self?.capturingGroup == true else { return event }
            if event.keyCode == 53 { self?.pauseGroupCapture(); return nil }
            if Self.isUndoScreenshot(event) { self?.undoLastScreenshot(); return nil }
            return event
        }
        groupGlobalEscapeMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 { self?.pauseGroupCapture() }
        }
        captureRegion()
    }

    static func isUndoScreenshot(_ event: NSEvent) -> Bool {
        event.keyCode == 6 && !event.isARepeat
            && event.modifierFlags.intersection([.command, .control, .option, .shift]) == .command
    }

    func undoLastScreenshot() {
        if saving, capturingGroup { undoPending = true; return }
        guard canUndoScreenshot, let session, let id = captureUndoIDs.last,
              let attachment = images.first(where: { $0.id == id }), let file = attachment.file,
              let number = Int(file.deletingPathExtension().lastPathComponent) else { return }
        // Detach the old callback before cancelling; the editor stays hidden
        // and a fresh selector follows the atomic file operation.
        let controller = selection; selection = nil
        controller?.cancel()
        let store = store
        sessionTimer?.invalidate(); sessionTimer = nil
        saving = true; error = nil
        io.async { [weak self] in
            let result = Result { try store.removeSessionScreenshot(session, number: number) }
            DispatchQueue.main.async {
                guard let self else { return }
                self.saving = false
                switch result {
                case .success(let updated):
                    self.session = updated
                    self.captureUndoIDs.removeAll { $0 == id }
                    self.images = self.images.filter { $0.id != id }.map { item in
                        guard let old = item.file, old.deletingLastPathComponent() == session.folder,
                              let index = Int(old.deletingPathExtension().lastPathComponent), index > number else { return item }
                        return Attachment(id: item.id, image: item.image,
                                          file: old.deletingLastPathComponent().appendingPathComponent(String(format: "%02d.png", index - 1)))
                    }
                    if self.capturingGroup { self.continueGroupCapture() }
                case .failure:
                    self.endGroupCapture()
                    self.error = .save
                    NotchService.shared.openQuickCapture()
                    NotchService.shared.signalQuickCapture(success: false)
                }
                self.undoPending = false
                self.scheduleSessionClose()
            }
        }
    }

    func pauseGroupCapture() {
        guard capturingGroup else { return }
        endGroupCapture()
        if let selection { selection.cancel() }
        else { NotchService.shared.openQuickCapture(); scheduleSessionClose() }
    }

    private func endGroupCapture() {
        capturingGroup = false
        groupGeneration = UUID()
        if let groupEscapeMonitor { NSEvent.removeMonitor(groupEscapeMonitor) }
        if let groupGlobalEscapeMonitor { NSEvent.removeMonitor(groupGlobalEscapeMonitor) }
        groupEscapeMonitor = nil; groupGlobalEscapeMonitor = nil
    }

    private func continueGroupCapture() {
        let generation = groupGeneration
        DispatchQueue.main.async { [weak self] in
            guard let self, self.capturingGroup, self.groupGeneration == generation else { return }
            self.captureRegion()
        }
    }
    var canSave: Bool {
        !saving && pendingSessionImage == nil && (hasUnsavedContent || !images.isEmpty)
            && (error != .save || hasUnsavedContent)
    }
    private var hasUnsavedContent: Bool {
        !NotchQuickCaptureStore.singleLine(text).isEmpty || images.contains { $0.file == nil }
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
        cleanup?.cancel(); cleanup = nil
        cancelSelection()
    }

    func cancelSelection() {
        endGroupCapture()
        let controller = selection
        selection = nil
        controller?.cancel()
        scheduleSessionClose()
    }

    func cancel() {
        guard !saving else { return }
        // A failed session image must remain available to Retry/Stop.
        guard pendingSessionImage == nil else { NotchService.shared.collapse(); return }
        text = ""; images = []; error = nil; captureUndoIDs = []
        NotchService.shared.collapse()
    }

    func removeImage(_ id: UUID) {
        guard !saving else { return }
        images.removeAll { $0.id == id && $0.file == nil }
    }

    func moveImage(_ id: UUID, to target: UUID) -> Bool {
        guard !saving, !isSelecting, !capturingGroup, id != target,
              let from = images.firstIndex(where: { $0.id == id }),
              let to = images.firstIndex(where: { $0.id == target }) else { return false }
        let sourceFolder = images[from].file?.deletingLastPathComponent()
        guard sourceFolder == images[to].file?.deletingLastPathComponent() else { return false }
        var reordered = images
        let moved = reordered.remove(at: from)
        reordered.insert(moved, at: to)
        guard let sourceFolder else { images = reordered; return true }
        guard let session, session.folder == sourceFolder else { return false }
        let group = reordered.filter { $0.file?.deletingLastPathComponent() == sourceFolder }
        let numbers = group.compactMap { Int($0.file!.deletingPathExtension().lastPathComponent) }
        guard numbers.count == group.count, numbers.allSatisfy({ (1...session.count).contains($0) }) else { return false }
        let slots = numbers.sorted()
        var order = Array(1...session.count)
        var newPaths: [UUID: URL] = [:]
        for (offset, slot) in slots.enumerated() {
            order[slot - 1] = numbers[offset]
            newPaths[group[offset].id] = sourceFolder.appendingPathComponent(String(format: "%02d.png", slot))
        }
        let updated = reordered.map { attachment in
            newPaths[attachment.id].map { Attachment(id: attachment.id, image: attachment.image, file: $0) } ?? attachment
        }
        let store = store
        saving = true; error = nil
        let fileOrder = order
        io.async { [weak self] in
            let result = Result { try store.reorderSession(session, order: fileOrder) }
            DispatchQueue.main.async {
                guard let self else { return }
                self.saving = false
                switch result {
                case .success: self.images = updated
                case .failure:
                    self.error = .save
                    NotchService.shared.signalQuickCapture(success: false)
                }
                self.scheduleSessionClose()
            }
        }
        return true
    }

    func startSession() {
        guard session == nil, !saving, !isSelecting else { return }
        captureUndoIDs = []; undoPending = false
        session = .init(startedAt: now(), label: sessionLabel)
        error = nil
        scheduleSessionClose()
    }

    func stopSession() {
        guard session != nil, !saving, !isSelecting else { return }
        endGroupCapture()
        writeSession(close: true)
    }

    func closeSessionIfIdle() {
        guard let session, now().timeIntervalSince(session.lastCaptureAt) >= Self.sessionIdleTimeout,
              !saving, !isSelecting, pendingSessionImage == nil else { return }
        stopSession()
    }

    private func scheduleSessionClose() {
        sessionTimer?.invalidate(); sessionTimer = nil
        guard let session else { return }
        let delay = max(0.01, Self.sessionIdleTimeout - now().timeIntervalSince(session.lastCaptureAt))
        let timer = Timer(timeInterval: delay, repeats: false) { [weak self] _ in self?.closeSessionIfIdle() }
        sessionTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    private static func png(_ image: CGImage) throws -> Data {
        guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            throw NotchQuickCaptureStore.Failure.write
        }
        return data
    }

    /// Session originals already live on disk. Retain only a small preview in
    /// the draft, so long sessions do not accumulate full-screen image buffers.
    private static func thumbnail(_ image: CGImage) -> CGImage {
        let scale = min(1, 176.0 / Double(max(image.width, image.height)))
        let width = max(1, Int(Double(image.width) * scale))
        let height = max(1, Int(Double(image.height) * scale))
        guard let context = CGContext(data: nil, width: width, height: height,
                                      bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return image }
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage() ?? image
    }

    private func writeSession(close: Bool) {
        guard let session, !saving else { return }
        let image = pendingSessionImage, capturedAt = pendingCaptureAt ?? now(), store = store
        sessionTimer?.invalidate(); sessionTimer = nil
        saving = true; error = nil
        io.async { [weak self] in
            // Keep a successful image even if the summary append fails, so a
            // retry never writes that screenshot or increments its count twice.
            var updated = session
            var imageSaved = false
            var attachment: Attachment?
            let result: Result<Void, Error> = Result {
                if let image {
                    updated = try store.saveSessionScreenshot(Self.png(image), session: session, at: capturedAt)
                    imageSaved = true
                    if let folder = updated.folder {
                        attachment = Attachment(image: Self.thumbnail(image),
                                                file: folder.appendingPathComponent(String(format: "%02d.png", updated.count)))
                    }
                }
                if close { try store.appendSession(updated) }
                try? store.removeExpiredScreenshots()
            }
            let savedSession = updated, didSaveImage = imageSaved, savedAttachment = attachment
            DispatchQueue.main.async {
                guard let self else { return }
                self.saving = false
                self.session = savedSession
                if didSaveImage {
                    if let savedAttachment {
                        self.images.append(savedAttachment)
                        self.captureUndoIDs.append(savedAttachment.id)
                    }
                    self.pendingSessionImage = nil; self.pendingCaptureAt = nil
                }
                switch result {
                case .success:
                    if close {
                        self.captureUndoIDs = []; self.undoPending = false
                        self.session = nil; self.sessionLabel = ""
                        if savedSession.count > 0 { NotchService.shared.signalQuickCapture(success: true) }
                    } else {
                        self.scheduleSessionClose()
                        if self.undoPending {
                            self.undoPending = false
                            self.undoLastScreenshot()
                        } else if self.capturingGroup { self.continueGroupCapture() }
                    }
                case .failure:
                    self.endGroupCapture()
                    self.undoPending = false
                    self.error = .save
                    NotchService.shared.openQuickCapture()
                    NotchService.shared.signalQuickCapture(success: false)
                }
            }
        }
    }

    func save() {
        guard canSave else { return }
        let text = text, images = images.filter { $0.file == nil }, store = store, date = now()
        let append = hasUnsavedContent
        saving = true; error = nil
        io.async { [weak self] in
            let result: Result<Void, Error> = Result {
                if append {
                    try store.append(text: text, pngs: images.map { try Self.png($0.image) }, at: date)
                }
                try? store.removeExpiredScreenshots()
            }
            DispatchQueue.main.async {
                guard let self else { return }
                self.saving = false
                switch result {
                case .success:
                    self.text = ""; self.images = []; self.error = nil; self.captureUndoIDs = []
                    if NotchService.shared.showingQuickCapture { NotchService.shared.collapse() }
                    NotchService.shared.signalQuickCapture(success: true)
                case .failure:
                    self.error = .save
                    NotchService.shared.openQuickCapture()
                    NotchService.shared.signalQuickCapture(success: false)
                }
                self.scheduleSessionClose()
            }
        }
    }

    func captureRegion() {
        guard !saving, selection == nil, !ScreenshotSelectionController.isSessionOnScreen else { return }
        if pendingSessionImage != nil { writeSession(close: false); return }
        closeSessionIfIdle()
        guard !saving else { return }
        guard Permissions.shared.screenRecording else {
            Permissions.shared.requestScreenRecording()
            failScreenshot()
            return
        }
        error = nil
        let controller = ScreenshotSelectionController(
            freeze: true, includePointer: false, showLastRegion: false, hideVorssaintWindows: true,
            protectedWindowIDs: { NotchService.shared.captureChromeWindowIDs },
            purpose: capturingGroup
                ? String(format: NotchQuickCaptureStrings.localized(L10n.shared.language).sessionCount, session?.count ?? 0) + " · ⌘Z · Esc"
                : NotchQuickCaptureStrings.localized(L10n.shared.language).title,
            requiresDraggedRegion: true)
        selection = controller
        NotchService.shared.collapse()
        controller.begin { [weak self, weak controller] outcome in
            guard let self, let controller, self.selection === controller else { return }
            self.selection = nil
            switch outcome {
            case .captured(let capture):
                if self.session != nil {
                    self.pendingSessionImage = capture.image
                    self.pendingCaptureAt = self.now()
                    self.writeSession(close: false)
                } else { self.images.append(.init(image: capture.image)) }
            case .cancelled: self.endGroupCapture(); self.scheduleSessionClose()
            default: self.endGroupCapture(); self.error = .screenshot; self.scheduleSessionClose()
            }
            if !self.capturingGroup { NotchService.shared.openQuickCapture() }
            if self.error != nil { NotchService.shared.signalQuickCapture(success: false) }
        }
    }

    private func failScreenshot() {
        endGroupCapture()
        error = .screenshot
        NotchService.shared.signalQuickCapture(success: false)
    }
}
