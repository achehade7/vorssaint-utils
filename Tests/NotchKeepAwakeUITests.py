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
import CoreGraphics
var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checks += 1; if !condition() { fatalError(message) }
}
enum AppFeature { case keepAwake; static var available = true; var isAvailable: Bool { Self.available } }
enum PanelSectionID: CaseIterable { case keepAwake, brightness, mixer, system, network, disk, power, fanControl, utilities, controls, toggles, wallpaper; var isAvailable: Bool { AppFeature.available } }
enum MetricDetailKind { case system }
enum NotchModule { case controls }
enum PanelLayout { static var shown = false; static func isVisibleInPanel(_ id: PanelSectionID) -> Bool { shown } }
FOCUS_TYPES
final class NotchService {
    static let shared = NotchService()
    var opened = 0
    var showingAppPanel = false
    var expanded = true, showingSections = false
    var keepAwakeCardHeight: CGFloat?
    var refreshed = 0
    func refreshPresentation() { refreshed += 1 }
    AWAKE_HEIGHT
    func open(_ module: NotchModule, appPanel: Bool) { if module == .controls && appPanel { opened += 1; showingAppPanel = true } }
    var detailTitle: String { DETAIL_TITLE; return "Other" }
    OPEN_KEEP_AWAKE
    func activateQuickAction(_ action: QuickAction) {
        guard AppFeature.available else { return }
        QUICK_PRIMARY_HANDLER
    }
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
enum QuickAction { case keepAwake }
struct QuickCup: View {
    let service = NotchService.shared
    @ObservedObject var awake = KeepAwakeManager.shared
    let action = QuickAction.keepAwake
    var body: some View {
        Button { QUICK_PRIMARY_ACTION } label: {
            Image(systemName: awake.isActive ? "cup.and.saucer.fill" : "cup.and.saucer")
                .frame(width: 80, height: 80)
        }
        .buttonStyle(.plain)
        .background { QUICK_SECONDARY }
        .accessibilityIdentifier("notch.quickAccess.testCup")
    }
}
struct Visibility {
    let panelFocus = MenuPanelFocus.shared
    var notchSize: CGSize? = CGSize(width: 520, height: 260)
    KEEP_AWAKE_ONLY
    let showKeepAwake = false, showBrightness = false, brightnessEnabled = false, showMixer = false,
        showSystem = false, showNetwork = false, showDisk = false, showPower = false,
        showFanControl = false, showUtilities = false, showControls = false, showToggles = false,
        showWallpaper = false
    VISIBILITY
}

let session = CGSessionCopyCurrentDictionary() as? [String: Any]
guard session?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native Keep Awake clicks require an unlocked Mac. No input was sent.\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let attribute = "AXEnhancedUserInterface"
let setter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
let previous = app.perform(NSSelectorFromString("accessibilityAttributeValue:"), with: attribute)?.takeUnretainedValue()
app.perform(setter, with: true, with: attribute)
defer { app.perform(setter, with: previous, with: attribute) }
private let host = NSHostingView(rootView: HStack(spacing: 20) {
    NotchAwakeButton().frame(width: 92, height: 80)
    QuickCup().frame(width: 92, height: 80)
}.background(Color.black).preferredColorScheme(.dark))
host.frame = NSRect(x: 0, y: 0, width: 204, height: 80)
let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 204, height: 80), styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = host; window.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)
func drain() {
    let end = Date().addingTimeInterval(0.15)
    while Date() < end {
        if let event = app.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01), inMode: .default, dequeue: true) {
            app.sendEvent(event)
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.002))
    }
}
drain(); host.layoutSubtreeIfNeeded()
func press(_ element: AnyObject, identifier: String) -> Bool {
    if element.accessibilityIdentifier?() == identifier { return element.accessibilityPerformPress?() ?? false }
    for child in element.accessibilityChildren?() ?? [] {
        if press(child as AnyObject, identifier: identifier) { return true }
    }
    return false
}
func areas(in view: NSView) -> [NotchObsidianRightClick.Area] {
    (view as? NotchObsidianRightClick.Area).map { [$0] } ?? view.subviews.flatMap { areas(in: $0) }
}
let listeners = areas(in: host).sorted { $0.convert(.zero, to: nil).x < $1.convert(.zero, to: nil).x }
expect(listeners.count == 2 && listeners.allSatisfy { $0.bounds.width > 0 && $0.bounds.height > 0 },
       "both cup presentations install a nonempty native right-click area")
