#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Render production awake card body, chips and styles with an isolated session backend."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
panel = (repo / "Sources/Vorssaint/UI/MenuPanel/MenuPanelView.swift").read_text()
card = panel[panel.index("struct KeepAwakeCard:"):panel.index("/// Session durations shared")]


def declaration(source, marker):
    start = source.index(marker)
    end, depth = source.index("{", start) + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


code = r'''
import AppKit
import SwiftUI
import CoreGraphics
import ScreenCaptureKit

enum AppLanguage: String { case enUS = "en-US", ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct Strings {
    let keepAwakeTitle = "Keep awake", keepAwakeEndsIn = "Ends in", keepAwakeUntilDisabled = "Active until you turn it off"
    let keepAwakeNormalRules = "The Mac follows its normal energy rules", keepAwakeUntilLabel = "Until", keepAwakeUntilStart = "Start"
    let clamshellTitle = "Clamshell mode", minutes15 = "15 minutes", minutes30 = "30 minutes", hour1 = "1 hour"
    let hours2 = "2 hours", hours4 = "4 hours", hours8 = "8 hours", indefinite = "Indefinite"
    let configuring = "Configuring…", sudoersFailed = "Configuration failed"
    let clamshellOnCaption = "Sleep fully disabled. Mind the power"
    let clamshellNeedsSession = "Applied whenever “Keep awake” is active"
    let clamshellReady = "Ready. Toggles without a password"
    let clamshellNeedsPassword = "Will ask for the administrator password once"
}
final class L10n: ObservableObject { static let shared = L10n(); let s = Strings(); let language = AppLanguage.enUS }
final class KeepAwakeManager: ObservableObject {
    enum Trigger { case manual, automation }
    static let shared = KeepAwakeManager()
    @Published var isActive = false
    @Published var endDate: Date?
    @Published var sessionMinutes: Int?
    @Published var clamshellPreferred = false
    var sessionTrigger = Trigger.manual
    var activeAutomationConditions: [String] = []
    var clamshellSetupInProgress = false, clamshellSetupFailed = false
    var clamshellActive = false, passwordlessClamshell = false
    var blockedPercent: Int?
    func batteryProtectionPercent() -> Int? { blockedPercent }
    func extend(minutes: Int) { endDate = endDate?.addingTimeInterval(Double(minutes * 60)) }
    func toggle() { isActive = false; endDate = nil; sessionMinutes = nil }
    func activate(minutes: Int) { isActive = true; sessionMinutes = minutes; endDate = minutes == 0 ? nil : Date().addingTimeInterval(Double(minutes * 60)) }
    func activate(until date: Date) { isActive = true; sessionMinutes = nil; endDate = date }
    func startLastPick() { activate(minutes: 60) }
}
enum KeepAwakeAutomationSupport { static func resolvedUntilDate(picked: Date, now: Date) -> Date { picked > now ? picked : picked.addingTimeInterval(86400) } }
struct AutomationStrings { func activeStatus(for conditions: [String]) -> String { "Active while connected to power" } }
struct RawChoice { let rawValue: String }
enum Defaults {
    static func sanitizedDefaultDuration(_ value: Int) -> Int { value }
    static func sanitizedKeepAwakeIconTint(_ value: String) -> RawChoice { RawChoice(rawValue: value) }
    static func sanitizedKeepAwakeActiveIcon(_ value: String) -> RawChoice { RawChoice(rawValue: value) }
    static func sanitizedKeepAwakeMouseJiggleInterval(_ value: Int) -> Int { value }
}
enum DefaultsKey { static let notchLiquidGlassEnabled = "test-awake-glass" }
private struct NotchPresentationKey: EnvironmentKey { static let defaultValue = true }
private struct NotchGlassKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var notchPresentation: Bool { get { self[NotchPresentationKey.self] } set { self[NotchPresentationKey.self] = newValue } }
    var notchGlassSurface: Bool { get { self[NotchGlassKey.self] } set { self[NotchGlassKey.self] = newValue } }
}
enum PanelSurface {
    static func cardFill(for scheme: ColorScheme) -> Color { .gray.opacity(0.1) }
    static func border(for scheme: ColorScheme) -> Color { .gray.opacity(0.2) }
}
SECTION_TITLE
PANEL_CARD_MODIFIER
CONTROL_SURFACE
extension View { func panelCard() -> some View { modifier(PanelCardModifier(interactive: true)) } }
enum Section { case keepAwake }
struct PanelSection<Content: View>: View {
    let title: String
    let content: Content
    init(_ section: Section, title: String, collapsible: Bool, @ViewBuilder content: () -> Content) {
        self.title = title; self.content = content()
    }
    var body: some View { VStack(alignment: .leading, spacing: 8) { HStack { sectionTitle(title); Spacer() }; content } }
}
DURATION_PICKER
CHIP_STYLE
NATIVE_SWITCH
struct KeepAwakeCard: View {
    @ObservedObject var l10n = L10n.shared
    @ObservedObject var awake = KeepAwakeManager.shared
    @State var defaultDuration = 60
    @State var keepAwakeIconTint = "orange"
    @State var keepAwakeActiveIcon = "vorssaint"
    @State var keepAwakeMouseJiggleInterval = 5
    @State var untilDraft: Date?
    @State var selectedUntil = Date().addingTimeInterval(3600)
    var untilTime: Binding<Date> { $selectedUntil }
    var collapsible = false
    var showsOptions = false
    var automationStrings: AutomationStrings { AutomationStrings() }
    var optionsDisclosure: some View { Text("Options").accessibilityIdentifier("awake.options") }
    CARD_BODY
    CARD_HELPERS
}
var checks = 0
func expect(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
func drain() {
    let end = Date().addingTimeInterval(0.15)
    while Date() < end {
        if let event = NSApp.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01), inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.002))
    }
}
func children(_ element: AnyObject) -> [AnyObject] {
    [element] + (element.accessibilityChildren?() ?? []).flatMap { children($0 as AnyObject) }
}
func label(_ element: AnyObject) -> String {
    element.accessibilityLabel?() ?? element.accessibilityTitle?() ?? ""
}
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native awake rendering checks require an unlocked Mac.\n", stderr); exit(2)
}
func windowPixels(_ window: NSWindow) -> NSBitmapImageRep {
    var completed = false
    var result: CGImage?
    var failure: Error?
    if #available(macOS 14.4, *) {
        Task { @MainActor in
            do {
                let shareable = try await SCShareableContent.currentProcess
                guard let own = shareable.windows.first(where: { $0.windowID == CGWindowID(window.windowNumber) }) else {
                    throw NSError(domain: "OwnWindowCapture", code: 1, userInfo: [NSLocalizedDescriptionKey: "Own fixture window unavailable"])
                }
                let configuration = SCStreamConfiguration()
                configuration.width = Int(window.frame.width * window.backingScaleFactor)
                configuration.height = Int(window.frame.height * window.backingScaleFactor)
                configuration.showsCursor = false
                configuration.ignoreShadowsSingleWindow = true
                result = try await SCScreenshotManager.captureImage(contentFilter: SCContentFilter(desktopIndependentWindow: own), configuration: configuration)
            } catch { failure = error }
            completed = true
        }
        let deadline = Date().addingTimeInterval(10)
        while !completed && Date() < deadline { drain() }
        guard let result else { fatalError("Own-window capture failed: \(String(describing: failure))") }
        return NSBitmapImageRep(cgImage: result)
    }
    fatalError("Own-window capture requires macOS 14.4")
}
final class AwakePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    @objc func _hasActiveAppearanceIgnoringKeyFocus() -> Bool { true }
}
OVERLAY_SCROLL
struct CardContainer: View {
    let width: CGFloat
    @State var height: CGFloat = 240
    var body: some View {
        OverlayScrollView(measuredHeight: $height) {
            KeepAwakeCard().frame(width: width - 24)
                .environment(\.colorScheme, .dark)
                .environment(\.notchPresentation, true)
        }
        .frame(width: width - 24, height: height)
        .padding(12).background(Color.black)
    }
}
func nativeSwitches(_ view: NSView) -> [NSSwitch] {
    (view as? NSSwitch).map { [$0] } ?? view.subviews.flatMap(nativeSwitches)
}
func click(_ control: NSSwitch) {
    let point = control.convert(NSPoint(x: control.bounds.midX, y: control.bounds.midY), to: nil)
    for type: NSEvent.EventType in [.leftMouseDown, .leftMouseUp] {
        let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: control.window!.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
        NSApp.postEvent(event, atStart: false)
    }
    drain()
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.perform(NSSelectorFromString("accessibilitySetValue:forAttribute:"), with: true, with: "AXEnhancedUserInterface")
let awake = KeepAwakeManager.shared
let clipCount = NSPasteboard.general.changeCount
func capture(_ name: String, width: CGFloat) {
    let host = NSHostingView(rootView: CardContainer(width: width).preferredColorScheme(.dark).foregroundStyle(.white).tint(.white))
    host.frame = NSRect(x: 0, y: 0, width: width, height: 400)
    let window = AwakePanel(contentRect: NSRect(x: 150, y: 180, width: width, height: 400), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    window.isOpaque = false; window.backgroundColor = .clear
    window.appearance = NSAppearance(named: .darkAqua); window.hidesOnDeactivate = false
    host.wantsLayer = true
    let mask = CALayer(); mask.backgroundColor = NSColor.black.cgColor
    mask.frame = host.bounds; host.layer?.mask = mask
    window.contentView = host; window.makeKeyAndOrderFront(nil)
    app.activate(ignoringOtherApps: true)
    drain(); host.layoutSubtreeIfNeeded()
    let height = ceil(host.fittingSize.height)
    window.setContentSize(NSSize(width: width, height: height))
    mask.frame = host.bounds
    drain(); host.layoutSubtreeIfNeeded()
    let elements = children(host)
    let names = elements.map(label)
    for title in ["15 minutes", "30 minutes", "1 hour", "2 hours", "4 hours", "8 hours", "Indefinite", "Until"] {
        expect(names.contains(title), "\(name) exposes \(title)")
    }
    expect(!names.contains("Options") && names.contains("Clamshell mode"), "focused card keeps lid controls without the extra Options section")
    expect(height < 290 && height > 140, "\(name) fits the compact card instead of a full settings page")
    let switches = ["keepAwake.session", "keepAwake.clamshell"].compactMap { identifier in
        elements.first { $0.accessibilityIdentifier?() == identifier }
    }
    expect(switches.count == 2, "both awake and lid controls remain accessible switches")
    let bitmap = windowPixels(window)
    let controls = nativeSwitches(host)
    expect(controls.count == 2, "card uses native AppKit switches for session and lid")
    let scale = CGFloat(bitmap.pixelsWide) / window.frame.width
    for control in controls {
        let frame = control.convert(control.bounds, to: nil)
        let x0 = max(0, Int(frame.minX * scale)), x1 = min(bitmap.pixelsWide, Int(frame.maxX * scale))
        let y0 = max(0, Int((window.frame.height - frame.maxY) * scale)), y1 = min(bitmap.pixelsHigh, Int((window.frame.height - frame.minY) * scale))
        var lightPixels = 0
        if x0 < x1 && y0 < y1 {
            for y in y0..<y1 { for x in x0..<x1 {
                if let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB), min(c.redComponent, c.greenComponent, c.blueComponent) > 0.65 { lightPixels += 1 }
            } }
        }
        expect(lightPixels > 30, "\(name) switch thumb is visible in actual WindowServer pixels")
    }
    try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/vorssaint-awake-card-\(name).png"))
    if name == "off" {
        let session = controls.first { $0.accessibilityIdentifier() == "keepAwake.session" }!
        let lid = controls.first { $0.accessibilityIdentifier() == "keepAwake.clamshell" }!
        click(session)
        expect(awake.isActive && awake.sessionMinutes == 60, "session switch starts the last duration")
        click(session)
        expect(!awake.isActive, "session switch stops awake")
        click(lid)
        expect(awake.clamshellPreferred, "lid switch enables the existing clamshell preference")
        click(lid)
        expect(!awake.clamshellPreferred, "lid switch can turn the preference off")
    }
    print("\(name): \(Int(width)) × \(Int(height))")
    window.orderOut(nil)
}
capture("off", width: 700)
capture("off-small", width: 340)
awake.activate(minutes: 0)
capture("indefinite", width: 700)
capture("indefinite-small", width: 340)
awake.activate(minutes: 30)
capture("timed", width: 700)
capture("timed-small", width: 340)
awake.activate(until: Date().addingTimeInterval(3600))
capture("until-small", width: 340)
awake.toggle(); awake.blockedPercent = 15
capture("battery-small", width: 340)
expect(NSPasteboard.general.changeCount == clipCount, "card checks never touch the clipboard")
print("PASS: \(checks) production awake card checks; screenshots /tmp/vorssaint-awake-card-*.png")
'''
theme = (repo / "Sources/Vorssaint/UI/Theme.swift").read_text()
components = (repo / "Sources/Vorssaint/UI/Notch/NotchComponents.swift").read_text()
for marker, source, declaration_marker in [
    ("SECTION_TITLE", theme, "func sectionTitle("),
    ("PANEL_CARD_MODIFIER", theme, "private struct PanelCardModifier:"),
    ("CONTROL_SURFACE", components, "struct NotchControlSurface:"),
    ("DURATION_PICKER", panel, "enum DurationPicker"),
    ("CHIP_STYLE", panel, "struct KeepAwakeChipStyle:"),
    ("NATIVE_SWITCH", panel, "private struct KeepAwakeSwitch:"),
    ("CARD_BODY", card, "var body: some View"),
]:
    code = code.replace(marker, declaration(source, declaration_marker))
code = code.replace("OVERLAY_SCROLL", declaration(panel, "private struct OverlayScrollView<") + "\n" + declaration(panel, "private final class HeightReportingHostingView<"))
code = code.replace("CARD_HELPERS", "\n".join(declaration(card, marker) for marker in [
    "private var statusLine:", "private func durationChip(", "private var untilChip:", "private var manualSession:",
    "static func countdownText(", "private func batteryNote(", "private var chipHint:",
    "private var activeBinding:", "private var clamshellCaption:", "private func optionRow(", "static func remainingText(",
]))
with tempfile.TemporaryDirectory(prefix="awake-card-ui-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(code)
    executable = folder / "check"
    subprocess.run(["xcrun", "swiftc", "-target", "arm64-apple-macosx14.0", "-sdk",
                    "/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk", "-Xfrontend",
                    "-interface-compiler-version", "-Xfrontend", "6.3.2",
                    str(repo / "Sources/Vorssaint/UI/MenuPanel/KeepAwakeEndTimePicker.swift"), str(main), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=60)
