#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Production history action routing with inert windows/events; no native input."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
history = 'Sources/Vorssaint/Services/Clipboard/ClipboardHistoryService.swift'
support = 'Sources/Vorssaint/Services/Clipboard/ClipboardHistorySupport.swift'
fixture = r'''
import Foundation
import CoreGraphics
import Carbon.HIToolbox
class NSResponder: NSObject {}
class NSWindow: NSResponder {
    var isVisible = true, attachedSheet: NSWindow?, firstResponder: NSResponder?
    var frame = NSRect(x: 0, y: 0, width: 100, height: 100)
    var windowNumber = 1, keyCalls = 0
    func makeKey() { keyCalls += 1 }
    func makeFirstResponder(_ responder: NSResponder) { firstResponder = responder }
    func orderOut(_ sender: Any?) { isVisible = false }
    func endSheet(_ sheet: NSWindow) { attachedSheet = nil }
}
final class NSPanel: NSWindow {}
final class NSTextView: NSResponder {
    var composing = false, isFieldEditor = true, isEditable = true
    func hasMarkedText() -> Bool { composing }
}
final class NSEvent {
    struct ModifierFlags: OptionSet {
        let rawValue: Int
        static let command = Self(rawValue: 1), option = Self(rawValue: 2), shift = Self(rawValue: 4), control = Self(rawValue: 8)
    }
    struct EventTypeMask: OptionSet {
        let rawValue: Int
        static let keyDown = Self(rawValue: 1), leftMouseDown = Self(rawValue: 2), rightMouseDown = Self(rawValue: 4), otherMouseDown = Self(rawValue: 8)
    }
    static var monitors: [UUID: (EventTypeMask, (NSEvent) -> NSEvent?)] = [:]
    static var mouseLocation = NSPoint(x: 500, y: 500)
    var cgEvent: CGEvent?
    var window: NSWindow?
    var windowNumber: Int { window?.windowNumber ?? 0 }
    var modifierFlags: ModifierFlags = [], keyCode: UInt16 = 0, charactersIgnoringModifiers: String?, isARepeat = false
    var mask: EventTypeMask = .keyDown
    init(window: NSWindow?, key: String? = nil, code: UInt16 = 0, modifiers: ModifierFlags = []) {
        self.window = window; charactersIgnoringModifiers = key; keyCode = code; modifierFlags = modifiers
    }
    static func addLocalMonitorForEvents(matching mask: EventTypeMask, handler: @escaping (NSEvent) -> NSEvent?) -> Any {
        let id = UUID(); monitors[id] = (mask, handler); return id
    }
    static func addGlobalMonitorForEvents(matching mask: EventTypeMask, handler: @escaping (NSEvent) -> Void) -> Any { UUID() }
    static func removeMonitor(_ token: Any) { monitors.removeValue(forKey: token as! UUID) }
    static func send(_ event: NSEvent) -> NSEvent? {
        for (mask, handle) in Array(monitors.values) where mask.contains(event.mask) {
            if handle(event) == nil { return nil }
        }
        return event
    }
}
final class NSRunningApplication { var bundleIdentifier: String? }
final class NSWorkspace {
    static let shared = NSWorkspace()
    let notificationCenter = NotificationCenter()
    static let didActivateApplicationNotification = Notification.Name("activated")
    static let applicationUserInfoKey = "app"
}
enum AssistiveKeyboard {
    static let bundleID = "assistive"
    static func ownsCocoaPoint(_ point: NSPoint) -> Bool { false }
}
struct ClipboardHistoryEntry: Equatable {
    enum Kind { case text, image, files }
    var id = UUID(), text = "selected text", kind = Kind.text, imageFile: String?
}
struct ClipboardHistoryLayout { var sideArrowsMoveSelection = false }
enum SharedToolActions {
    static var available = true, presented: [ClipboardHistoryEntry] = [], currentOwner: UUID?, closed: (() -> Void)?
    static let child = NSWindow()
    static func supports(entry: ClipboardHistoryEntry) -> Bool { available && entry.kind != .files }
    static func present(entry: ClipboardHistoryEntry, from window: NSWindow, owner: UUID, onClose: @escaping () -> Void = {}) {
        presented.append(entry); currentOwner = owner; closed = onClose
    }
    static func cancel(owner: UUID) {
        guard currentOwner == owner else { return }
        let callback = closed; closed = nil; currentOwner = nil; callback?()
    }
    static func owns(window: NSWindow?, owner: UUID) -> Bool { currentOwner == owner && window === child }
}
final class History {
    var panel: NSPanel? = NSPanel()
    let quickActionsOwner = UUID()
    var selectedQuickEntry: ClipboardHistoryEntry? = .init()
    var quickBatchCount = 0, editingEntryID: UUID?, quickWindowPresentationID = UUID()
    var keyMonitor: Any?, localClickMonitor: Any?, outsideClickMonitor: Any?, activationObserver: NSObjectProtocol?
    var quickSelectionIsVisible = true, quickQuery = "", quickLayout = ClipboardHistoryLayout()
    var copies = 0, copyOnly = 0, toggles = 0
    func captureIfChanged(historyPanelClosing: Bool) {}
    func clearQuickBatchSelection() { quickBatchCount = 0 }
    func toggleQuickPreview() {}
    func toggleSelectedQuickEntryBatchSelection() { toggles += 1 }
    func copySelectedQuickEntryOnly() { copyOnly += 1 }
    func copySelectedQuickEntry() { copies += 1 }
    func selectAllQuickEntries() {}
    func togglePinSelectedQuickEntry() {}
    func removeSelectedQuickEntries() {}
    func moveQuickSelection(_ step: Int) {}
    static func digitIndex(for code: UInt16) -> Int? { nil }
    func copyQuickEntry(at index: Int) {}
    // METHODS
}
var checks = 0
func check(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
let service = History(), panel = History().panel!
service.panel = panel
let field = NSTextView()
panel.firstResponder = field
service.installKeyMonitor(for: panel)
service.installDismissMonitors(for: panel)
func actionsKey(_ window: NSWindow) -> NSEvent { NSEvent(window: window, key: "`", code: 50, modifiers: .option) }
check(service.canShowQuickActions, "one selected text entry offers actions")
check(NSEvent.send(actionsKey(panel)) == nil && SharedToolActions.presented.count == 1, "Option-backtick in search opens actions")
let original = SharedToolActions.presented.last!
service.selectedQuickEntry?.text = "newer entry content"
check(SharedToolActions.presented.last == original, "open action request retains value snapshot when entry changes")
SharedToolActions.cancel(owner: service.quickActionsOwner)
let commandK = NSEvent(window: panel, key: "k", code: 40, modifiers: .command)
check(NSEvent.send(commandK) === commandK, "Cmd-K remains available to the normal search responder")
let accent = actionsKey(panel)
accent.cgEvent = CGEvent(source: nil)
accent.cgEvent?.setIntegerValueField(.eventSourceUserData, value: SharedActionShortcut.accentEventTag)
check(NSEvent.send(accent) === accent, "remapped grave accent stays with the search responder")
for flags: NSEvent.ModifierFlags in [[], .command, .control, [.option, .shift], [.option, .control], [.option, .command]] {
    let event = NSEvent(window: panel, key: "`", code: 50, modifiers: flags)
    check(NSEvent.send(event) === event, "only exact Option-backtick opens history Actions")
}
check(panel.firstResponder === field && panel.keyCalls == 0, "history integration leaves focus restoration to shared menu")
for blocked in ["batch", "editor", "composing", "files", "disabled", "sheet", "other-window", "repeat"] {
    service.quickBatchCount = blocked == "batch" ? 1 : 0
    service.editingEntryID = blocked == "editor" ? UUID() : nil
    field.isFieldEditor = blocked != "editor"; field.composing = blocked == "composing"
    service.selectedQuickEntry?.kind = blocked == "files" ? .files : .text
    SharedToolActions.available = blocked != "disabled"
    panel.attachedSheet = blocked == "sheet" ? NSWindow() : nil
    let event = actionsKey(blocked == "other-window" ? NSWindow() : panel)
    event.isARepeat = blocked == "repeat"
    let previous = SharedToolActions.presented.count
    check(NSEvent.send(event) === event && SharedToolActions.presented.count == previous,
          "Option-backtick preserves \(blocked) ownership and never opens actions")
}
field.isFieldEditor = true; field.composing = false; service.editingEntryID = nil
service.quickBatchCount = 0; panel.attachedSheet = nil; SharedToolActions.available = true
service.selectedQuickEntry = .init(text: "image", kind: .image, imageFile: "selected.png")
check(NSEvent.send(actionsKey(panel)) == nil && SharedToolActions.presented.last?.imageFile == "selected.png",
      "image actions receive selected historical file identity")
let click = NSEvent(window: SharedToolActions.child); click.mask = .leftMouseDown
_ = NSEvent.send(click)
check(panel.isVisible && SharedToolActions.currentOwner == service.quickActionsOwner, "clicking owned action window keeps history open")
SharedToolActions.cancel(owner: service.quickActionsOwner)
let enter = NSEvent(window: panel, code: UInt16(kVK_Return))
check(NSEvent.send(enter) == nil && service.copies == 1, "plain Return retains existing paste action")
let shiftEnter = NSEvent(window: panel, code: UInt16(kVK_Return), modifiers: .shift)
check(NSEvent.send(shiftEnter) == nil && service.copyOnly == 1, "Shift-Return retains existing copy-only action")
_ = NSEvent.send(actionsKey(panel))
let keyCalls = panel.keyCalls
service.hideHistoryWindow()
check(!panel.isVisible && SharedToolActions.currentOwner == nil && panel.keyCalls == keyCalls,
      "history hide cancels owned action without restoring hidden focus")
check(NSEvent.monitors.isEmpty, "history hide removes key and local dismissal monitors")
panel.isVisible = true
service.installKeyMonitor(for: panel); service.installDismissMonitors(for: panel)
_ = NSEvent.send(actionsKey(panel))
let outside = NSEvent(window: NSWindow()); outside.mask = .leftMouseDown
_ = NSEvent.send(outside)
check(!panel.isVisible && SharedToolActions.currentOwner == nil, "unrelated window click still hides history and actions")
print("PASS: \(checks) clipboard shared action routing checks")
'''
methods = '\n'.join(declaration(history, prefix).replace('private ', '', 1) for prefix in [
    '    var canShowQuickActions:', '    func showQuickActions()', '    func hideHistoryWindow()',
    '    private func installKeyMonitor(', '    private func installDismissMonitors(',
    '    private static func mouseIsInside(', '    private func removeDismissMonitors()', '    private func removeKeyMonitor()'])
fixture = fixture.replace('// METHODS', methods)
fixture += '\n' + declaration('Sources/Vorssaint/Core/SharedActionShortcut.swift', 'enum SharedActionShortcut {')
fixture += '\n' + '\n'.join(declaration(support, prefix) for prefix in [
    'enum ClipboardHistoryPreview {', 'enum ClipboardHistoryNavigation {', 'enum ClipboardHistoryEscape {', 'enum ClipboardHistoryFocus {'])
fixture += '\nenum ClipboardHistoryBatch {\n' + '\n'.join(declaration(support, prefix) for prefix in [
    '    static func listOwnsCopyShortcut(', '    static func listOwnsSelectAllShortcut(', '    static func listOwnsDeleteShortcut(']) + '\n}\n'
with tempfile.TemporaryDirectory(prefix='clipboard-shared-actions-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(fixture)
    binary = folder / 'check'
    subprocess.run(['swiftc', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
