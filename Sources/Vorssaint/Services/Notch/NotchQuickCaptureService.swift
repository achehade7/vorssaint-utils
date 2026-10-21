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
        let id = UUID()
        let image: CGImage
        let file: URL?
        init(image: CGImage, file: URL? = nil) { self.image = image; self.file = file }
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
        let controller = selection
        selection = nil
        controller?.cancel()
        scheduleSessionClose()
    }

    func cancel() {
        guard !saving else { return }
        // A failed session image must remain available to Retry/Stop.
        guard pendingSessionImage == nil else { NotchService.shared.collapse(); return }
        text = ""; images = []; error = nil
        NotchService.shared.collapse()
    }

    func removeImage(_ id: UUID) {
        guard !saving else { return }
        images.removeAll { $0.id == id && $0.file == nil }
    }

    func startSession() {
        guard session == nil, !saving, !isSelecting else { return }
        session = .init(startedAt: now(), label: sessionLabel)
        error = nil
        scheduleSessionClose()
    }

    func stopSession() {
        guard session != nil, !saving, !isSelecting else { return }
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
                    if let savedAttachment { self.images.append(savedAttachment) }
                    self.pendingSessionImage = nil; self.pendingCaptureAt = nil
                }
                switch result {
                case .success:
                    if close {
                        self.session = nil; self.sessionLabel = ""
                        if savedSession.count > 0 { NotchService.shared.signalQuickCapture(success: true) }
                    } else { self.scheduleSessionClose() }
                case .failure:
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
                    self.text = ""; self.images = []; self.error = nil
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
            purpose: NotchQuickCaptureStrings.localized(L10n.shared.language).title,
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
            case .cancelled: self.scheduleSessionClose()
            default: self.error = .screenshot; self.scheduleSessionClose()
            }
            NotchService.shared.openQuickCapture()
            if self.error != nil { NotchService.shared.signalQuickCapture(success: false) }
        }
    }

    private func failScreenshot() {
        error = .screenshot
        NotchService.shared.signalQuickCapture(success: false)
    }
}
