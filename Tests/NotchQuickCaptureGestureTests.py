#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native Command-drag gate using production pointer handlers and shortcut routing.

Opens isolated panels without screen capture, clipboard or personal vault access.
Pointer/key input targets this process through WindowServer. Editor autorepeat uses
queued AppKit events because WindowServer filters injected repeat events here.
"""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
tracker = repo / 'Sources/Vorssaint/Services/Notch/NotchQuickCaptureKeyTracker.swift'
selector = 'Sources/Vorssaint/Services/QuickTools/ScreenshotSelectionController.swift'
service = 'Sources/Vorssaint/Services/Notch/NotchQuickCaptureService.swift'
support = 'Sources/Vorssaint/Services/QuickTools/ScreenshotSupport.swift'
prefix = r'''
import AppKit
import CoreGraphics
final class CaptureKeyRouter {
    var actions: [String] = []
    func undoLastScreenshot() { actions.append("undo") }
    func pauseGroupCapture() { actions.append("pause") }
    func hide() { actions.append("hide") }
    func captureGroup() { actions.append("group") }
    func captureRegion() { actions.append("region") }
    func captureText() { actions.append("text") }
    func save() { actions.append("save") }
'''
prefix += declaration(service, '    static func isUndoScreenshot(')
prefix += declaration(service, '    func handleKey(') + '\n}\n'
prefix += 'enum ScreenshotSupport {\nstatic let clickDragThreshold: CGFloat = 4\n'
for item in ['    struct PickableWindow:', '    static func selectionRect(',
             '    static func clamp(', '    static func isClick(', '    static func window(']:
    prefix += declaration(support, item)
prefix += r'''
}
final class Panel: OverlayPanel {
    let screenFrame: CGRect
    var frozenImage: CGImage?
    override var canBecomeKey: Bool { true }
    init(frame: CGRect) {
        screenFrame = frame
        super.init(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel],
                   backing: .buffered, defer: false)
        isReleasedWhenClosed = false
        isOpaque = false; backgroundColor = .clear; hasShadow = false
        animationBehavior = .none
        level = NSWindow.Level(rawValue: Int(CGShieldingWindowLevel()))
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        hidesOnDeactivate = false; acceptsMouseMovedEvents = true; ignoresMouseEvents = false
    }
'''
for item in ['    override func setFrame(', '    private static func frameCoveringScreen(']:
    prefix += declaration(selector, item)
prefix += r'''
}
final class CaptureFixture {
    typealias ScreenshotOverlayPanel = Panel
    var onSelectionBegan: ((NSEvent.ModifierFlags) -> Void)?
    var currentPointerLocation: CGPoint?
    var isPickingColor = false, spaceIsDown = false, acceptsWindowClick = false
    let freezeOnCommand = true, includePointer = false, hideVorssaintWindows = true
    var finished = false, acquisitionPending = false, selectionInProgress = false
    var commandHeld = false, commandSnapshotPending = false, freeze = false
    var sourceGeneration = 0
    var pendingCommandRegion: (rect: CGRect, panel: Panel)?
    var frozenCaptureTimes: [CGDirectDisplayID: Date] = [:]
    var panels: [Panel] = []
    var captureExcludedWindowIDs: Set<CGWindowID> { Set(panels.map { CGWindowID($0.windowNumber) }) }
    var began: [NSEvent.ModifierFlags] = []
    var completed: [(flags: NSEvent.ModifierFlags, region: CGRect, capturedAt: Date?)] = []
    init() { onSelectionBegan = { [weak self] in self?.began.append($0) } }
    func setSelectionInProgress(_ value: Bool) {
        selectionInProgress = value
        if !value { setCommandFrozen(commandHeld) }
    }
    func applySource(frozenImages: [CGDirectDisplayID: CGImage]) {
        for panel in panels {
            panel.frozenImage = freeze ? frozenImages[1] : nil
            panel.contentView?.needsDisplay = true
        }
    }
    func confirmRegion(_ region: CGRect, on panel: Panel) {
        acquisitionPending = true
        if commandSnapshotPending { pendingCommandRegion = (region, panel); return }
        completed.append((began.last!, region, frozenCaptureTimes[1]))
        // The real owner replaces the completed selector. Retire its source
        // here while retaining this fixture's history for native assertions.
        acquisitionPending = false; selectionInProgress = false
        setCommandFrozen(false)
    }
    func confirmColor(at point: CGPoint, on panel: Panel) { preconditionFailure("unexpected color capture") }
    func confirmWindow(_ id: UInt32, frame: CGRect, on panel: Panel) { preconditionFailure("unexpected window capture") }
'''
for item in ['    fileprivate func commandModifiersChanged(', '    fileprivate func prepareSelection(',
             '    private func setCommandFrozen(']:
    prefix += declaration(selector, item)
prefix += r'''
}
enum ScreenshotCaptureEngine {
    struct Acquisition { let image: CGImage; let capturedAt: Date }
    static var pending: [CheckedContinuation<[CGDirectDisplayID: Acquisition], Never>] = []
    static func captureAllDisplaysWithTimestamps(includePointer: Bool, hideVorssaintWindows: Bool,
                                                 protectedWindowIDs: Set<CGWindowID>) async -> [CGDirectDisplayID: Acquisition] {
        await withCheckedContinuation { pending.append($0) }
    }
    static func complete(at date: Date) {
        let context = CGContext(data: nil, width: 300, height: 180, bitsPerComponent: 8, bytesPerRow: 0,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.setFillColor(NSColor.systemPurple.cgColor)
        context.fill(CGRect(x: 0, y: 0, width: 300, height: 180))
        pending.removeFirst().resume(returning: [1: Acquisition(image: context.makeImage()!, capturedAt: date)])
    }
}
final class DragView: NSView {
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    let controller: CaptureFixture?
    weak var panel: Panel?
    var acceptsPointerInput = true, pointerIsInside = false
    var hoverPoint = CGPoint.zero, lastDragPoint = CGPoint.zero
    var dragOrigin: CGPoint?
    var selection = CGRect.zero
    var windows: [ScreenshotSupport.PickableWindow] = []
    var unhandledRepeats = 0
    init(frame: CGRect, controller: CaptureFixture, panel: Panel) {
        self.controller = controller; self.panel = panel
        super.init(frame: frame)
    }
    required init?(coder: NSCoder) { nil }
    override func draw(_ dirtyRect: NSRect) {
        if let image = panel?.frozenImage { NSImage(cgImage: image, size: bounds.size).draw(in: bounds) }
    }
    override func keyDown(with event: NSEvent) {
        // Observe fallback without sounding a test beep.
        if event.isARepeat { unhandledRepeats += 1 }
    }
'''
for item in ['    override func mouseDown(', '    override func mouseDragged(', '    override func mouseUp(']:
    prefix += declaration(selector, item)
prefix += '\n}\n'

code = r'''
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
if (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool == true {
    fputs("ERROR: Native Command-drag checks require an unlocked Mac. No input was sent.\n", stderr)
    exit(1)
}
var checks = 0
func expect(_ value: @autoclosure () -> Bool, _ message: String) {
    checks += 1
    guard value() else { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
@MainActor func waitUntil(_ message: String, _ condition: () -> Bool) async {
    let until = Date().addingTimeInterval(5)
    while !condition(), Date() < until { try? await Task.sleep(nanoseconds: 10_000_000) }
    if !condition() { fputs("STATE actions=\(router.actions) key=\(app.keyWindow?.windowNumber ?? -1)\n", stderr) }
    expect(condition(), message)
}
func isOnScreen(_ window: NSWindow) -> Bool {
    let info = CGWindowListCopyWindowInfo(.optionIncludingWindow, CGWindowID(window.windowNumber)) as? [[String: Any]]
    return info?.first?[kCGWindowIsOnscreen as String] as? Bool == true
}
func modifiers(_ flags: CGEventFlags) {
    let event = CGEvent(source: nil)!
    event.type = .flagsChanged; event.flags = flags
    event.postToPid(getpid())
}
func key(_ code: UInt16, flags: CGEventFlags = [], repeated: Bool = false) {
    if repeated {
        let event = NSEvent.keyEvent(with: .keyDown, location: .zero,
            modifierFlags: NSEvent.ModifierFlags(rawValue: UInt(flags.rawValue)),
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: app.keyWindow?.windowNumber ?? 0, context: nil,
            characters: "t", charactersIgnoringModifiers: "t", isARepeat: true, keyCode: code)!
        app.postEvent(event, atStart: false)
        return
    }
    for down in [true, false] {
        let event = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: down)!
        event.flags = flags
        event.postToPid(getpid())
    }
}
func mouse(_ type: NSEvent.EventType, in window: NSWindow, flags: NSEvent.ModifierFlags, offset: CGFloat = 0) {
    let native = NSEvent.mouseEvent(with: type,
        location: NSPoint(x: 40 + offset, y: 40 + offset), modifierFlags: flags,
        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
        context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
    let event = native.cgEvent!
    event.flags = CGEventFlags(rawValue: UInt64(flags.rawValue))
    let top = NSScreen.screens[0].frame.maxY
    event.location = CGPoint(x: window.frame.minX + 40 + offset,
                             y: top - (window.frame.minY + 40 + offset))
    event.postToPid(getpid())
}
func drag(in window: NSWindow, start: NSEvent.ModifierFlags, afterStart: NSEvent.ModifierFlags? = nil) {
    mouse(.leftMouseDown, in: window, flags: start)
    let later = afterStart ?? start
    if later != start { modifiers(CGEventFlags(rawValue: UInt64(later.rawValue))) }
    mouse(.leftMouseDragged, in: window, flags: later, offset: 60)
    mouse(.leftMouseUp, in: window, flags: later, offset: 60)
}
let tracker = NotchQuickCaptureKeyTracker()
let router = CaptureKeyRouter()
let capture = CaptureFixture()
var selecting = true
var owned = Set<ObjectIdentifier>()
var repeatedKeyEvents = 0
tracker.start(ownsWindow: { $0.map { owned.contains(ObjectIdentifier($0)) } ?? false },
              handleEvent: { event in
    if event.isARepeat { repeatedKeyEvents += 1 }
    return router.handleKey(event, selecting: selecting)
})
let flagsMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
    if event.window.map({ owned.contains(ObjectIdentifier($0)) }) == true {
        capture.commandModifiersChanged(event.modifierFlags)
    }
    return event
}
func panel() -> Panel {
    let window = Panel(frame: NSRect(x: 140, y: 140, width: 300, height: 180))
    let view = DragView(frame: NSRect(x: 0, y: 0, width: 300, height: 180), controller: capture, panel: window)
    window.contentView = view
    capture.panels = [window]
    owned.insert(ObjectIdentifier(window))
    window.makeKeyAndOrderFront(nil); window.makeFirstResponder(view)
    return window
}
Task { @MainActor in
    app.activate(ignoringOtherApps: true)
    let first = panel()
    await waitUntil("first selector is key and on screen") { app.keyWindow === first && isOnScreen(first) }
    let initialFrame = first.frame

    modifiers(.maskCommand)
    await waitUntil("Command press requests fresh pixels before a drag") { ScreenshotCaptureEngine.pending.count == 1 }
    let firstAcquiredAt = Date(timeIntervalSince1970: 321)
    ScreenshotCaptureEngine.complete(at: firstAcquiredAt)
    await waitUntil("fresh frozen backdrop is visible before dragging") { first.frozenImage != nil && !capture.commandSnapshotPending }
    drag(in: first, start: .command, afterStart: [])
    await waitUntil("Command-drag reaches production region confirmation") { capture.completed.count == 1 }
    expect(capture.completed[0].flags.contains(.command),
           "immediate Command release after mouse-down preserves this region's OCR intent")
    expect(capture.completed[0].region.size == CGSize(width: 60, height: 60), "Command-drag draws the chosen region")
    expect(capture.completed[0].capturedAt == firstAcquiredAt, "frozen selection retains pre-drag acquisition time")
    expect(first.frame == initialFrame, "Command-drag does not move the selector overlay")

    drag(in: first, start: .command)
    await waitUntil("early mouse-up waits for the fresh snapshot") {
        capture.acquisitionPending && capture.completed.count == 1 && ScreenshotCaptureEngine.pending.count == 1
    }
    modifiers([])
    ScreenshotCaptureEngine.complete(at: Date(timeIntervalSince1970: 322))
    await waitUntil("second Command-drag completes") { capture.completed.count == 2 }
    first.orderOut(nil)
    let second = panel()
    await waitUntil("replacement selector is key and on screen") { app.keyWindow === second && isOnScreen(second) }
    drag(in: second, start: .command)
    await waitUntil("replacement snapshot is requested") { ScreenshotCaptureEngine.pending.count == 1 }
    ScreenshotCaptureEngine.complete(at: Date(timeIntervalSince1970: 323))
    await waitUntil("Command-drag completes in the replacement selector") { capture.completed.count == 3 }
    expect(capture.completed[1...2].allSatisfy { $0.flags.contains(.command) },
           "successive Command-drags each retain their own OCR intent")
    expect(second.frame == initialFrame, "replacement overlay stays fixed during Command-drag")

    modifiers([])
    modifiers(.maskCommand)
    await waitUntil("preview can begin without a drag") { ScreenshotCaptureEngine.pending.count == 1 }
    modifiers([])
    // A subsequent owned key is an ordering barrier for modifier release.
    key(17)
    await waitUntil("released Command cancels the unlatched preview") { !capture.freeze }
    ScreenshotCaptureEngine.complete(at: Date(timeIntervalSince1970: 324))
    drag(in: second, start: [])
    await waitUntil("normal screenshot drag completes after Command release") { capture.completed.count == 4 }
    expect(!capture.completed[3].flags.contains(.command), "Command release restores image mode on the next drag")
    drag(in: second, start: [], afterStart: .command)
    await waitUntil("late Command press drag completes") { capture.completed.count == 5 }
    expect(!capture.completed[4].flags.contains(.command), "Command pressed after mouse-down cannot change the active region")
    modifiers([])

    let view = second.contentView as! DragView
    view.acceptsPointerInput = false
    let beginsBeforeBlocked = capture.began.count
    mouse(.leftMouseDown, in: second, flags: .command)
    mouse(.leftMouseUp, in: second, flags: .command)
    // This routed key is an event-order barrier after the blocked mouse events.
    key(5, flags: .maskCommand)
    await waitUntil("selector Cmd-G keeps its pause shortcut") { router.actions == ["pause"] }
    expect(capture.began.count == beginsBeforeBlocked, "inactive selector input cannot replace latched intent")
    view.acceptsPointerInput = true

    selecting = false
    key(17, flags: .maskCommand)
    await waitUntil("Cmd-T keeps the text capture shortcut") { router.actions == ["pause", "text"] }
    let beforeRepeat = repeatedKeyEvents
    key(17, flags: .maskCommand, repeated: true)
    await waitUntil("modified action repeat stays unhandled") {
        repeatedKeyEvents == beforeRepeat + 1 && view.unhandledRepeats == 1
    }
    expect(router.actions == ["pause", "text"], "modified auto-repeat does not duplicate a capture action")

    let editor = NSTextView(frame: second.contentView!.bounds)
    editor.isRichText = false
    second.contentView = editor; second.makeFirstResponder(editor)
    key(17)
    await waitUntil("editor receives ordinary T") { editor.string == "t" }
    for _ in 0..<3 { key(17, repeated: true) }
    await waitUntil("editor retains ordinary T auto-repeat") { editor.string == "tttt" }
    expect(router.actions == ["pause", "text"], "ordinary T typing never starts a capture")
    tracker.stop()
    if let flagsMonitor { NSEvent.removeMonitor(flagsMonitor) }
    first.orderOut(nil); second.orderOut(nil)
    print("PASS: \(checks) native Command-drag/routing checks (production pointer handlers; PID-targeted input)")
    app.terminate(nil)
}
app.run()
'''
with tempfile.TemporaryDirectory(prefix='quick-capture-gesture-') as temporary:
    source = Path(temporary) / 'main.swift'
    source.write_text(prefix + code)
    binary = Path(temporary) / 'checks'
    subprocess.run(['xcrun', 'swiftc', '-target', 'arm64-apple-macosx14.0', '-sdk',
                    '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk', '-Xfrontend',
                    '-interface-compiler-version', '-Xfrontend', '6.3.2', str(tracker),
                    str(repo / 'Sources/Vorssaint/UI/OverlayPanel.swift'), str(source),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=45)
