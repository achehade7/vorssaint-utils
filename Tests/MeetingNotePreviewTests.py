#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native preview render and Return/Escape; no real calendar, vault or browser."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / 'Sources/Vorssaint/Services/CommandBar/MeetingNoteService.swift').read_text()
view = source[source.index('private struct MeetingNoteView:'):]
code = r'''
import AppKit
import SwiftUI
import Combine

enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
final class L10n { static let shared = L10n(); let language = AppLanguage.enUS }
enum NotchQuickCaptureStrings {
    struct Text { let cancel = "Cancel" }
    static func localized(_ language: AppLanguage) -> Text { Text() }
}
enum NotchNeonPalette {
    static let purple = Color(red: 0.73, green: 0.49, blue: 1)
    static let blue = Color(red: 0.43, green: 0.56, blue: 1)
}
VIEW
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let input = MeetingNoteInput(identity: "fixture", title: "SAP-531 Review", start: Date(), end: Date().addingTimeInterval(1800), people: [.init(name: "Example Person")])
let draft = MeetingNoteDraft(input: input, store: .init(vault: URL(fileURLWithPath: "/unavailable-test-vault")))
var confirms = 0, cancels = 0
private let view = MeetingNoteView(draft: draft, cancel: { if draft.cancel() { cancels += 1 } }, confirm: { confirms += 1 })
private let host = NSHostingView(rootView: view)
host.frame = NSRect(x: 0, y: 0, width: 440, height: 250)
let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = host
window.makeKeyAndOrderFront(nil)
RunLoop.main.run(until: Date().addingTimeInterval(0.2))
host.layoutSubtreeIfNeeded()
precondition(host.fittingSize.height <= 250, "preview fits its panel")
if let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
    host.cacheDisplay(in: host.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/island-meeting-note-preview.png"))
}
func key(_ code: UInt16) {
    let characters = code == 53 ? "\u{1b}" : "\r"
    app.sendEvent(NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 1,
                                 windowNumber: window.windowNumber, context: nil, characters: characters,
                                 charactersIgnoringModifiers: characters, isARepeat: false, keyCode: code)!)
    RunLoop.main.run(until: Date().addingTimeInterval(0.05))
}
key(36)
precondition(confirms == 1 && cancels == 0, "Return confirms once")
key(53)
precondition(cancels == 1 && draft.cancelled, "Escape cancels from editable topic field")
window.orderOut(nil)
print("PASS: native meeting preview render, Return and Escape")
'''.replace('VIEW', view)
with tempfile.TemporaryDirectory(prefix='meeting-note-preview-') as folder:
    main = Path(folder) / 'main.swift'; main.write_text(code)
    binary = Path(folder) / 'tests'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Core/MeetingNotePerson.swift'),
                    str(repo / 'Sources/Vorssaint/Core/MeetingNoteStrings.swift'),
                    str(repo / 'Sources/Vorssaint/Services/CommandBar/MeetingNoteStore.swift'),
                    str(repo / 'Sources/Vorssaint/Services/CommandBar/MeetingNoteDraft.swift'), str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
