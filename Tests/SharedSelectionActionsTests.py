#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""External-selection request lifecycle with inert readers/menu/HUD; no user text."""
from pathlib import Path
import os
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
enum SelectedTextReader {
    struct Selection { let text: String }
    static var reads: [(pid_t, Bool)] = []
    static func read(processID: pid_t) -> Selection? {
        reads.append((processID, Thread.isMainThread))
        return Selection(text: "  exact background\r\nselection  ")
    }
}
enum SharedToolActionStrings {
    static let selectionNeedsAccessibility = "Accessibility permission is required."
    static let selectionUnavailable = "No selected text is available."
    static let selectionSecureInput = "Secure Input prevents reading the selection."
}
enum QuickToolHUD {
    static var messages: [String] = []
    static func show(icon: String, message: String) { messages.append(message) }
}
enum SharedToolActions {
    enum Content { case text(String) }
    static var values: [String] = [], owners: [UUID] = [], closes: [() -> Void] = []
    static func present(content: Content, title: String, from: NSWindow?, owner: UUID,
                        onClose: @escaping () -> Void) {
        precondition(from == nil && Thread.isMainThread)
        if case .text(let text) = content { values.append(text) }
        owners.append(owner); closes.append(onClose)
    }
    static func cancel(owner: UUID) { owners.append(owner) }
}
var checks = 0
func check(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
final class Harness {
    var pid: pid_t? = 42
    var permission = true, secure = false
    var reads: [(pid_t, (String?) -> Void)] = []
    var presentations: [(String, String, UUID, () -> Void)] = []
    var failures: [SharedSelectionActionsService.Failure] = []
    var dismissed: [UUID] = []
    let application = NotificationCenter(), workspace = NotificationCenter()
    lazy var service = SharedSelectionActionsService(
        frontmost: { [unowned self] in self.pid.map { .init(processID: $0, name: "External fixture") } },
        trusted: { [unowned self] in self.permission }, secureInput: { [unowned self] in self.secure },
        readSelection: { [unowned self] pid, completion in self.reads.append((pid, completion)) },
        present: { [unowned self] text, title, owner, close in self.presentations.append((text, title, owner, close)) },
        dismiss: { [unowned self] in self.dismissed.append($0) },
        feedback: { [unowned self] in self.failures.append($0) },
        applicationNotifications: application, workspaceNotifications: workspace)
}
let h = Harness()
h.service.trigger()
check(h.reads.count == 1 && h.reads[0].0 == 42 && h.presentations.isEmpty, "trigger captures source PID and waits for selection")
let exact = " \tselected 👩🏽‍💻\r\nsecond line  "
h.reads[0].1(exact)
check(h.presentations.count == 1 && h.presentations[0].0 == exact && h.presentations[0].1 == "External fixture",
      "selected text retains exact spaces, CRLF and Unicode")
h.service.trigger()
check(h.reads.count == 1 && h.dismissed.last == h.presentations[0].2, "second trigger closes own menu without another read")
h.service.trigger()
check(h.reads.count == 2, "closed request allows a fresh selection")
h.service.trigger()
h.reads[1].1("late toggled selection")
check(h.presentations.count == 1, "second trigger cancels pending read and rejects late result")
h.service.trigger()
h.service.cancel()
h.reads[2].1("late stopped selection")
check(h.presentations.count == 1, "explicit stop or disable invalidates pending result")
h.service.trigger()
h.reads[3].1("new current selection")
h.presentations[0].3()
h.service.trigger()
check(h.reads.count == 4, "old menu close callback cannot clear a newer active request")

for unavailable: String? in [nil, "", " \t\r\n"] {
    h.service.trigger(); h.reads.last!.1(unavailable)
    check(h.failures.last == .unavailable && h.presentations.count == 2, "missing selection reports unavailable without presenting")
}
h.permission = false
let readsBeforePermission = h.reads.count
h.service.trigger()
check(h.reads.count == readsBeforePermission && h.failures.last == .accessibility, "missing AX permission reports clearly without reading")
h.permission = true; h.secure = true
h.service.trigger()
check(h.reads.count == readsBeforePermission && h.failures.last == .secureInput, "Secure Input rejects selection reading")
h.secure = false; h.pid = ProcessInfo.processInfo.processIdentifier
h.service.trigger()
check(h.reads.count == readsBeforePermission && h.failures.last == .unavailable, "external entrypoint rejects own process")
h.pid = nil; h.service.trigger()
check(h.reads.count == readsBeforePermission && h.failures.last == .unavailable, "absent front app does not read")
h.pid = 42; h.service.trigger(); h.pid = 43
h.reads.last!.1("wrong front app")
check(h.presentations.count == 2, "changed front PID invalidates delayed completion")
h.pid = 42; h.service.trigger(); let switchedRead = h.reads.last!.1
h.pid = 43; h.workspace.post(name: NSWorkspace.didActivateApplicationNotification, object: nil)
h.pid = 42; switchedRead("switched away and returned")
check(h.presentations.count == 2, "activation away then back still invalidates outstanding request")
h.service.trigger()
h.application.post(name: NSApplication.didResignActiveNotification, object: nil)
h.reads.last!.1("deactivated request")
check(h.presentations.count == 2, "application deactivation while reading cancels request")
h.service.trigger(); h.permission = false
h.reads.last!.1("permission revoked")
check(h.presentations.count == 2 && h.failures.last == .accessibility, "permission is checked again after selection completes")
h.permission = true; h.service.trigger(); h.secure = true
h.reads.last!.1("secure input began")
check(h.presentations.count == 2 && h.failures.last == .secureInput, "Secure Input is checked again before presentation")
h.secure = false; h.service.trigger(); h.reads.last!.1("open standalone selection")
let dismissedBefore = h.dismissed.count
h.pid = 43; h.workspace.post(name: NSWorkspace.didActivateApplicationNotification, object: nil)
check(h.dismissed.count == dismissedBefore + 1, "switching apps closes the standalone menu")
h.pid = 42; h.service.trigger(); h.reads.last!.1("closed by menu")
h.presentations.last!.3()
let readsBeforeReopen = h.reads.count
h.service.trigger()
check(h.reads.count == readsBeforeReopen + 1, "normal menu close clears ownership for next trigger")
h.service.cancel()
let readsBeforeQueuedTrigger = h.reads.count, failuresBeforeQueuedTrigger = h.failures.count
h.pid = 43; h.permission = false
h.service.trigger(expectedSourcePID: 42)
check(h.reads.count == readsBeforeQueuedTrigger && h.failures.count == failuresBeforeQueuedTrigger,
      "source changed between shortcut press and queued trigger is ignored before reading or feedback")
h.pid = 42; h.permission = true
h.service.trigger(expectedSourcePID: 42)
check(h.reads.count == readsBeforeQueuedTrigger + 1, "matching press PID starts the intended selection request")
let presentationsBeforeQueuedCancel = h.presentations.count
h.pid = 43
h.service.trigger(expectedSourcePID: 42)
h.reads.last!.1("cancelled after source switch")
check(h.presentations.count == presentationsBeforeQueuedCancel && h.failures.count == failuresBeforeQueuedTrigger,
      "toggle cancellation precedes expected-PID rejection and invalidates pending work")

// Exercise the production default worker/main-queue path with the inert reader.
let application = NotificationCenter(), workspace = NotificationCenter()
let worker = SharedSelectionActionsService(frontmost: { .init(processID: 101, name: "Worker fixture") },
    trusted: { true }, secureInput: { false },
    applicationNotifications: application, workspaceNotifications: workspace)
worker.trigger()
let deadline = Date().addingTimeInterval(3)
while SharedToolActions.values.isEmpty && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
check(SelectedTextReader.reads.count == 1 && SelectedTextReader.reads[0].0 == 101 && !SelectedTextReader.reads[0].1,
      "default selection read runs off main with the captured PID")
check(SharedToolActions.values == ["  exact background\r\nselection  "], "default presentation receives exact selected text and no parent")
worker.cancel()
let denied = SharedSelectionActionsService(frontmost: { nil }, trusted: { false }, secureInput: { false },
    applicationNotifications: application, workspaceNotifications: workspace)
denied.trigger()
check(QuickToolHUD.messages.last == SharedToolActionStrings.selectionNeedsAccessibility, "default permission feedback names missing permission")
print("PASS: \(checks) external selection lifecycle checks")
'''
with tempfile.TemporaryDirectory(prefix='shared-selection-actions-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(fixture)
    binary = folder / 'check'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Services/QuickTools/SharedSelectionActionsService.swift'),
                    str(source), '-o', str(binary)], check=True)
    home = folder / 'preferences'
    home.mkdir()
    subprocess.run([str(binary)], check=True, timeout=20, env={**os.environ, 'CFFIXED_USER_HOME': str(home)})