let controls = listeners[0], quick = listeners[1]
func click(_ type: NSEvent.EventType, at point: NSPoint, in target: NSWindow = window) -> NSEvent {
    NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                      windowNumber: target.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
}
func mouseClick(_ target: NSView, secondary: Bool) {
    let inside = target.convert(NSPoint(x: target.bounds.midX, y: target.bounds.midY), to: nil)
    for type: NSEvent.EventType in secondary ? [.rightMouseDown, .rightMouseUp] : [.leftMouseDown, .leftMouseUp] {
        // Only this test app receives the mouse events. In particular the
        // secondary action must pass through the production local monitor.
        app.postEvent(click(type, at: inside), atStart: false)
    }
    drain()
}
let awake = KeepAwakeManager.shared
var visibility = Visibility()
expect(!visibility.isSectionVisible(.keepAwake), "hidden card stays hidden during normal presentation")
PanelLayout.shown = true
expect(PanelSectionID.allCases.allSatisfy(visibility.isSectionVisible), "normal panel exposes every enabled section before the cup request")
mouseClick(quick, secondary: false)
expect(NotchService.shared.opened == 1 && MenuPanelFocus.shared.request?.target == .section(.keepAwake),
       "quickaccess primary mouse click opens the existing duration card")
expect(NotchService.shared.detailTitle == "Keep awake", "focused island header names only Keep awake")
NotchService.shared.updateKeepAwakeCardHeight(120.2)
expect(NotchService.shared.keepAwakeCardHeight == 121 && NotchService.shared.refreshed == 1, "focused card measures and refreshes its compact height")
NotchService.shared.updateKeepAwakeCardHeight(120.2)
NotchService.shared.updateKeepAwakeCardHeight(.nan)
NotchService.shared.updateKeepAwakeCardHeight(0)
expect(NotchService.shared.refreshed == 1, "unchanged or invalid heights cannot cause a resize loop")
expect(!awake.isActive && awake.toggles == 0, "opening the duration card does not start a session")
expect(PanelSectionID.allCases.filter(visibility.isSectionVisible) == [.keepAwake] && PanelLayout.shown,
       "coffee request shows ONLY awake even when every category is enabled")
PanelLayout.shown = false
expect(visibility.isSectionVisible(.keepAwake) && !PanelLayout.shown,
       "explicit request also reveals a hidden awake card without changing saved visibility")
mouseClick(quick, secondary: true)
expect(awake.isActive && awake.toggles == 1 && NotchService.shared.opened == 1,
       "quickaccess native right click starts indefinite awake without opening a card")
mouseClick(quick, secondary: true)
expect(!awake.isActive && awake.toggles == 2, "a second quickaccess right click stops awake")
mouseClick(controls, secondary: false)
expect(NotchService.shared.opened == 2,
       "Controls tile native primary mouse click opens the duration card")
expect(!awake.isActive && awake.toggles == 2, "Controls primary action does not change the session")
mouseClick(controls, secondary: true)
expect(awake.isActive && awake.toggles == 3, "Controls tile native right click starts indefinite awake")
expect(press(host, identifier: "notch.quickAccess.testCup") && NotchService.shared.opened == 3 && awake.isActive && awake.toggles == 3,
       "quickaccess primary action leaves an active session running")
mouseClick(controls, secondary: true)
expect(!awake.isActive && awake.toggles == 4, "Controls tile right click stops awake")
let inside = quick.convert(NSPoint(x: quick.bounds.midX, y: quick.bounds.midY), to: nil)
expect(!quick.handle(click(.leftMouseDown, at: inside)), "secondary listener leaves primary clicks native")
expect(!quick.handle(click(.rightMouseDown, at: NSPoint(x: -50, y: -50))), "outside clicks are not consumed")
let other = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
expect(!quick.handle(click(.rightMouseDown, at: inside, in: other)), "other windows cannot activate the cup")
quick.isHidden = true
expect(!quick.handle(click(.rightMouseDown, at: inside)), "hidden cup cannot intercept a click")
quick.isHidden = false
PanelLayout.shown = true
visibility.notchSize = nil
expect(PanelSectionID.allCases.allSatisfy(visibility.isSectionVisible), "standalone menu panel retains all sections for an ordinary focus request")
visibility.notchSize = CGSize(width: 520, height: 260)
MenuPanelFocus.shared.showNormalPanel()
expect(PanelSectionID.allCases.allSatisfy(visibility.isSectionVisible) && NotchService.shared.detailTitle == "Vorssaint", "normal app-panel route restores every enabled category and its normal title")
NotchService.shared.updateKeepAwakeCardHeight(400)
expect(NotchService.shared.keepAwakeCardHeight == 121, "general app panel is not resized by a stale awake measurement")
PanelLayout.shown = false
expect(!visibility.isSectionVisible(.keepAwake), "returning to the normal panel restores hidden layout")
AppFeature.available = false
NotchService.shared.openKeepAwake()
NotchService.shared.activateQuickAction(.keepAwake)
expect(NotchService.shared.opened == 3, "unavailable Keep Awake cannot open its card through either route")
for listener in listeners { listener.stop() }
window.orderOut(nil)

