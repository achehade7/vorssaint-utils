// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// Runs the production OCR entry points and completion with controlled queues.
/// Vision, feature preferences and the clipboard are local fakes; no user data
/// or system pasteboard is touched.
enum ScreenTextCompletionTests {
    typealias CGImage = Int
    enum BarcodeDetector { typealias Reading = String }
    enum ScreenshotSelectionController {
        struct Capture { let image: CGImage }
        enum Outcome {
            case captured(Capture), region(Int), scrollingRegion(Int), color(Int), cancelled, failed
        }
        static var isSessionOnScreen = false
    }

    final class Queue {
        var pending: [() -> Void] = []
        func async(execute work: @escaping () -> Void) { pending.append(work) }
        func drain() {
            let work = pending
            pending = []
            work.forEach { $0() }
        }
    }
    enum DispatchQueue {
        enum QoS { case userInitiated }
        static var main = Queue()
        static var background = Queue()
        static func global(qos: QoS) -> Queue { background }
    }
    enum AppFeature {
        case screenOCR, screenRecorder
        static var available = true
        var isAvailable: Bool { Self.available }
    }
    struct UserDefaults {
        static let standard = Self()
        static var values: [String: Bool] = [:]
        func bool(forKey key: String) -> Bool { Self.values[key] ?? false }
        func integer(forKey key: String) -> Int { 0 }
    }
    struct L10n {
        static let shared = Self()
        struct Language { let rawValue = "en-US" }
        struct Strings { let ocrCopied = "copied"; let ocrNoText = "empty" }
        let language = Language()
        let s = Strings()
    }
    enum MediaSupport {
        static func recognitionLanguages(for language: String) -> [String] { [language] }
    }
    final class NSPasteboard {
        static let general = NSPasteboard()
        var changeCount = 0
        var value = "original"
        func write(_ value: String) { self.value = value; changeCount += 1 }
    }
    enum QuickToolHUD {
        static var messages: [String] = []
        static func show(icon: String, message: String) { messages.append(message) }
    }
    final class ScreenTextPreviewController {
        static let shared = ScreenTextPreviewController()
        var texts: [String] = []
        var available = true
        func close() {}
        func show(text: String) -> Bool {
            guard available else { return false }
            texts.append(text)
            return true
        }
    }
    final class QRResultController {
        static let shared = QRResultController()
        var readings: [String] = []
        func show(reading: String) { readings.append(reading) }
    }
    class State {
        var recognitionGeneration = 0
        static var outcomes: [Int: ScreenTextService.Outcome] = [:]
        static var requests: [(image: Int, qr: Bool, joinLines: Bool, languages: [String])] = []
        /// Stands in for the area bound: maps an oversized capture to the
        /// smaller image Vision should read, and records every image bounded.
        static var scaledImages: [Int: Int] = [:]
        static var boundedImages: [Int] = []
        static func recognitionImage(_ image: Int) -> Int {
            boundedImages.append(image)
            return scaledImages[image] ?? image
        }
        static func outcome(for image: Int, detectQRCodes: Bool, removeLineBreaks: Bool,
                            fallbackLanguages: [String]) -> ScreenTextService.Outcome {
            requests.append((image, detectQRCodes, removeLineBreaks, fallbackLanguages))
            return outcomes[image] ?? .text("capture \(image)")
        }
        static func copyToPasteboard(_ value: String) { NSPasteboard.general.write(value) }
    }

