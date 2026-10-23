#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Production Actions routing and mode transition with inert windows and events."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
service = 'Sources/Vorssaint/Services/CommandBar/CommandBarService.swift'
monitor = declaration(service, '    private func installMonitors(for panel:')
# Run the production prefix through the Actions branch. Later branches retain
# their existing native editing/navigation contracts in CommandBarFeatureTests.
monitor = monitor[:monitor.index('            if event.modifierFlags.contains(.command) {')]
monitor += '            _ = navigationModifiers\n            return event\n        }\n    }\n'
monitor = monitor.replace('private func', 'func', 1)
fixture = r'''
import Foundation
import CoreGraphics
class NSWindow { var attachedSheet: NSWindow? }
final class NSPanel: NSWindow {}
final class NSEvent {
    struct ModifierFlags: OptionSet {
        let rawValue: Int
        static let command = Self(rawValue: 1), option = Self(rawValue: 2)
        static let shift = Self(rawValue: 4), control = Self(rawValue: 8)
    }
    enum EventTypeMask { case keyDown }
    static var handler: ((NSEvent) -> NSEvent?)?
    var cgEvent: CGEvent?
    var window: NSWindow?
    let keyCode: UInt16
    let modifierFlags: ModifierFlags
    var isARepeat = false
    init(window: NSWindow, keyCode: UInt16 = 50, modifiers: ModifierFlags = .option) {
        self.window = window; self.keyCode = keyCode; modifierFlags = modifiers
    }
    static func addLocalMonitorForEvents(matching: EventTypeMask, handler: @escaping (NSEvent) -> NSEvent?) -> Any {
        self.handler = handler; return 1
    }
}
struct GlobalShortcutModifiers { init(eventFlags: NSEvent.ModifierFlags) {} }
final class CommandBarDroplet {
    static let shared = CommandBarDroplet()
    func hurry() {}
}
final class NotchService {
    static let shared = NotchService()
    var presentationWindow: NSPanel? = NSPanel()
}
struct Entry { let id: String }
struct ClipboardEntry: Equatable { var text: String }
enum SharedToolActions {
    static var received: [ClipboardEntry] = []
    static var source: NSWindow?
    static func present(entry: ClipboardEntry, from window: NSWindow, owner: UUID) {
        received.append(entry); source = window
    }
}
final class Bar {
    enum Presentation { case window, island, droplet }
    enum Mode: Equatable { case search, actions(entryID: String), capturingShortcut }
    var panel: NSPanel? = NSPanel()
    var presentation = Presentation.window
    var mode = Mode.search
    var selectedEntry: Entry? = Entry(id: "fixture.application")
    var selectedClipboard: ClipboardEntry?
    var canOpenActions = true, composing = false
    var savedQuery = "", query = "terminal", actionIndex = 8
    var layoutChanges = 0, recordings = 0
    var keyMonitor: Any?
    let contentActionsOwner = UUID()
    func clipboardEntry(for: Entry) -> ClipboardEntry? { selectedClipboard }
    func fieldIsComposing(in: NSPanel) -> Bool { composing }
    func handleCaptureKey(keyCode: Int64, modifiers: GlobalShortcutModifiers) { recordings += 1 }
    func refreshPanelLayout() { layoutChanges += 1 }
    func removeMonitors() { NSEvent.handler = nil }
    // METHODS
}
var checks = 0
func check(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
let bar = Bar(), panel = NSPanel()
bar.panel = panel; bar.installMonitors(for: panel)
check(NSEvent.handler?(NSEvent(window: panel)) == nil && bar.mode == .actions(entryID: "fixture.application")
      && bar.savedQuery == "terminal" && bar.actionIndex == 0 && bar.layoutChanges == 1,
      "Option-backtick opens normal app-management Actions and retains the query")
bar.mode = .search
bar.selectedClipboard = ClipboardEntry(text: "owned payload")
check(NSEvent.handler?(NSEvent(window: panel)) == nil && bar.mode == .search
      && SharedToolActions.received.last?.text == "owned payload" && SharedToolActions.source === panel,
      "the same shortcut opens shared actions for a clipboard result without changing normal mode")
bar.selectedClipboard?.text = "later payload"
check(SharedToolActions.received.last?.text == "owned payload", "clipboard action handoff owns the selected value")
bar.presentation = .island
_ = NSEvent.handler?(NSEvent(window: panel))
check(SharedToolActions.source === NotchService.shared.presentationWindow,
      "island Command Bar anchors shared actions to the island")
bar.presentation = .window; bar.selectedClipboard = nil
for flags in 0..<16 {
    bar.mode = .search
    let event = NSEvent(window: panel, modifiers: .init(rawValue: flags))
    let accepted = flags == NSEvent.ModifierFlags.option.rawValue
    check((NSEvent.handler?(event) == nil) == accepted && (bar.mode != .search) == accepted,
          "normal Actions accepts only exact Option-backtick")
}
for blocked in ["Cmd-K", "ordinary-backtick", "other-window", "sheet", "composition", "repeat"] {
    bar.mode = .search; bar.composing = blocked == "composition"
    panel.attachedSheet = blocked == "sheet" ? NSWindow() : nil
    let event = NSEvent(window: blocked == "other-window" ? NSPanel() : panel,
        keyCode: blocked == "Cmd-K" ? 40 : 50,
        modifiers: blocked == "Cmd-K" ? .command : blocked == "ordinary-backtick" ? [] : .option)
    event.isARepeat = blocked == "repeat"
    check(NSEvent.handler?(event) === event && bar.mode == .search,
          "Actions forwards \(blocked) to its existing owner")
}
panel.attachedSheet = nil; bar.composing = false
let accent = NSEvent(window: panel)
accent.cgEvent = CGEvent(source: nil)
accent.cgEvent?.setIntegerValueField(.eventSourceUserData, value: SharedActionShortcut.accentEventTag)
check(NSEvent.handler?(accent) === accent && bar.mode == .search,
      "remapped grave accent stays with Command Bar search")
bar.mode = .capturingShortcut
check(NSEvent.handler?(NSEvent(window: panel)) == nil && bar.recordings == 1 && bar.mode == .capturingShortcut,
      "shortcut recording keeps ownership of Option-backtick")
print("PASS: \(checks) Command Bar Actions checks")
'''
fixture = fixture.replace('// METHODS', monitor + '\n' + declaration(service, '    func openActions()'))
fixture += '\n' + declaration('Sources/Vorssaint/Core/SharedActionShortcut.swift', 'enum SharedActionShortcut {')
assert 'case "k":' not in declaration(service, '    private func installMonitors(for panel:')
with tempfile.TemporaryDirectory(prefix='command-bar-actions-') as temporary:
    folder = Path(temporary)
    (folder / 'main.swift').write_text(fixture)
    binary = folder / 'check'
    subprocess.run(['swiftc', str(folder / 'main.swift'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