// Exercise the real focused container. Leaf content is a marker here; the
// unchanged production KeepAwakeCard is inspected in the installed app.
private struct NotchPresentationKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var notchPresentation: Bool { get { self[NotchPresentationKey.self] } set { self[NotchPresentationKey.self] = newValue } }
}
struct OverlayScrollView<Content: View>: View {
    @Binding var measuredHeight: CGFloat
    @ViewBuilder var content: () -> Content
    var body: some View { ScrollView { content() } }
}
struct KeepAwakeCard: View {
    let collapsible: Bool
    var showsOptions = true
    var body: some View { VStack {
        Text("Existing awake controls").frame(height: 140).accessibilityIdentifier("fixture.awakeControls")
        if showsOptions { Text("Options").accessibilityIdentifier("fixture.awakeOptions") }
    } }
}
struct FocusedContainer: View {
    let notchSize: CGSize? = CGSize(width: 520, height: 260)
    @ObservedObject var panelFocus = MenuPanelFocus.shared
    @State var navigableContentHeight: CGFloat = 0
    KEEP_AWAKE_ONLY
    EMBEDDED_PANEL
    private func embeddedNavigationPanel(size: CGSize) -> some View {
        VStack {
            Text("All section tabs").accessibilityIdentifier("fixture.navigation")
            Text("General app footer").accessibilityIdentifier("fixture.footer")
        }.frame(width: size.width, height: size.height)
    }
    var body: some View { embeddedPanel(size: notchSize!) }
}
func identifiers(_ element: AnyObject) -> [String] {
    let current = (element.accessibilityIdentifier?() ?? "").isEmpty ? [] : [element.accessibilityIdentifier?() ?? ""]
    return current + (element.accessibilityChildren?() ?? []).flatMap { identifiers($0 as AnyObject) }
}
AppFeature.available = true
PanelLayout.shown = true
MenuPanelFocus.shared.focus(.keepAwake)
let focusedHost = NSHostingView(rootView: FocusedContainer())
let focusedWindow = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 520, height: 260), styleMask: [.titled], backing: .buffered, defer: false)
focusedWindow.contentView = focusedHost; focusedWindow.makeKeyAndOrderFront(nil)
drain()
let focusedIDs = identifiers(focusedHost)
expect(focusedIDs.contains("notch.keepAwake.card") && !focusedIDs.contains("fixture.navigation") && !focusedIDs.contains("fixture.footer") && !focusedIDs.contains("fixture.awakeOptions"),
       "production embedded awake container has no global category toolbar, app footer or optional settings")
MenuPanelFocus.shared.showNormalPanel()
drain()
let normalIDs = identifiers(focusedHost)
expect(normalIDs.contains("fixture.navigation") && normalIDs.contains("fixture.footer") && !normalIDs.contains("notch.keepAwake.card"),
       "normal app panel still uses its ordinary navigation and footer")
focusedWindow.orderOut(nil)

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
quick_source = (repo / "Sources/Vorssaint/UI/Notch/NotchQuickAccessView.swift").read_text()
quick_handler = declaration("Sources/Vorssaint/Services/Notch/NotchService.swift", "func activateQuickAction(")
swift = swift.replace("QUICK_PRIMARY_HANDLER", next(line.split("case .keepAwake:", 1)[1].strip()
    for line in quick_handler.splitlines() if "case .keepAwake:" in line))
swift = swift.replace("QUICK_PRIMARY_ACTION", next(line.strip() for line in quick_source.splitlines()
    if "service.activateQuickAction(action)" in line))
secondary_start = quick_source.index("else if action == .control(.keepAwake), motion.interactive {")
swift = swift.replace("QUICK_SECONDARY", quick_source[secondary_start:].splitlines()[1].strip())
swift = swift.replace("VISIBILITY", declaration(panel, "private func isSectionVisible(").replace("private func", "func", 1))
swift = swift.replace("KEEP_AWAKE_ONLY", declaration(panel, "private var keepAwakeOnly:").replace("private var", "var", 1))
swift = swift.replace("EMBEDDED_PANEL", declaration(panel, "private func embeddedPanel("))
swift = swift.replace("AWAKE_HEIGHT", declaration("Sources/Vorssaint/Services/Notch/NotchService.swift", "func updateKeepAwakeCardHeight("))
detail = declaration("Sources/Vorssaint/Services/Notch/NotchService.swift", "var detailTitle:")
start = detail.index("if showingAppPanel {")
end, depth = detail.index("{", start) + 1, 1
while depth:
    depth += (detail[end] == "{") - (detail[end] == "}")
    end += 1
swift = swift.replace("DETAIL_TITLE", detail[start:end])
with tempfile.TemporaryDirectory(prefix="notch-keep-awake-ui-") as temporary:
    source = Path(temporary) / "main.swift"
    source.write_text(swift)
    binary = Path(temporary) / "checks"
    subprocess.run(["xcrun", "swiftc", "-target", "arm64-apple-macosx14.0", "-sdk",
                    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk", "-Xfrontend",
                    "-interface-compiler-version", "-Xfrontend", "6.3.2", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
