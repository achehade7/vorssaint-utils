#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Production one-shot expiry methods with isolated defaults and app-open spies."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
meeting = 'Sources/Vorssaint/Services/CommandBar/MeetingNoteService.swift'
snippets = 'Sources/Vorssaint/Services/Snippets/TextSnippetService.swift'
code = r'''
import Foundation
import Combine
enum Defaults { static let defaultSnippetSoundName = "Tink" }
enum DefaultsKey { static let textSnippets = "snippets" }
final class Preferences {
    static let standard = Preferences()
    var value: Data?
    func data(forKey key: String) -> Data? { value }
    func set(_ data: Data, forKey key: String) { value = data }
}
typealias UserDefaults = Preferences
final class Workspace {
    static let shared = Workspace()
    var opened: [URL] = []
    func open(_ url: URL) { opened.append(url) }
}
typealias NSWorkspace = Workspace
final class NotchService {
    static let shared = NotchService()
    func perform(_ action: () -> Void) { action() }
}
final class SnippetLibraryService {
    static let shared = SnippetLibraryService()
    var reloads = 0
    func syncWithPreferences() { reloads += 1 }
}
final class MeetingShortcut {
    var activeNote: URL?, activeNoteEnd: Date?, expiry: Timer?
    MEETING_METHODS
}
final class SnippetExpiry {
    var expiryTimer: Timer?, calls = 0
    func syncWithPreferences() { calls += 1; scheduleExpiry() }
    EXPIRY_METHOD
}
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ label: String) {
    checks += 1; precondition(condition(), label)
}
func wait(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
let shortcut = MeetingShortcut()
let first = URL(string: "obsidian://open?path=/test/first.md")!
let second = URL(string: "obsidian://open?path=/test/second.md")!
shortcut.keepShortcut(first, until: Date().addingTimeInterval(0.06))
shortcut.openActiveNote()
expect(Workspace.shared.opened == [first], "meeting shortcut opens its prepared note")
shortcut.keepShortcut(second, until: Date().addingTimeInterval(0.2))
wait(0.1)
expect(shortcut.activeNote == second, "replacing shortcut cancels previous meeting timer")
shortcut.openActiveNote()
expect(Workspace.shared.opened == [first, second], "shortcut points to most recently prepared meeting")
wait(0.15)
expect(shortcut.activeNote == nil && shortcut.expiry == nil, "shortcut disappears at meeting end")
shortcut.openActiveNote()
expect(Workspace.shared.opened.count == 2, "expired note cannot reopen from stale button")
shortcut.keepShortcut(first, until: Date().addingTimeInterval(-1))
expect(shortcut.activeNote == nil, "preparing an ended meeting cannot leave a shortcut")
var permanent = TextSnippet(); permanent.name = "Keep"; permanent.replacement = "forever"
var temporary = permanent; temporary.id = UUID(); temporary.name = "Today"; temporary.expiresAt = Date().addingTimeInterval(0.06)
Preferences.standard.value = try JSONEncoder().encode([permanent, temporary])
let expiry = SnippetExpiry(); expiry.syncWithPreferences()
expect(expiry.expiryTimer != nil, "temporary snippet arms one timer")
wait(0.12)
expect(TextSnippetSupport.decode(Preferences.standard.value) == [permanent], "timer removes expired text from stored preferences")
expect(expiry.expiryTimer == nil && expiry.calls == 2 && SnippetLibraryService.shared.reloads == 1,
       "expiry refreshes consumers and stops; no polling")
Preferences.standard.value = Data("bad".utf8)
expiry.syncWithPreferences()
expect(Preferences.standard.value == Data("bad".utf8), "expiry never repairs or overwrites damaged store")
print("Island shortcut lifecycle: \(checks) checks passed")
'''
methods = '\n'.join(declaration(meeting, prefix).replace('private func', 'func', 1) for prefix in [
    '    func openActiveNote()', '    private func clearActiveNote()', '    private func keepShortcut('])
code = code.replace('MEETING_METHODS', methods).replace('EXPIRY_METHOD', declaration(snippets, '    private func scheduleExpiry()'))
with tempfile.TemporaryDirectory(prefix='island-shortcut-lifecycle-') as folder:
    main = Path(folder) / 'main.swift'; main.write_text(code)
    binary = Path(folder) / 'tests'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Services/Snippets/TextSnippetSupport.swift'), str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