    // Execute the actual global capture entry and result dispatcher with an
    // inert chooser; normal text results use the OCR/clipboard fixture above.
    enum ScreenCaptureTool: CaseIterable {
        case screenshot, recording, text, color
        static func available() -> [Self] {
            allCases.filter { $0 != .text || AppFeature.screenOCR.isAvailable }
        }
        func opensDuringRecording(fromShortcut: Bool) -> Bool { fromShortcut }
        func showsCaptureMenu(fromShortcut: Bool) -> Bool { !fromShortcut }
    }
    enum ScreenshotSupport {
        static func sanitizedDelay(_ delay: Int) -> Int { delay }
        static func captureRouteIsAuthorized(selected: ScreenCaptureTool) -> Bool {
            ScreenCaptureTool.available().contains(selected)
        }
    }
    final class NotchService {
        static let shared = NotchService()
        var showingQuickCapture = false
    }
    final class NotchQuickCaptureService {
        static let shared = NotchQuickCaptureService()
        var textCaptures = 0
        func captureText() { textCaptures += 1 }
    }
    final class Permissions {
        static let shared = Permissions()
        let screenRecording = true
        func requestScreenRecording() {}
    }
    struct RecorderSelectionAudioOptions {}
    final class ScreenRecorderService {
        static let shared = ScreenRecorderService()
        let hasActiveCapture = false
        func stopOrCancelActiveCapture() -> Bool { false }
        func prepareForSelection() -> Bool { true }
        func record(_ region: Int, audioOptions: RecorderSelectionAudioOptions) {}
    }
    final class ScreenshotService {
        static let shared = ScreenshotService()
        func receiveUnifiedCapture(_ capture: ScreenshotSelectionController.Capture) {}
        func receiveUnifiedScrollingRegion(_ region: Int) {}
    }
    final class ColorSamplerService {
        static let shared = ColorSamplerService()
        func pickNative() {}
        func receiveUnifiedColor(_ color: Int) {}
    }
    class CaptureState {
        var selection: Int?
        var countdown: DispatchWorkItem?
        var countdownTools: [ScreenCaptureTool]?
        var countdownRemaining = 0
        var selections: [ScreenCaptureTool] = []
        func cancelSelection() { selection = nil; countdown = nil }
        func beginSelection(tools: [ScreenCaptureTool], selected: ScreenCaptureTool, showsCaptureMenu: Bool) {
            selections.append(selected)
        }
        func tickCountdown(tools: [ScreenCaptureTool], selected: ScreenCaptureTool, showsCaptureMenu: Bool) {}
        func showFailure(for tool: ScreenCaptureTool) {}
    }

    static func reset() {
        DispatchQueue.main = Queue()
        DispatchQueue.background = Queue()
        AppFeature.available = true
        UserDefaults.values = [DefaultsKey.screenOCRDetectQRCodes: true,
                               DefaultsKey.screenOCRRemoveLineBreaks: true]
        NSPasteboard.general.value = "original"
        NSPasteboard.general.changeCount = 0
        ScreenTextPreviewController.shared.texts = []
        ScreenTextPreviewController.shared.available = true
        QuickToolHUD.messages = []
        QRResultController.shared.readings = []
        State.outcomes = [:]
        State.requests = []
        State.scaledImages = [:]
        State.boundedImages = []
        NotchService.shared.showingQuickCapture = false
        NotchQuickCaptureService.shared.textCaptures = 0
    }

    static func finish() {
        DispatchQueue.background.drain()
        DispatchQueue.main.drain()
    }

