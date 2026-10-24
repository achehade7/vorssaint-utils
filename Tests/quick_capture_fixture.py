# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Compile production capture components with isolated app/calendar/capture boundaries."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]

STUBS = r'''
import AppKit
import SwiftUI
import Combine
import Carbon.HIToolbox
import Darwin

final class NotchService: ObservableObject {
    static let shared = NotchService()
    struct Geometry { var safeContentTop: CGFloat = 24 }
    let geometry = Geometry()
    @Published var showingQuickCapture = true
    var presentationWindow: NSPanel?
    var captureChromeWindowIDs: Set<CGWindowID> = []
    var signals: [Bool] = []
    var opens = 0, closes = 0
    func openQuickCapture() { showingQuickCapture = true; opens += 1 }
    func collapse() { showingQuickCapture = false; closes += 1 }
    func signalQuickCapture(success: Bool) { signals.append(success) }
}
final class Permissions {
    static let shared = Permissions()
    var screenRecording = true
    var requests = 0
    func requestScreenRecording() { requests += 1 }
}
enum AppFeature {
    case screenOCR, clipboardHistory, textSnippets, screenshot
    static var ocrAvailable = true
    var isAvailable: Bool { self == .screenOCR ? Self.ocrAvailable : true }
}
enum AppLanguage: String, CaseIterable {
    case enUS = "en-US", ptBR = "pt-BR", tr, ru, es, sk, de, fr, it, ja, ko, uk
    case zhHans = "zh-Hans", zhTW = "zh-TW", zhHK = "zh-HK"
}
final class L10n: ObservableObject {
    static let shared = L10n()
    @Published var language = AppLanguage.enUS
}
enum NotchNeonPalette { static let purple = Color.purple, blue = Color.blue }
enum NotchLayout { static let horizontalInset: CGFloat = 18, bottomInset: CGFloat = 14 }

struct NotchCalendarEvent {
    let id: String
    var title = "Meeting"
    let start: Date
    let end: Date
    var allDay = false
    var noteEventKey: String? = nil
    var notePeople: [MeetingNotePerson] = []
}
final class NotchCalendarService {
    static let shared = NotchCalendarService()
    var events: [NotchCalendarEvent] = []
    var authorized = true
    var reads: [Date] = []
    func meetingEvents(now: Date = Date()) async -> [NotchCalendarEvent] {
        reads.append(now)
        return authorized ? events : []
    }
}
enum ScreenTextService {
    static func recognizeCaptureText(_ image: CGImage, completion: @escaping (Result<String, Error>) -> Void) {
        completion(.success("Fixture text"))
    }
}

/// No screen access or panel creation. Tests choose when acquisition completes.
final class ScreenshotSelectionController {
    struct Capture {
        let image: CGImage
        var capturedAt = Date()
        var scale: CGFloat = 1
        var anchorRect: CGRect = .zero
    }
    enum Outcome { case captured(Capture), cancelled, failed }
    static var isSessionOnScreen = false
    static var last: ScreenshotSelectionController?
    var isAcquiring = false
    let freeze: Bool
    let freezeOnCommand: Bool
    let requiresDraggedRegion: Bool
    let purpose: String?
    let onSelectionBegan: ((NSEvent.ModifierFlags) -> Void)?
    var protectedWindowIDs: Set<CGWindowID>
    var completion: ((Outcome) -> Void)?
    init(freeze: Bool, includePointer: Bool, showLastRegion: Bool, hideVorssaintWindows: Bool,
         protectedWindowIDs: @escaping () -> Set<CGWindowID>, purpose: String?,
         requiresDraggedRegion: Bool, freezeOnCommand: Bool = false,
         onSelectionBegan: ((NSEvent.ModifierFlags) -> Void)? = nil) {
        self.freeze = freeze
        self.freezeOnCommand = freezeOnCommand
        self.requiresDraggedRegion = requiresDraggedRegion
        self.purpose = purpose
        self.protectedWindowIDs = protectedWindowIDs()
        self.onSelectionBegan = onSelectionBegan
        Self.last = self
    }
    func begin(completion: @escaping (Outcome) -> Void) {
        Self.isSessionOnScreen = true
        self.completion = completion
    }
    func complete(_ outcome: Outcome) {
        Self.isSessionOnScreen = false
        isAcquiring = false
        let callback = completion
        completion = nil
        callback?(outcome)
    }
    func cancel() { complete(.cancelled) }
}
'''

