#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Production shortcut state, native PID tap/dead keys, and native focus ownership.

Only this probe receives posted keys. Session-level physical keyboard delivery is
not simulated: CGEventPostToPid enters immediately before process-specific taps.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
headless = r'''
import AppKit
import Carbon.HIToolbox
import CoreGraphics

var checks = 0
var cleanupOnFailure: () -> Void = {}
func expect(_ value: Bool, _ message: String) {
    checks += 1
    guard value else { cleanupOnFailure(); fputs("FAIL: \(message)\n", stderr); exit(1) }
}
func flags(_ bits: Int) -> NSEvent.ModifierFlags {
    let all: [NSEvent.ModifierFlags] = [.option, .control, .shift, .command]
    return all.enumerated().reduce([]) { $1.offset < 4 && bits & (1 << $1.offset) != 0 ? $0.union($1.element) : $0 }
}
func stateChecks() {
    for bits in 0..<16 {
        for extras in [NSEvent.ModifierFlags(), [.capsLock], [.numericPad, .function]] {
            let modifiers = flags(bits).union(extras)
            for code: UInt16 in 0..<128 {
                expect(SharedActionShortcut.matches(keyCode: code, modifiers: modifiers) == (code == 50 && bits == 1),
                       "exact Option-backtick matching for code \(code), flags \(bits), extras \(extras)")
            }
            for local in [false, true] {
                for enabled in [false, true] {
                    var state = SharedActionKeyState()
                    let expected: SharedActionKeyState.Outcome = !enabled ? .pass
                        : bits == 3 ? .accent : bits == 1 ? (local ? .pass : .openActions) : .pass
                    expect(state.handle(keyCode: 50, isDown: true, isRepeat: false,
                                        modifiers: modifiers, local: local, enabled: enabled) == expected,
                           "fresh press chooses exactly one local/global/accent route")
                    let held: SharedActionKeyState.Outcome = !enabled ? .pass
                        : bits == 3 ? .accent : bits == 1 ? .consume : .pass
                    expect(state.handle(keyCode: 0, isDown: false, isRepeat: false, modifiers: [], local: !local, enabled: !enabled) == .pass,
                           "unrelated key release never changes the owned press")
                    for _ in 0..<3 {
                        expect(state.handle(keyCode: 50, isDown: true, isRepeat: true, modifiers: [], local: !local, enabled: false) == held,
                               "repeat keeps initial press intent despite focus/modifier/availability changes")
                    }
                    expect(state.handle(keyCode: 50, isDown: false, isRepeat: false, modifiers: [], local: !local, enabled: false) == held,
                           "matching release remains owned after all modifiers release")
                    expect(state.handle(keyCode: 50, isDown: false, isRepeat: false, modifiers: modifiers, local: local, enabled: enabled) == .pass,
                           "release clears state exactly once")
                }
            }
        }
    }
    var state = SharedActionKeyState()
    for tag in [Int64(0), SharedActionShortcut.accentEventTag] {
        for bits in 0..<16 {
            let event = CGEvent(keyboardEventSource: nil, virtualKey: 50, keyDown: true)!
            event.flags = CGEventFlags(rawValue: UInt64(flags(bits).rawValue))
            event.setIntegerValueField(.eventSourceUserData, value: tag)
            expect(SharedActionShortcut.matches(NSEvent(cgEvent: event)!) == (bits == 1 && tag == 0),
                   "event-aware matcher excludes remapped accent instead of reopening Actions")
        }
    }
    expect(state.handle(keyCode: 50, isDown: true, isRepeat: true, modifiers: .option, local: false, enabled: true) == .pass,
           "an orphan repeat does not open Actions")
    expect(state.handle(keyCode: 50, isDown: true, isRepeat: false, modifiers: .option, local: true, enabled: true) == .pass,
           "first local press is delivered to source-local monitor")
    expect(state.handle(keyCode: 50, isDown: true, isRepeat: true, modifiers: .option, local: false, enabled: true) == .consume,
           "focus changes during local hold never reopen global Actions")
    state.reset()
    expect(state.handle(keyCode: 50, isDown: false, isRepeat: false, modifiers: [], local: false, enabled: true) == .pass,
           "reset removes stale physical press ownership")
    expect(state.handle(keyCode: 50, isDown: true, isRepeat: false, modifiers: [.control, .option], local: false, enabled: true) == .accent,
           "accent can follow reset")
    state.reset()
    expect(state.handle(keyCode: 50, isDown: true, isRepeat: true, modifiers: .option, local: false, enabled: true) == .pass,
           "reset also clears accent repeats")
}
stateChecks()
if CommandLine.arguments.contains("--headless") {
    print("PASS: \(checks) shortcut state checks")
    exit(0)
}
'''
handler = r'''
enum ShortcutCapture { static var isCapturing = false }
final class SharedSelectionActionsService {
    static let shared = SharedSelectionActionsService()
    var triggers = 0
    var sourcePIDs: [pid_t] = []
    func trigger(expectedSourcePID: pid_t) { triggers += 1; sourcePIDs.append(expectedSourcePID) }
}
final class Handler {
    var state = SharedActionKeyState()
    var tap: CFMachPort?
    var generation = UUID()
    var available = true
'''
handler += declaration("Sources/Vorssaint/Services/QuickTools/SharedActionHotkeyService.swift", "    private func handle(type:").replace("private func", "func", 1)
handler += "}\n"
native = r'''
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
if CommandLine.arguments.contains("--focus-helper") {
    let helper = NSWindow(contentRect: NSRect(x: 170, y: 170, width: 420, height: 130),
                          styleMask: [.titled], backing: .buffered, defer: false)
    helper.title = "Isolated shortcut focus helper"
    helper.isReleasedWhenClosed = false
    helper.contentView = NSTextField(labelWithString: "Temporary focus fixture — no input requested")
    helper.makeKeyAndOrderFront(nil)
    app.activate(ignoringOtherApps: true)
    DispatchQueue.main.asyncAfter(deadline: .now() + 15) { app.terminate(nil) }
    app.run()
    exit(0)
}
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native shortcut checks require an unlocked Mac. No input was sent.\n", stderr); exit(2)
}
let input = TISCopyCurrentKeyboardInputSource().takeRetainedValue()
let layoutID = Unmanaged<CFString>.fromOpaque(TISGetInputSourceProperty(input, kTISPropertyInputSourceID)!).takeUnretainedValue() as String
guard layoutID == "com.apple.keylayout.US" else {
    fputs("ERROR: Dead-key proof requires existing US input source, found \(layoutID). Layout was not changed.\n", stderr); exit(2)
}
let clipboardBefore = NSPasteboard.general.changeCount
let token: Int64 = 0x5354414354494F
final class Panel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}
let window = NSWindow(contentRect: NSRect(x: 160, y: 160, width: 520, height: 220),
                      styleMask: [.titled, .closable], backing: .buffered, defer: false)
window.title = "Isolated shortcut native checks"
window.isReleasedWhenClosed = false
let text = NSTextView(frame: NSRect(x: 0, y: 0, width: 520, height: 220))
text.isRichText = false
text.isAutomaticQuoteSubstitutionEnabled = false
text.isAutomaticDashSubstitutionEnabled = false
window.contentView = text
let panel = Panel(contentRect: NSRect(x: 180, y: 180, width: 400, height: 130),
                  styleMask: [.titled, .nonactivatingPanel], backing: .buffered, defer: false)
panel.title = "Isolated nonactivating shortcut panel"
panel.isReleasedWhenClosed = false
panel.hidesOnDeactivate = false
let panelText = NSTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 130))
panel.contentView = panelText
var localActions = 0
let localMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp]) { event in
    guard event.window === window || event.window === panel else { return event }
    // Never admit unrelated input into test text or logs.
    guard let marker = event.cgEvent?.getIntegerValueField(.eventSourceUserData),
          marker == token || marker == SharedActionShortcut.accentEventTag else { return nil }
    if event.type == .keyDown, !event.isARepeat, !ShortcutCapture.isCapturing,
       (event.window?.firstResponder as? NSTextView)?.hasMarkedText() != true,
       SharedActionShortcut.matches(event) {
        localActions += 1
        return nil
    }
    return event
}
window.makeKeyAndOrderFront(nil)
window.makeFirstResponder(text)
app.activate(ignoringOtherApps: true)
let handler = Handler()
let mask = CGEventMask((1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue))
guard let tap = CGEvent.tapCreateForPid(pid: getpid(), place: .headInsertEventTap, options: .defaultTap,
    eventsOfInterest: mask, callback: { _, type, event, context in
        guard event.getIntegerValueField(.eventSourceUserData) == token else { return Unmanaged.passUnretained(event) }
        let result = Unmanaged<Handler>.fromOpaque(context!).takeUnretainedValue().handle(type: type, event: event)
        return result
    }, userInfo: Unmanaged.passUnretained(handler).toOpaque()) else {
    fputs("ERROR: Active PID event tap unavailable.\n", stderr); exit(2)
}
handler.tap = tap
let loopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)!
CFRunLoopAddSource(CFRunLoopGetMain(), loopSource, .commonModes)
CGEvent.tapEnable(tap: tap, enable: true)
let helper = Process()
helper.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
helper.arguments = ["--focus-helper"]
helper.standardOutput = FileHandle.nullDevice
helper.standardError = FileHandle.nullDevice
func cleanup() {
    CGEvent.tapEnable(tap: tap, enable: false); CFMachPortInvalidate(tap)
    CFRunLoopRemoveSource(CFRunLoopGetMain(), loopSource, .commonModes)
    if let localMonitor { NSEvent.removeMonitor(localMonitor) }
    panel.close(); window.close()
    if helper.isRunning { helper.terminate() }
}
cleanupOnFailure = cleanup
func key(_ code: CGKeyCode, _ flags: CGEventFlags = [], down: Bool = true, repeated: Bool = false) {
    let event = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: down)!
    event.flags = flags
    event.setIntegerValueField(.eventSourceUserData, value: token)
    event.setIntegerValueField(.keyboardEventAutorepeat, value: repeated ? 1 : 0)
    event.postToPid(getpid())
}
func press(_ code: CGKeyCode, _ flags: CGEventFlags = []) { key(code, flags); key(code, flags, down: false) }
func settle() async { try? await Task.sleep(nanoseconds: 100_000_000) }
func until(_ message: String, _ condition: () -> Bool) async {
    let deadline = Date().addingTimeInterval(3)
    while !condition(), Date() < deadline { await settle() }
    if !condition() { cleanup() }
    expect(condition(), message)
}
func resetText() { text.inputContext?.discardMarkedText(); text.string = ""; text.setSelectedRange(NSRange(location: 0, length: 0)) }
Task { @MainActor in
    await until("probe owns regular text input", { window.isKeyWindow && window.firstResponder === text })
    if !CommandLine.arguments.contains("--focus-only") {
    ShortcutCapture.isCapturing = true
    press(50, .maskAlternate); await settle(); press(0); await settle()
    expect(text.string == "à" && localActions == 0, "recording shortcut bypass retains original Option-grave composition")
    resetText(); ShortcutCapture.isCapturing = false
    text.setMarkedText("composition", selectedRange: NSRange(location: 11, length: 0),
                       replacementRange: NSRange(location: NSNotFound, length: 0))
    expect(text.hasMarkedText(), "marked-text fixture enters native composition")
    press(50, .maskAlternate); await settle()
    expect(localActions == 0 && SharedSelectionActionsService.shared.triggers == 0,
           "actual callback preserves native composition instead of opening Actions")
    resetText()
    press(50, [.maskControl, .maskAlternate]); await settle(); press(0); await settle()
    if text.string != "à" || localActions != 0 {
        fputs("ACCENT DIAGNOSTIC text=\(String(reflecting: text.string)) localActions=\(localActions) globalActions=\(SharedSelectionActionsService.shared.triggers) marked=\(text.hasMarkedText())\n", stderr)
    }
    expect(text.string == "à" && localActions == 0, "actual production callback rewrites accent without opening Actions")
    for bits: UInt64 in [0x21, 0x2040] {
        resetText()
        key(50, CGEventFlags(rawValue: CGEventFlags.maskControl.rawValue | CGEventFlags.maskAlternate.rawValue | bits))
        key(50, [], down: false); await settle(); press(0); await settle()
        expect(text.string == "à", "device-specific flags and early modifier release preserve composition")
    }
    resetText(); press(50, [.maskControl, .maskAlternate]); await settle(); press(49); await settle()
    expect(text.string == "`", "accent followed by Space inserts literal grave")
    resetText()
    key(50, .maskAlternate); key(50, .maskAlternate, repeated: true); key(50, .maskAlternate, repeated: true); key(50, [], down: false)
    await settle(); press(0); await settle()
    expect(localActions == 1 && SharedSelectionActionsService.shared.triggers == 0,
           "local first press opens local Actions once; repeats never toggle or invoke global source")
    expect(text.string == "a" && !text.hasMarkedText(), "local Actions leaves no dead-key residue")
    resetText(); press(50); await settle()
    expect(text.string == "`", "plain backtick still inserts normally")
    }
    let previousLocalActions = localActions
    try! helper.run()
    await until("temporary helper becomes frontmost", { NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier })
    await until("background regular window is no longer key", { !window.isKeyWindow })
    expect(!(NSApp.keyWindow?.isVisible == true && NSApp.keyWindow?.isKeyWindow == true),
           "background regular window cannot steal global Actions route")
    key(50, .maskAlternate); key(50, .maskAlternate, repeated: true); key(50, [], down: false)
    await settle()
    expect(SharedSelectionActionsService.shared.triggers == 1 && localActions == previousLocalActions,
           "actual callback opens global selection action once when own regular window is background")
    expect(SharedSelectionActionsService.shared.sourcePIDs == [helper.processIdentifier],
           "global action captures the exact temporary source PID at keydown")
    panel.makeKeyAndOrderFront(nil); panel.makeFirstResponder(panelText)
    await until("nonactivating panel becomes key", { panel.isKeyWindow })
    expect(NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier,
           "nonactivating key panel keeps temporary source app frontmost")
    expect(NSApp.keyWindow === panel && NSApp.keyWindow?.isKeyWindow == true,
           "actual NSApp key-window predicate recognizes nonactivating panel ownership")
    key(50, .maskAlternate); key(50, .maskAlternate, repeated: true); key(50, [], down: false)
    await settle()
    expect(localActions == previousLocalActions + 1 && SharedSelectionActionsService.shared.triggers == 1,
           "nonactivating panel owns local action without duplicate global action")
    expect(NSPasteboard.general.changeCount == clipboardBefore, "shortcut probes never mutate clipboard")
    cleanup()
    let coverage = CommandLine.arguments.contains("--focus-only") ? "focus routing" : "composition and focus routing"
    print("PASS: \(checks) shared shortcut checks including native PID-tap \(coverage); layout=\(layoutID)")
    app.terminate(nil)
}
app.run()
'''

with tempfile.TemporaryDirectory(prefix="shared-action-shortcut-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(headless + handler + native)
    executable = folder / "checks"
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk")
    sdk_args = ["-sdk", str(sdk), "-Xfrontend", "-interface-compiler-version", "-Xfrontend", "6.3.2"] if sdk.exists() else []
    subprocess.run(["swiftc", *sdk_args, str(repo / "Sources/Vorssaint/Core/SharedActionShortcut.swift"), str(main), "-o", str(executable)], check=True, cwd=repo)
    env = dict(os.environ)
    env["CFFIXED_USER_HOME"] = str(folder / "home")
    Path(env["CFFIXED_USER_HOME"]).mkdir()
    arguments = [arg for arg in sys.argv[1:] if arg in ("--headless", "--focus-only")]
    subprocess.run([str(executable), *arguments], check=True, timeout=40, cwd=repo, env=env)