    static func run(_ suite: TestSuite) {
        defer { reset() }
        reset()
        let normal = ScreenTextService()
        normal.copyText(from: 42)
        suite.expect(NSPasteboard.general.value == "original" && State.requests.isEmpty,
                     "preview OCR does not block or copy before background recognition")
        finish()
        suite.expect(NSPasteboard.general.value == "capture 42"
                     && ScreenTextPreviewController.shared.texts == ["capture 42"]
                     && QuickToolHUD.messages.isEmpty,
                     "an unchanged clipboard receives the recognized text and success feedback")
        suite.expect(State.requests.count == 1 && State.requests[0].image == 42
                     && !State.requests[0].qr && State.requests[0].joinLines
                     && State.requests[0].languages == ["en-US"],
                     "preview OCR uses the captured image and language/line preferences, bypassing QR")

        reset()
        ScreenTextPreviewController.shared.available = false
        let fallback = ScreenTextService()
        fallback.copyText(from: 43)
        finish()
        suite.expect(NSPasteboard.general.value == "capture 43" && QuickToolHUD.messages == ["copied"],
                     "OCR still copies and confirms when the island cannot show a preview")

        reset()
        State.scaledImages[60] = 24
        let oversized = ScreenTextService()
        oversized.copyText(from: 60)
        suite.expect(State.boundedImages.isEmpty,
                     "an oversized capture is not scaled on the main thread")
        finish()
        suite.expect(State.boundedImages == [60] && State.requests.map { $0.image } == [24]
                     && NSPasteboard.general.value == "capture 24",
                     "an oversized capture is scaled to the recognition bound before Vision reads it")

        for duringRecognition in [true, false] {
            reset()
            let service = ScreenTextService()
            service.copyText(from: 1)
            if !duringRecognition { DispatchQueue.background.drain() }
            NSPasteboard.general.write("newer user copy")
            finish()
            suite.expect(NSPasteboard.general.value == "newer user copy" && QuickToolHUD.messages.isEmpty
                         && ScreenTextPreviewController.shared.texts.isEmpty,
                         "OCR preserves a newer copy made before or after recognition finishes")
        }

        reset()
        AppFeature.available = false
        let disabled = ScreenTextService()
        disabled.copyText(from: 1)
        disabled.receiveUnifiedCapture(.init(image: 2))
        suite.expect(DispatchQueue.background.pending.isEmpty,
                     "disabled OCR cannot start from the preview or unified capture")

        for resync in [false, true] {
            reset()
            let service = ScreenTextService()
            service.copyText(from: 1)
            DispatchQueue.background.drain()
            AppFeature.available = false
            if resync {
                service.syncWithPreferences()
                AppFeature.available = true
            }
            finish()
            suite.expect(NSPasteboard.general.value == "original" && QuickToolHUD.messages.isEmpty,
                         "turning OCR off suppresses pending results, including after reinstall")
        }

        reset()
        let suspended = ScreenTextService()
        suspended.copyText(from: 1)
        suspended.suspend()
        finish()
        suite.expect(NSPasteboard.general.value == "original" && QuickToolHUD.messages.isEmpty,
                     "suspending OCR suppresses a pending preview result")

        for newestFirst in [false, true] {
            reset()
            let latest = ScreenTextService()
            latest.copyText(from: 1)
            latest.copyText(from: 2)
            if newestFirst { DispatchQueue.background.pending.reverse() }
            finish()
            suite.expect(NSPasteboard.general.value == "capture 2"
                         && ScreenTextPreviewController.shared.texts == ["capture 2"]
                         && QuickToolHUD.messages.isEmpty,
                         "only the latest OCR request copies, with newestFirst=\(newestFirst)")
        }

        for detectQR in [false, true] {
            for joinLines in [false, true] {
                for preview in [false, true] {
                    reset()
                    UserDefaults.values = [DefaultsKey.screenOCRDetectQRCodes: detectQR,
                                           DefaultsKey.screenOCRRemoveLineBreaks: joinLines]
                    let service = ScreenTextService()
                    if preview { service.copyText(from: 7) }
                    else { service.receiveUnifiedCapture(.init(image: 7)) }
                    finish()
                    suite.expect(State.requests.count == 1
                                 && State.requests[0].qr == (preview ? false : detectQR)
                                 && State.requests[0].joinLines == joinLines,
                                 "OCR respects QR=\(detectQR), joinLines=\(joinLines), preview=\(preview)")
                    suite.expect(NSPasteboard.general.value == "capture 7",
                                 "both entry points still copy text with each preference combination")
                }
            }
        }

        reset()
        State.outcomes[1] = .empty
        let empty = ScreenTextService()
        empty.copyText(from: 1)
        finish()
        suite.expect(NSPasteboard.general.value == "original" && QuickToolHUD.messages == ["empty"],
                     "no text leaves the clipboard intact and reports the empty result")

        reset()
        State.outcomes[1] = .qr("https://example.com")
        let unified = ScreenTextService()
        unified.receiveUnifiedCapture(.init(image: 1))
        finish()
        suite.expect(State.requests.first?.qr == true
                     && QRResultController.shared.readings == ["https://example.com"]
                     && NSPasteboard.general.value == "original",
                     "unified OCR still honors QR detection and presents its result without copying")

        reset()
        State.outcomes[8] = .text("first line\nsecond line")
        var captureResult: Result<String, Error>?
        ScreenTextService.recognizeCaptureText(8) { captureResult = $0 }
        suite.expect(captureResult == nil && State.requests.isEmpty,
                     "capture OCR returns asynchronously without blocking its owner")
        NSPasteboard.general.write("a newer unrelated copy")
        finish()
        suite.expect((try? captureResult?.get()) == "first line\nsecond line"
                     && State.requests.count == 1 && !State.requests[0].qr && !State.requests[0].joinLines,
                     "capture OCR returns multiline text independently of clipboard preferences")
        suite.expect(NSPasteboard.general.value == "a newer unrelated copy"
                     && QuickToolHUD.messages.isEmpty && ScreenTextPreviewController.shared.texts.isEmpty
                     && QRResultController.shared.readings.isEmpty,
                     "capture OCR has no clipboard or presentation side effects")

        for disabledAtStart in [false, true] {
            reset()
            captureResult = nil
            AppFeature.available = !disabledAtStart
            ScreenTextService.recognizeCaptureText(9) { captureResult = $0 }
            AppFeature.available = false
            finish()
            if case .failure? = captureResult {
                suite.expect(true, "capture OCR always completes with failure when its feature is unavailable")
            } else { suite.expect(false, "disabled capture OCR cannot strand its owner's pending operation") }
        }
        reset()
        captureResult = nil
        State.outcomes[10] = .empty
        ScreenTextService.recognizeCaptureText(10) { captureResult = $0 }
        finish()
        if case .failure? = captureResult {
            suite.expect(true, "empty capture OCR returns a failure for the draft to resolve")
        } else { suite.expect(false, "empty capture OCR must not publish an empty extract") }

        for showingCapture in [false, true] {
            for fromShortcut in [false, true] {
                reset()
                NotchService.shared.showingQuickCapture = showingCapture
                let router = ScreenCaptureService()
                router.capture(initial: .text, fromShortcut: fromShortcut)
                if showingCapture && fromShortcut {
                    suite.expect(NotchQuickCaptureService.shared.textCaptures == 1 && router.selections.isEmpty,
                                 "global OCR shortcut while Quick Capture is visible enters its text capture only")
                    finish()
                    suite.expect(NSPasteboard.general.value == "original" && NSPasteboard.general.changeCount == 0
                                 && State.requests.isEmpty,
                                 "redirected OCR shortcut never enters standard recognition or clipboard path")
                } else {
                    suite.expect(NotchQuickCaptureService.shared.textCaptures == 0 && router.selections == [.text],
                                 "OCR outside Quick Capture and non-shortcut actions keep standard text chooser")
                    router.route(.captured(.init(image: 11)), selected: router.selections[0], recorderAudio: .init())
                    finish()
                    suite.expect(NSPasteboard.general.value == "capture 11" && NSPasteboard.general.changeCount == 1
                                 && State.requests.first?.image == 11,
                                 "standard selected text still uses existing copy completion")
                }
            }
        }
        reset()
        NotchService.shared.showingQuickCapture = true
        let screenshotRouter = ScreenCaptureService()
        screenshotRouter.capture(initial: .screenshot, fromShortcut: true)
        suite.expect(NotchQuickCaptureService.shared.textCaptures == 0 && screenshotRouter.selections == [.screenshot],
                     "Quick Capture does not intercept another capture tool's shortcut")
        AppFeature.available = false
        let unavailableRouter = ScreenCaptureService()
        unavailableRouter.capture(initial: .text, fromShortcut: true)
        suite.expect(NotchQuickCaptureService.shared.textCaptures == 0 && unavailableRouter.selections == [.screenshot]
                     && NSPasteboard.general.changeCount == 0,
                     "disabled OCR never enters Quick Capture or text-copy routing")
    }
}
