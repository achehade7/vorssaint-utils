#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native island cup routing; no power assertions or user preferences changed."""
from pathlib import Path
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


controls = "Sources/Vorssaint/UI/Notch/NotchControlsView.swift"
panel = "Sources/Vorssaint/UI/MenuPanel/MenuPanelView.swift"
swift = r'''
import AppKit
import SwiftUI
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checks += 1; if !condition() { fatalError(message) }
}
enum AppFeature { case keepAwake; static var available = true; var isAvailable: Bool { Self.available } }
enum PanelSectionID { case keepAwake, system; var isAvailable: Bool { AppFeature.available } }
enum MetricDetailKind { case system }
enum NotchModule { case controls }
enum PanelLayout { static var shown = false; static func isVisibleInPanel(_ id: PanelSectionID) -> Bool { shown } }
FOCUS_TYPES
final class NotchService {
    static let shared = NotchService()
    var opened = 0
    func open(_ module: NotchModule, appPanel: Bool) { if module == .controls && appPanel { opened += 1 } }
    OPEN_KEEP_AWAKE
}
final class KeepAwakeManager: ObservableObject {
    static let shared = KeepAwakeManager()
    @Published var isActive = false
    var toggles = 0
    func toggleIndefinitely() { toggles += 1; isActive.toggle() }
}
final class L10n: ObservableObject {
    static let shared = L10n(); let s = Strings()
    struct Strings { let keepAwakeTitle = "Keep awake" }
}
enum NotchLayout { static let shortcutHeight: CGFloat = 80 }
enum NotchNeonPalette { static let amber = Color.orange }
struct NotchButtonStyle: ButtonStyle {
    let cornerRadius: CGFloat
    func makeBody(configuration: Configuration) -> some View { configuration.label }
}
struct NotchRollingDigits: ViewModifier {
    let value: String, countsDown: Bool
    func body(content: Content) -> some View { content }
}
TILE
RIGHT_CLICK
AWAKE_BUTTON
struct Visibility {
    let panelFocus = MenuPanelFocus.shared
    let showKeepAwake = false, showBrightness = false, brightnessEnabled = false, showMixer = false,
        showSystem = false, showNetwork = false, showDisk = false, showPower = false,
        showFanControl = false, showUtilities = false, showControls = false, showToggles = false,
        showWallpaper = false
    VISIBILITY
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let attribute = "AXEnhancedUserInterface"
let setter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
let previous = app.perform(NSSelectorFromString("accessibilityAttributeValue:"), with: attribute)?.takeUnretainedValue()
app.perform(setter, with: true, with: attribute)
defer { app.perform(setter, with: previous, with: attribute) }
private let host = NSHostingView(rootView: NotchAwakeButton().background(Color.black).preferredColorScheme(.dark))
host.frame = NSRect(x: 0, y: 0, width: 92, height: 80)
let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = host; window.orderFrontRegardless()
RunLoop.main.run(until: Date().addingTimeInterval(0.1)); host.layoutSubtreeIfNeeded()
func press(_ element: AnyObject) -> Bool {
    if element.accessibilityIdentifier?() == "notch.controls.keepAwake" {
        return element.accessibilityPerformPress?() ?? false
    }
    for child in element.accessibilityChildren?() ?? [] { if press(child as AnyObject) { return true } }
    return false
}
func area(in view: NSView) -> NotchObsidianRightClick.Area? {
    if let view = view as? NotchObsidianRightClick.Area { return view }
    return view.subviews.lazy.compactMap { area(in: $0) }.first
}
let awake = KeepAwakeManager.shared
expect(press(host) && awake.isActive && awake.toggles == 1, "native cup action starts indefinite toggle")
expect(press(host) && !awake.isActive && awake.toggles == 2, "native cup action stops active session")
let listener = area(in: host)!
let inside = listener.convert(NSPoint(x: listener.bounds.midX, y: listener.bounds.midY), to: nil)
func click(_ type: NSEvent.EventType, at point: NSPoint, in target: NSWindow = window) -> NSEvent {
    NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: 1,
                      windowNumber: target.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
}
let visibility = Visibility()
expect(!visibility.isSectionVisible(.keepAwake), "hidden card stays hidden during normal presentation")
expect(listener.handle(click(.rightMouseDown, at: inside)), "secondary click reaches the actual cup background")
expect(NotchService.shared.opened == 1 && MenuPanelFocus.shared.request?.target == .section(.keepAwake),
       "secondary click opens the app panel focused on the duration card")
expect(!awake.isActive && awake.toggles == 2, "opening the duration card does not start a session")
expect(visibility.isSectionVisible(.keepAwake) && !PanelLayout.shown,
       "explicit request reveals a hidden card without changing saved visibility")
expect(!visibility.isSectionVisible(.system), "the request does not reveal other hidden cards")
expect(!listener.handle(click(.leftMouseDown, at: inside)), "right-click listener leaves primary clicks native")
expect(!listener.handle(click(.rightMouseDown, at: NSPoint(x: -50, y: -50))), "outside clicks are not consumed")
let other = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
expect(!listener.handle(click(.rightMouseDown, at: inside, in: other)), "other windows cannot activate the cup")
listener.isHidden = true
expect(!listener.handle(click(.rightMouseDown, at: inside)), "hidden cup cannot intercept a click")
listener.isHidden = false
awake.isActive = true
expect(listener.handle(click(.rightMouseDown, at: inside)) && awake.isActive && awake.toggles == 2,
       "opening the card does not stop an active session")
MenuPanelFocus.shared.showNormalPanel()
expect(!visibility.isSectionVisible(.keepAwake), "returning to the normal panel restores hidden layout")
AppFeature.available = false
NotchService.shared.openKeepAwake()
expect(NotchService.shared.opened == 2, "unavailable Keep Awake cannot open its card")
listener.stop(); window.orderOut(nil)
print("PASS: \(checks) native Keep Awake checks")
'''
swift = swift.replace("FOCUS_TYPES", "\n".join(declaration(panel, marker) for marker in [
    "struct MenuPanelFocusRequest:", "enum MenuPanelFocusTarget:", "final class MenuPanelFocus:",
]))
swift = swift.replace("OPEN_KEEP_AWAKE", declaration(
    "Sources/Vorssaint/Services/Notch/NotchService.swift", "func openKeepAwake()"))
swift = swift.replace("TILE", "\n".join(declaration(controls, marker) for marker in [
    "enum NotchTileAccent", "struct NotchActionTile:",
]))
swift = swift.replace("RIGHT_CLICK", declaration(
    "Sources/Vorssaint/UI/Notch/NotchQuickCaptureView.swift", "struct NotchObsidianRightClick:"))
swift = swift.replace("AWAKE_BUTTON", declaration(controls, "private struct NotchAwakeButton:"))
swift = swift.replace("VISIBILITY", declaration(panel, "private func isSectionVisible(").replace("private func", "func", 1))
with tempfile.TemporaryDirectory(prefix="notch-keep-awake-ui-") as temporary:
    source = Path(temporary) / "main.swift"
    source.write_text(swift)
    binary = Path(temporary) / "checks"
    subprocess.run(["xcrun", "swiftc", "-target", "arm64-apple-macosx14.0", "-sdk",
                    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk", "-Xfrontend",
                    "-interface-compiler-version", "-Xfrontend", "6.3.2", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
