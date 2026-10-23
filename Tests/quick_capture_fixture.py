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
    case screenOCR
    static var ocrAvailable = true
    var isAvailable: Bool { Self.ocrAvailable }
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


def run(code, include_view=False, arguments=None):
    sources = [
        'Services/Notch/NotchQuickCaptureStore.swift',
        'Services/Notch/NotchQuickCaptureService.swift',
        'Services/Notch/NotchQuickCaptureMeetings.swift',
        'Services/Notch/NotchQuickCaptureKeyTracker.swift',
        'Core/NotchQuickCaptureStrings.swift',
        'Services/CommandBar/MeetingNoteStore.swift',
        'Core/MeetingNotePerson.swift',
    ]
    view = ''
    if include_view:
        full = (REPO / 'Sources/Vorssaint/UI/Notch/NotchQuickCaptureView.swift').read_text()
        view = full[full.index('struct NotchQuickCaptureView:'):full.index('struct NotchQuickCapturePulse:')]
        view += full[full.index('struct NotchObsidianRightClick:'):]
    with tempfile.TemporaryDirectory(prefix='quick-capture-fixture-') as temporary:
        folder = Path(temporary)
        source = folder / 'main.swift'
        source.write_text(STUBS + '\n' + view + '\n' + code)
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
