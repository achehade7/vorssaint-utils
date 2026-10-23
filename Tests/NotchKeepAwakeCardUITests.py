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

enum AppLanguage: String { case enUS = "en-US", ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct Strings {
    let keepAwakeTitle = "Keep awake", keepAwakeEndsIn = "Ends in", keepAwakeUntilDisabled = "Active until you turn it off"
    let keepAwakeNormalRules = "The Mac follows its normal energy rules", keepAwakeUntilLabel = "Until", keepAwakeUntilStart = "Start"
    let clamshellTitle = "Clamshell mode", minutes15 = "15 minutes", minutes30 = "30 minutes", hour1 = "1 hour"
    let hours2 = "2 hours", hours4 = "4 hours", hours8 = "8 hours", indefinite = "Indefinite"
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
    let clamshellSetupInProgress = false, clamshellSetupFailed = false
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
    var clamshellCaption: String { "Clamshell controls" }
    var optionsDisclosure: some View { Text("Options").accessibilityIdentifier("awake.options") }
    CARD_BODY
    CARD_HELPERS
}
var checks = 0
func expect(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.15)) }
func children(_ element: AnyObject) -> [AnyObject] {
    [element] + (element.accessibilityChildren?() ?? []).flatMap { children($0 as AnyObject) }
}
func label(_ element: AnyObject) -> String {
    element.accessibilityLabel?() ?? element.accessibilityTitle?() ?? ""
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.perform(NSSelectorFromString("accessibilitySetValue:forAttribute:"), with: true, with: "AXEnhancedUserInterface")
let awake = KeepAwakeManager.shared
let clipCount = NSPasteboard.general.changeCount
func capture(_ name: String, width: CGFloat) {
    let host = NSHostingView(rootView: KeepAwakeCard().padding(12).frame(width: width).background(Color.black).preferredColorScheme(.dark))
    host.frame = NSRect(x: 0, y: 0, width: width, height: 400)
    let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = host; window.makeKeyAndOrderFront(nil)
    drain(); host.layoutSubtreeIfNeeded()
    let height = ceil(host.fittingSize.height)
    window.setContentSize(NSSize(width: width, height: height))
    drain(); host.layoutSubtreeIfNeeded()
    let elements = children(host)
    let names = elements.map(label)
    for title in ["15 minutes", "30 minutes", "1 hour", "2 hours", "4 hours", "8 hours", "Indefinite", "Until"] {
        expect(names.contains(title), "\(name) exposes \(title)")
    }
    expect(!names.contains("Options") && !names.contains("Clamshell mode"), "focused card omits all optional settings")
    expect(height < 230 && height > 90, "\(name) fits the compact card instead of a full settings page")
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/vorssaint-awake-card-\(name).png"))
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
    ("CARD_BODY", card, "var body: some View"),
]:
    code = code.replace(marker, declaration(source, declaration_marker))
code = code.replace("CARD_HELPERS", "\n".join(declaration(card, marker) for marker in [
    "private var statusLine:", "private func durationChip(", "private var untilChip:", "private var manualSession:",
    "static func countdownText(", "private func batteryNote(", "private var chipHint:",
    "private var activeBinding:", "private func optionRow(", "static func remainingText(",
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