ACTION_DESTINATIONS = r'''
extension NSScreen {
    var displayID: CGDirectDisplayID { deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID ?? 0 }
}
struct ClipboardHistoryEntry {
    enum Kind { case text, image, files }
    var text: String
    var kind = Kind.text
    var imageFile: String? = nil
    var preview: String { text }
}
enum ClipboardImageStore { static func imageData(named: String) -> Data? { nil } }
final class PayloadInspectorService {
    static let shared = PayloadInspectorService()
    var received: [String] = []
    func receive(_ text: String) { received.append(text) }
}
final class ClipboardDiffService {
    static let shared = ClipboardDiffService()
    var received: [(String, Bool)] = []
    func receive(_ text: String, asBefore: Bool, name: String?) { received.append((text, asBefore)) }
}
final class SnippetLibraryService {
    static let shared = SnippetLibraryService()
    var received: [String] = []
    func saveCapturedText(_ text: String) { received.append(text) }
}
final class ScreenshotService {
    static let shared = ScreenshotService()
    func annotate(_ image: CGImage) { preconditionFailure("unexpected screenshot handoff") }
}
final class ScreenCompareService {
    static let shared = ScreenCompareService()
    func receive(_ image: CGImage, asBefore: Bool, name: String?) { preconditionFailure("unexpected image comparison") }
}
enum ExtractedTextController {
    static func show(image: CGImage) { preconditionFailure("unexpected OCR window") }
}
enum TextTransformStrings { static let title = "Text tools" }
enum TextTransformController {
    static var received: [String] = []
    static func show(text: String) { received.append(text) }
}
// Browser destinations are outside the capture fixture; Jira routing has its own suite.
struct CommandBarEntry { let run: (Int?) -> Void }
enum CommandBarTicketSearch {
    static func ticketKeys(in text: String) -> [String] { [] }
    static func directEntry(query: String) -> (entry: CommandBarEntry, priority: Int)? { nil }
}
'''

HEADLESS_ACTIONS = r'''
enum SharedToolActions {
    enum Content { case text(String) }
    static func present(content: Content, title: String, from window: NSWindow, owner: UUID) {}
    static func cancel(owner: UUID) {}
}
'''


def run(code, include_view=False, arguments=None):
    sources = [
        'Services/Notch/NotchQuickCaptureStore.swift',
        'Services/Notch/NotchQuickCaptureService.swift',
        'Services/Notch/NotchQuickCaptureMeetings.swift',
        'Services/Notch/NotchQuickCaptureKeyTracker.swift',
        'Core/NotchQuickCaptureStrings.swift',
        'Core/SharedToolActionStrings.swift',
        'Core/SharedActionShortcut.swift',
        'Services/CommandBar/MeetingNoteStore.swift',
        'Core/MeetingNotePerson.swift',
    ]
    view = ''
    if include_view:
        sources += ['Services/QuickTools/SharedToolActions.swift', 'Core/SnippetCaptureStrings.swift',
                    'Core/AppKitExtensions.swift', 'UI/ToolAppearance.swift']
        full = (REPO / 'Sources/Vorssaint/UI/Notch/NotchQuickCaptureView.swift').read_text()
        view = full[full.index('struct NotchQuickCaptureView:'):full.index('struct NotchQuickCapturePulse:')]
        view += full[full.index('struct NotchObsidianRightClick:'):]
    with tempfile.TemporaryDirectory(prefix='quick-capture-fixture-') as temporary:
        folder = Path(temporary)
        source = folder / 'main.swift'
        source.write_text(STUBS + '\n' + (ACTION_DESTINATIONS if include_view else HEADLESS_ACTIONS)
                          + '\n' + view + '\n' + code)
        binary = folder / 'checks'
        subprocess.run(['xcrun', 'swiftc', '-target', 'arm64-apple-macosx14.0', '-sdk',
                        '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk', '-Xfrontend',
                        '-interface-compiler-version', '-Xfrontend', '6.3.2',
                        *[str(REPO / 'Sources/Vorssaint' / path) for path in sources],
                        str(source), '-o', str(binary)], check=True, cwd=REPO)
        prefs = folder / 'preferences'
        prefs.mkdir()
        subprocess.run([str(binary), *(sys.argv[1:] if arguments is None else arguments)],
                       check=True, cwd=REPO, env={**os.environ, 'CFFIXED_USER_HOME': str(prefs)})
