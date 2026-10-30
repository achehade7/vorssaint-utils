#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Click production transport buttons through WindowServer, without locking or playing music."""
from pathlib import Path
import os
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]


def declaration(path, marker):
    source = (repo / path).read_text()
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


swift = r'''
import AppKit
import SwiftUI
import ApplicationServices
STYLE
PANEL
HOST
struct NotchPlayback {
    let isPlaying = true, canSendCommandsDirectly = false
    let commandContext = 0
}
final class NotchMusicService: ObservableObject {
    enum Command { case toggle, previous, next }
    var commands: [Command] = []
    @Published var enabled = true
    func send(_ command: Command, context: Int) -> Bool { commands.append(command); return true }
    func canPerform(_ command: Command) -> Bool { enabled }
}
struct Fixture: View {
    @ObservedObject var music: NotchMusicService
    let command: NotchMusicService.Command
    let symbol: String
    let reduceMotion = true
    let accent = Color.purple
    @State var requestedPlaying: Bool?
    var body: some View {
        button(symbol, size: 22, title: "Transport", command: command, playback: NotchPlayback())
            .frame(width: 200, height: 120)
    }
    BUTTON
}
final class Backdrop: NSView {
    var clicks = 0
    override func mouseDown(with event: NSEvent) { clicks += 1 }
}
func pump(_ seconds: TimeInterval) {
    let end = Date().addingTimeInterval(seconds)
    while Date() < end {
        if let event = NSApp.nextEvent(matching: .any, until: Date().addingTimeInterval(0.005), inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.002))
    }
}
guard AXIsProcessTrusted() else { fatalError("Native clicks require the test runner's existing Accessibility access") }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let screen = NSScreen.main!
let frame = NSRect(x: screen.visibleFrame.midX - 100, y: screen.visibleFrame.midY - 60, width: 200, height: 120)
let backdrop = NotchLockScreenPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
backdrop.backgroundColor = .darkGray
backdrop.level = .floating
let target = Backdrop(frame: NSRect(origin: .zero, size: frame.size))
backdrop.contentView = target
backdrop.orderFrontRegardless()
let panel = NotchLockScreenPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = false
panel.hidesOnDeactivate = false; panel.isReleasedWhenClosed = false
panel.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
// Keep ignoresMouseEvents unset, exactly as the production interactive panel.
let savedPointer = CGEvent(source: nil)!.location
let primaryHeight = NSScreen.screens.first!.frame.maxY
func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: frame.minX + x, y: primaryHeight - frame.minY - y) }
func move(_ point: CGPoint) {
    CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)!.post(tap: .cghidEventTap)
    pump(0.05)
}
func click(_ x: CGFloat, _ y: CGFloat) {
    move(point(-30, -30))
    move(point(x, y))
    for type in [CGEventType.leftMouseDown, .leftMouseUp] {
        CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: point(x, y), mouseButton: .left)!.post(tap: .cghidEventTap)
        pump(0.04)
    }
}
var failures: [String] = [], checks = 0
for (command, symbol) in [(NotchMusicService.Command.toggle, "pause.fill"), (.toggle, "play.fill"), (.previous, "backward.end.fill"), (.next, "forward.end.fill")] {
    let music = NotchMusicService()
    let host = NotchLockScreenHostingView(rootView: AnyView(Fixture(music: music, command: command, symbol: symbol)))
    host.sizingOptions = []
    panel.contentView = host; panel.setFrame(frame, display: false); panel.orderFrontRegardless(); pump(0.1)
    for (x,y) in [(80.0,60.0),(120,60),(100,42),(100,78),(81,43),(119,43),(81,77),(119,77),(96,60)] {
        let before = music.commands.count
        click(x,y); checks += 1
        if music.commands.count != before + 1 || music.commands.last != command {
            failures.append("\(symbol) at (\(x),\(y)): \(music.commands.count - before) commands")
        }
    }
    let before = music.commands.count, passed = target.clicks
    click(15,15); checks += 1
    if music.commands.count != before || target.clicks != passed + 1 { failures.append("clear margin must pass through") }
    music.enabled = false
    host.rootView = AnyView(Fixture(music: music, command: command, symbol: symbol)); pump(0.05)
    click(96,60); checks += 1
    if music.commands.count != before { failures.append("disabled transport must not send commands") }

}
panel.orderOut(nil); backdrop.orderOut(nil); move(savedPointer)
if !failures.isEmpty { print("FAIL: " + failures.joined(separator: "; ")); exit(1) }
print("PASS: \(checks) native transport hit-area and click-through checks")
'''
for token, path, marker in [
    ("STYLE", "Sources/Vorssaint/UI/Notch/NotchComponents.swift", "struct NotchButtonStyle:"),
    ("PANEL", "Sources/Vorssaint/Services/Notch/NotchLockScreenService.swift", "final class NotchLockScreenPanel:"),
    ("HOST", "Sources/Vorssaint/Services/Notch/NotchLockScreenService.swift", "private final class NotchLockScreenHostingView:"),
    ("BUTTON", "Sources/Vorssaint/UI/Notch/NotchLockScreenView.swift", "    private func button(_ symbol:"),
]:
    swift = swift.replace(token, declaration(path, marker))
with tempfile.TemporaryDirectory(prefix="vorssaint-lock-buttons-") as directory:
    root = Path(directory)
    (root / "main.swift").write_text(swift)
    subprocess.run(["swiftc", "-sdk", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk", str(root / "main.swift"), "-o", str(root / "checks")], check=True)
    subprocess.run([str(root / "checks")], check=True, env={**os.environ, "CFFIXED_USER_HOME": directory})
