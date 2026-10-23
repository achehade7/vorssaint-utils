#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native AX proof using a child-owned text window; never reads other app selections."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
import ApplicationServices
let expected = " \tExternal fixture 👩🏽‍💻\r\nexact second line  "
if CommandLine.arguments.contains("--source") {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    let panel = NSWindow(contentRect: NSRect(x: 200, y: 200, width: 640, height: 300),
                         styleMask: [.titled, .closable], backing: .buffered, defer: false)
    panel.title = "Vorssaint isolated selection fixture"
    panel.isReleasedWhenClosed = false
    let editor = NSTextView(frame: NSRect(x: 0, y: 0, width: 640, height: 300))
    editor.isRichText = false
    editor.isAutomaticQuoteSubstitutionEnabled = false
    editor.isAutomaticDashSubstitutionEnabled = false
    editor.font = .monospacedSystemFont(ofSize: 15, weight: .regular)
    editor.string = "prefix" + expected + "suffix"
    panel.contentView = editor
    app.finishLaunching()
    panel.makeKeyAndOrderFront(nil)
    panel.makeFirstResponder(editor)
    editor.setSelectedRange(NSRange(location: 6, length: (expected as NSString).length))
    app.activate(ignoringOtherApps: true)
    // If the controller is interrupted, the synthetic window still exits itself.
    DispatchQueue.main.asyncAfter(deadline: .now() + 20) { app.terminate(nil) }
    app.run()
    exit(0)
}
enum SharedToolActionStrings {
    static let selectionNeedsAccessibility = "Accessibility permission required"
    static let selectionUnavailable = "Selection unavailable"
    static let selectionSecureInput = "Secure Input active"
}
enum QuickToolHUD {
    static var messages: [String] = []
    static func show(icon: String, message: String) { messages.append(message) }
}
enum SharedToolActions {
    enum Content { case text(String) }
    static var received: [String] = []
    static var onClose: (() -> Void)?
    static func present(content: Content, title: String, from: NSWindow?, owner: UUID,
                        onClose: @escaping () -> Void) {
        precondition(Thread.isMainThread && from == nil)
        if case .text(let text) = content { received.append(text) }
        self.onClose = onClose
    }
    static func cancel(owner: UUID) { let close = onClose; onClose = nil; close?() }
}
func wait(_ condition: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    return condition()
}
guard AXIsProcessTrusted() else {
    fputs("ERROR: Native selection fixture requires existing Accessibility permission; no prompt or user selection read.\n", stderr)
    exit(2)
}
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native selection fixture requires an unlocked Mac.\n", stderr); exit(2)
}
let source = Process()
source.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
source.arguments = ["--source"]
source.standardOutput = FileHandle.nullDevice
try source.run()
func stopSource() { if source.isRunning { source.terminate(); source.waitUntilExit() } }
func fail(_ message: String) -> Never { fputs(message + "\n", stderr); stopSource(); exit(1) }
defer { stopSource() }
let sourcePID = source.processIdentifier
guard wait({ NSWorkspace.shared.frontmostApplication?.processIdentifier == sourcePID }) else {
    fail("ERROR: Isolated source window did not become frontmost; no selection was read.")
}
// This is deliberately narrower than production: only the child PID can be read,
// even if the user switches applications between readiness and the request.
let service = SharedSelectionActionsService(frontmost: {
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == sourcePID else { return nil }
    return .init(processID: sourcePID, name: "Isolated AX fixture")
})
service.trigger()
guard wait({ !SharedToolActions.received.isEmpty || !QuickToolHUD.messages.isEmpty }) else {
    fail("ERROR: Isolated selected-text request did not finish.")
}
guard SharedToolActions.received == [expected] else {
    // Diagnostics intentionally omit the contents, including unexpected AX data.
    fail("ERROR: External AX fixture did not preserve its exact selected text.")
}
service.cancel()
print("PASS: external child-window AX selection preserves Unicode, whitespace and CRLF through the default async service")
'''
with tempfile.TemporaryDirectory(prefix='shared-selection-ax-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(fixture)
    binary = folder / 'check'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Services/SelectedTextReader.swift'),
                    str(repo / 'Sources/Vorssaint/Services/QuickTools/SharedSelectionActionsService.swift'),
                    str(source), '-o', str(binary)], check=True)
    if '--compile-only' not in sys.argv:
        home = folder / 'preferences'
        home.mkdir()
        subprocess.run([str(binary)], check=True, timeout=25,
                       env={**os.environ, 'CFFIXED_USER_HOME': str(home)})
