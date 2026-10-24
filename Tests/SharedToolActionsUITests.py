#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native shared action/OCR windows with isolated destinations, images and clipboard."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
import SwiftUI
import Carbon.HIToolbox
import ObjectiveC
enum ShortcutCapture { static var isCapturing = false }
struct GlobalShortcut: Equatable {
    let keyCode: Int64
    let modifiers: NSEvent.ModifierFlags
    var carbonKeyCode: UInt32 { UInt32(keyCode) }
    var carbonModifiers: UInt32 { precondition(modifiers == .command); return UInt32(cmdKey) }
}
enum SystemShortcutTakeover {
    static var claims = Set<String>()
    static func claim(_ key: String, shortcut: GlobalShortcut) { claims.insert(key) }
    static func release(_ key: String) { claims.remove(key) }
}
extension NSScreen {
    var displayID: CGDirectDisplayID { deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID ?? 0 }
}
enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n {
    static let shared = Self()
    let language = AppLanguage.enUS
    struct Strings { let ocrCopied = "Copied", ocrNoText = "No text found" }
    let s = Strings()
}
enum FeatureStrings {
    struct Clipboard { let copy = "Copy" }
    static func clipboard(_ language: AppLanguage) -> Clipboard { .init() }
    struct CommandBar { let openInBrowser = "Open in browser" }
    static func commandBar(_ language: AppLanguage) -> CommandBar { .init() }
}
enum AppFeature: CaseIterable {
    case clipboardHistory, textSnippets, screenOCR, screenshot
    static var available = Set(allCases)
    var isAvailable: Bool { Self.available.contains(self) }
}
struct ClipboardHistoryEntry {
    enum Kind { case text, image, files }
    var id = UUID()
    var text: String
    var kind = Kind.text
    var imageFile: String? = nil
    var preview: String { text }
}
final class ClipboardHistoryService {
    static let shared = ClipboardHistoryService()
    var entries: [ClipboardHistoryEntry] = []
}
enum ClipboardImageStore {
    static let lock = NSLock()
    static var data: [String: Data] = [:], reads: [String] = [], gate: DispatchSemaphore?
    static func imageData(named name: String) -> Data? {
        lock.lock(); reads.append(name); let hold = gate, result = data[name]; lock.unlock()
        hold?.wait()
        return result
    }
    static func readCount() -> Int { lock.lock(); defer { lock.unlock() }; return reads.count }
}
final class PayloadInspectorService {
    static let shared = PayloadInspectorService()
    var received: [String] = []
    func receive(_ text: String) { received.append(text) }
}
final class ClipboardDiffService {
    static let shared = ClipboardDiffService()
    var received: [(String, Bool)] = []
    func receive(_ text: String, asBefore: Bool, name: String?) { received.append((text, asBefore)) }
}
final class SnippetLibraryService {
    static let shared = SnippetLibraryService()
    var received: [String] = []
    func saveCapturedText(_ text: String) { received.append(text) }
}
final class ScreenshotService {
    static let shared = ScreenshotService()
    var images: [CGImage] = []
    func annotate(_ image: CGImage) { images.append(image) }
}
final class ScreenCompareService {
    static let shared = ScreenCompareService()
    var received: [(CGImage, Bool)] = []
    func receive(_ image: CGImage, asBefore: Bool, name: String?) { received.append((image, asBefore)) }
}
enum ScreenTextService {
    static var completions: [(Result<String, Error>) -> Void] = []
    static func recognizeCaptureText(_ image: CGImage, completion: @escaping (Result<String, Error>) -> Void) {
        completions.append(completion)
    }
}
enum NotchNeonPalette { static let purple = Color.purple }
final class NotchService {
    static let shared = NotchService()
    var presentationWindow: NSPanel?
    var acceptsSystemFeedback = true, expanded = false, routes = true
    var captureControls: Int?
    var captureID: UUID?, content: AnyView?, closeHandler: (() -> Void)?
    var tookFocus = false
    func presentCapture(id: UUID, content: AnyView, height: CGFloat, takeFocus: Bool, closeOnCollapse: Bool,
                        fallback: @escaping () -> Void, close: @escaping () -> Void, hover: @escaping (Bool) -> Void) -> Bool {
        guard routes, let panel = presentationWindow else { return false }
        captureID = id; self.content = content; closeHandler = close; expanded = true; tookFocus = takeFocus
        panel.setContentSize(NSSize(width: 600, height: height))
        // Match NotchView.page: captures sit in a vertical scroll view, which
        // proposes no height. A bare hosting window masks collapsed editors.
        panel.contentView = NSHostingView(rootView: ScrollView {
            content.frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.bottom, 4).contentShape(Rectangle())
        })
        if takeFocus { panel.makeKeyAndOrderFront(nil) } else { panel.orderFrontRegardless() }
        return true
    }
    func isCaptureVisible(id: UUID) -> Bool { captureID == id && expanded && acceptsSystemFeedback }
    func removeCapture(id: UUID) {
        guard captureID == id else { return }
        captureID = nil; content = nil; closeHandler = nil; expanded = false
        // NotchService.collapse explicitly resigns its nonactivating panel.
        presentationWindow?.resignKey()
        presentationWindow?.contentView = nil
        presentationWindow?.orderOut(nil)
    }
}

struct CommandBarEntry {
    enum Icon { case symbol(String) }
    let id: String
    var title = "", subtitle = "", icon = Icon.symbol("link"), countsUsage = false
    var run: (Int?) -> Void = { _ in }
    var isAnswer = false
}
enum DefaultsKey { static let commandBarLinks = "fixtureLinks" }
enum CommandBarSearch { static func normalized(_ text: String) -> String { text.lowercased() } }
enum CommandBarSource { case links; var idPrefix: String? { "link." } }
enum TestBrowser {
    static var urls: [URL] = []
    static func open(_ url: URL) { urls.append(url) }
}
enum CommandBarTicketSearch {
    // TICKET_METHODS
}
// JSON_FORMATTER
final class Bar {
    enum Mode: Equatable { case search, actions(entryID: String) }
    enum Presentation { case floating, island }
    var mode = Mode.search, presentation = Presentation.floating
    var query = "original query", savedQuery = "", actionIndex = 9, layouts = 0
    var selectedEntry: CommandBarEntry?, entriesByID: [String: CommandBarEntry] = [:]
    var panel: NSPanel?
    let contentActionsOwner = UUID()
    func actions(for entry: CommandBarEntry) -> [Int] { [1] }
    func refreshPanelLayout() { layouts += 1 }
    // BAR_METHODS
}
var checks = 0
func check(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
func wait(_ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    check(condition(), "asynchronous operation finished")
}
func drain() { RunLoop.main.run(until: Date().addingTimeInterval(0.12)) }
func views(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(views) }
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native shared action checks need an unlocked Mac.\n", stderr); exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let previewKeyTag: Int64 = 0x564F4352
let helperKeysURL = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent().appendingPathComponent("focus-keys")
if CommandLine.arguments.contains("--focus-helper") {
    let helperWindow = NSWindow(contentRect: NSRect(x: 200, y: 200, width: 360, height: 100),
                                styleMask: [.titled], backing: .buffered, defer: false)
    helperWindow.title = "Text tools focus fixture"
    helperWindow.contentView = NSTextField(labelWithString: "Isolated focus test")
    var received = ""
    try! received.write(to: helperKeysURL, atomically: true, encoding: .utf8)
    let monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
        guard event.cgEvent?.getIntegerValueField(.eventSourceUserData) == previewKeyTag,
              event.modifierFlags.intersection([.command, .option, .control, .shift]) == .command,
              let letter = event.charactersIgnoringModifiers, ["e", "v"].contains(letter) else { return event }
        received += letter
        try! received.write(to: helperKeysURL, atomically: true, encoding: .utf8)
        return nil
    }
    defer { if let monitor { NSEvent.removeMonitor(monitor) } }
    helperWindow.makeKeyAndOrderFront(nil); app.activate(ignoringOtherApps: true)
    DispatchQueue.main.asyncAfter(deadline: .now() + 30) { app.terminate(nil) }
    app.run(); exit(0)
}
let axGetter = NSSelectorFromString("accessibilityAttributeValue:")
let axSetter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
let previousAX = app.perform(axGetter, with: "AXEnhancedUserInterface")?.takeUnretainedValue()
app.perform(axSetter, with: true, with: "AXEnhancedUserInterface")
defer { app.perform(axSetter, with: previousAX, with: "AXEnhancedUserInterface") }
let editMenu = NSMenu(title: "Edit")
editMenu.addItem(NSMenuItem(title: "Undo", action: Selector(("undo:")), keyEquivalent: "z"))
let editRoot = NSMenuItem(); editRoot.submenu = editMenu
app.mainMenu = NSMenu(); app.mainMenu!.addItem(editRoot)
let actualClipboard = NSPasteboard.general
let actualChangeCount = actualClipboard.changeCount
final class TestPasteboard: NSObject {
    static let board = NSPasteboard.withUniqueName()
    @objc class func replacementGeneral() -> NSPasteboard { board }
}
let originalMethod = class_getClassMethod(NSPasteboard.self, NSSelectorFromString("generalPasteboard"))!
let replacementMethod = class_getClassMethod(TestPasteboard.self, #selector(TestPasteboard.replacementGeneral))!
method_exchangeImplementations(originalMethod, replacementMethod)
defer { method_exchangeImplementations(originalMethod, replacementMethod); TestPasteboard.board.releaseGlobally() }
TestPasteboard.board.setString("existing clipboard", forType: .string)
let fixtureChangeCount = TestPasteboard.board.changeCount
let jiraLink = CommandBarLink(name: "j", kind: .link, destination: "https://example.atlassian.net/browse/{query}")
func configureJira(_ links: [CommandBarLink]) {
    UserDefaults.standard.set(CommandBarLinks.encode(links), forKey: DefaultsKey.commandBarLinks)
}
configureJira([jiraLink])
let parent = NSPanel(contentRect: NSRect(x: 180, y: 180, width: 680, height: 480),
                     styleMask: [.titled, .closable, .nonactivatingPanel], backing: .buffered, defer: false)
parent.title = "Shared actions fixture"; parent.isReleasedWhenClosed = false
let parentField = NSTextField(frame: NSRect(x: 20, y: 30, width: 300, height: 30))
parentField.stringValue = "unchanged search"
parent.contentView!.addSubview(parentField)
parent.makeKeyAndOrderFront(nil); parent.makeFirstResponder(parentField)
let owner = UUID()
func menu() -> NSWindow? { app.windows.first { $0.isVisible && $0.title == SharedToolActionStrings.actions } }
func actionButtons(_ window: NSWindow) -> [NSButton] {
    let titles = Set(SharedToolActions.Action.allCases.map(\.title))
    return views(window.contentView!).compactMap { $0 as? NSButton }.filter { titles.contains($0.title) }.sorted { $0.tag < $1.tag }
}
func key(_ window: NSWindow, code: Int, characters: String = "", modifiers: NSEvent.ModifierFlags = [], repeatPress: Bool = false,
         accentTagged: Bool = false) {
    var event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: modifiers,
        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil,
        characters: characters, charactersIgnoringModifiers: characters, isARepeat: repeatPress, keyCode: UInt16(code))!
    if accentTagged {
        let quartz = event.cgEvent!
        let source = CGEventSource(event: quartz)!
        source.userData = SharedActionShortcut.accentEventTag
        quartz.setSource(source)
        event = NSEvent(cgEvent: quartz)!
        check(!SharedActionShortcut.matches(event) && event.window === window, "tagged accent remains scoped to its window and bypasses Actions matching")
    }
    app.sendEvent(event); drain()
}
func open(_ content: SharedToolActions.Content) -> NSWindow {
    SharedToolActions.present(content: content, title: "Selected fixture", from: parent, owner: owner)
    wait { menu() != nil }; return menu()!
}
func click(_ window: NSWindow, title: String) { actionButtons(window).first { $0.title == title }!.performClick(nil); drain() }
func destinationCalls() -> Int {
    PayloadInspectorService.shared.received.count + ClipboardDiffService.shared.received.count
        + SnippetLibraryService.shared.received.count + ScreenshotService.shared.images.count
        + ScreenCompareService.shared.received.count + ScreenTextService.completions.count + TestBrowser.urls.count
}
func image(_ width: Int) -> CGImage {
    let context = CGContext(data: nil, width: width, height: 5, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.setFillColor(NSColor.systemPurple.cgColor); context.fill(CGRect(x: 0, y: 0, width: width, height: 5))
    return context.makeImage()!
}
func capture(_ window: NSWindow, _ path: String) {
    let view = window.contentView!
    view.layoutSubtreeIfNeeded(); window.displayIfNeeded()
    let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: bitmap)
    try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
}
func verifyMenuLayout(_ window: NSWindow) {
    let content = window.contentView!
    content.layoutSubtreeIfNeeded()
    let actions = actionButtons(window)
    let frames = actions.map { $0.convert($0.bounds, to: content) }
    check(zip(frames, frames.dropFirst()).allSatisfy {
        abs($0.minY - $1.minY) < 1 && $0.maxX < $1.minX
    }, "all actions share a single ordered horizontal row: \(frames)")
    check(actions.allSatisfy { $0.image != nil && $0.imagePosition == .imageOnly },
          "every action has a valid symbol and displays only its icon")
    check(actions.allSatisfy { $0.accessibilityLabel() == $0.title && $0.toolTip?.contains($0.title) == true },
          "icon-only buttons retain accessible names and discoverable tooltips")
    check(frames.allSatisfy { content.bounds.contains($0) && $0.minX >= 6
          && content.bounds.maxX - $0.maxX >= 6 && $0.width == 32 && $0.height == 32 },
          "icons have equal usable targets and even outer padding")
    check(content.bounds.width <= 226 && content.bounds.height == 40,
          "menu is a compact forty-point-high icon strip")
    check(views(content).compactMap { $0 as? NSTextField }.allSatisfy(\.isHidden),
          "ready menu has no visible heading, source text or labels")
    check(!views(content).contains { $0 is NSSearchField || $0 is NSTextView
          || ($0 as? NSTextField)?.isEditable == true }, "menu contains no search field or editable text control")
    check(window.firstResponder === window, "compact menu routes keyboard commands without a text field editor")
    check(!views(content).compactMap { $0 as? NSTextField }.contains {
        !$0.isHidden && ($0.stringValue.contains("↑") || $0.stringValue.contains("↩") || $0.stringValue == "esc")
    }, "menu omits the arrow and Escape shortcut footer")
}

var entry = ClipboardHistoryEntry(text: "original selected payload")
SharedToolActions.present(entry: entry, from: parent, owner: owner)
wait { menu() != nil }
entry.text = "later source mutation"
let first = menu()!
check(SharedToolActions.owns(window: first, owner: owner), "menu belongs to the source owner")
check(actionButtons(first).map(\.title) == [SnippetCaptureStrings.localized(.enUS).save,
      SharedToolActionStrings.inspect, TextTransformStrings.title, SharedToolActionStrings.before, SharedToolActionStrings.after],
      "text actions put Save snippet first, Inspect second, then Text tools and comparison sides")
verifyMenuLayout(first)
key(first, code: kVK_Return, characters: "\r")
check(SnippetLibraryService.shared.received.last == "original selected payload" && menu() == nil,
      "Return defaults to Save snippet using the original selected snapshot")
let comparison = open(.text("comparison selected payload"))
key(comparison, code: kVK_DownArrow)
key(comparison, code: kVK_DownArrow)
key(comparison, code: kVK_DownArrow)
key(comparison, code: kVK_Return, characters: "\r")
check(ClipboardDiffService.shared.received.last?.0 == "comparison selected payload"
      && ClipboardDiffService.shared.received.last?.1 == true && menu() == nil,
      "three Down presses and Return choose Left after text tools")
let rightComparison = open(.text("right selected payload"))
key(rightComparison, code: kVK_DownArrow)
key(rightComparison, code: kVK_DownArrow)
key(rightComparison, code: kVK_DownArrow)
key(rightComparison, code: kVK_RightArrow)
key(rightComparison, code: kVK_Return, characters: "\r")
check(ClipboardDiffService.shared.received.last?.0 == "right selected payload"
      && ClipboardDiffService.shared.received.last?.1 == false,
      "Right moves to the right destination in the split comparison row")
let leftComparison = open(.text("left selected payload"))
key(leftComparison, code: kVK_UpArrow)
key(leftComparison, code: kVK_LeftArrow)
key(leftComparison, code: kVK_Return, characters: "\r")
check(ClipboardDiffService.shared.received.last?.0 == "left selected payload"
      && ClipboardDiffService.shared.received.last?.1 == true,
      "Up wraps to the right destination and Left moves back to the left")
for (name, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
    parent.appearance = NSAppearance(named: appearance)
    SharedToolActions.present(content: .text("Selected text SAP-531"), title: "Obsidian", from: parent, owner: owner)
    wait { menu() != nil }
    let screenshotMenu = menu()!
    verifyMenuLayout(screenshotMenu)
    capture(screenshotMenu, "/tmp/shared-actions-menu-\(name).png")
    SharedToolActions.cancel(owner: owner)
}
parent.appearance = nil
let inspected = open(.text("inspect target"))
key(inspected, code: kVK_DownArrow)
key(inspected, code: kVK_Return, characters: "\r")
check(PayloadInspectorService.shared.received.last == "inspect target", "Down and Return invoke the second action's payload inspector")

// Plain letters invoke the offered action using its original selected snapshot.
let letterActions = [("s", kVK_ANSI_S), ("l", kVK_ANSI_L), ("r", kVK_ANSI_R),
                     ("j", kVK_ANSI_J), ("i", kVK_ANSI_I)]
for (letter, code) in letterActions {
    let snapshot = "  exact \(letter) selection\r\nsecond line  " + (letter == "j" ? "sap-531" : "")
    var source = ClipboardHistoryEntry(text: snapshot)
    SharedToolActions.present(entry: source, from: parent, owner: owner)
    wait { menu() != nil }
    source.text = "later source edit"
    let calls = destinationCalls()
    key(menu()!, code: code, characters: letter)
    check(menu() == nil && destinationCalls() == calls + 1,
          "\(letter) closes the menu and invokes exactly one action")
    switch letter {
    case "s": check(SnippetLibraryService.shared.received.last == snapshot, "S saves exact selected text")
    case "l", "r":
        check(ClipboardDiffService.shared.received.last?.0 == snapshot
              && ClipboardDiffService.shared.received.last?.1 == (letter == "l"),
              "\(letter) routes exact selected text to the requested comparison side")
    case "j": check(TestBrowser.urls.last?.absoluteString == "https://example.atlassian.net/browse/SAP-531",
                    "J opens only the extracted key at the configured Jira destination")
    default: check(PayloadInspectorService.shared.received.last == snapshot, "I inspects exact selected text")
    }
}
// Jira uses the captured text and saved destination; an absent or ambiguous key never opens anything.
for text in ["no ticket here", "SAP-0", "SAP-531 OPS-42"] {
    let unavailable = open(.text(text))
    let calls = destinationCalls()
    check(!actionButtons(unavailable).contains { $0.title == "Jira" }, "Jira is absent without one distinct valid ticket")
    key(unavailable, code: kVK_ANSI_J, characters: "j")
    check(menu() === unavailable && destinationCalls() == calls, "J cannot fall through to Inspect or another action")
    SharedToolActions.cancel(owner: owner)
}
let jiraMenu = open(.text("Private context sap-531; https://untrusted.example/browse/SAP-531"))
check(actionButtons(jiraMenu).map(\.title) == [SnippetCaptureStrings.localized(.enUS).save,
      SharedToolActionStrings.inspect, TextTransformStrings.title, "Jira", SharedToolActionStrings.before, SharedToolActionStrings.after],
      "Jira follows Snippet, Inspect and Text tools, before the two comparison icons")
check(actionButtons(jiraMenu).first { $0.title == "Jira" }?.toolTip == "Jira · J"
      && actionButtons(jiraMenu).first { $0.title == SharedToolActionStrings.inspect }?.toolTip?.hasSuffix(" · I") == true,
      "tooltips advertise the distinct Jira and Inspect shortcuts")
let jiraCount = TestBrowser.urls.count
click(jiraMenu, title: "Jira")
check(TestBrowser.urls.count == jiraCount + 1
      && TestBrowser.urls.last?.absoluteString == "https://example.atlassian.net/browse/SAP-531",
      "click opens one deduplicated ticket using the saved site, without surrounding text")
for links in [[], [CommandBarLink(name: "j", kind: .link, destination: "file:///tmp/{query}")]] {
    configureJira(links)
    let unavailable = open(.text("SAP-531"))
    check(!actionButtons(unavailable).contains { $0.title == "Jira" }, "missing or non-web Jira configuration offers no action")
    SharedToolActions.cancel(owner: owner)
}
configureJira([jiraLink])
let removedJira = open(.text("SAP-531"))
configureJira([])
let beforeRemovedJira = TestBrowser.urls.count
key(removedJira, code: kVK_ANSI_J, characters: "j")
check(TestBrowser.urls.count == beforeRemovedJira, "a removed Jira destination is rechecked before dispatch")
configureJira([jiraLink])
let arrowJira = open(.text("SAP-531"))
key(arrowJira, code: kVK_RightArrow); key(arrowJira, code: kVK_RightArrow)
key(arrowJira, code: kVK_RightArrow)
key(arrowJira, code: kVK_Return, characters: "\r")
check(TestBrowser.urls.count == beforeRemovedJira + 1, "horizontal arrows navigate all icons to Jira")

let layoutCharacter = open(.text("keyboard-layout character"))
key(layoutCharacter, code: kVK_ANSI_X, characters: "s")
check(SnippetLibraryService.shared.received.last == "keyboard-layout character" && menu() == nil,
      "letter shortcuts follow the typed character rather than a physical US key position")
let capsCharacter = open(.text("caps-lock selection"))
key(capsCharacter, code: kVK_ANSI_S, characters: "S", modifiers: .capsLock)
check(SnippetLibraryService.shared.received.last == "caps-lock selection" && menu() == nil,
      "Caps Lock preserves plain-letter shortcuts")

let scopedLetters = open(.text("scoped shortcuts SAP-531"))
let callsBeforeScope = destinationCalls()
let foreign = NSPanel(contentRect: .zero, styleMask: [.nonactivatingPanel], backing: .buffered, defer: false)
foreign.isReleasedWhenClosed = false
for (letter, code) in letterActions + [("t", kVK_ANSI_T)] {
    key(scopedLetters, code: code, characters: letter, repeatPress: true)
    check(menu() === scopedLetters && destinationCalls() == callsBeforeScope,
          "held \(letter) cannot invoke an action from a repeated key event")
    for modifiers: NSEvent.ModifierFlags in [.command, .option, .control, .shift] {
        key(scopedLetters, code: code, characters: letter, modifiers: modifiers)
        check(menu() === scopedLetters && destinationCalls() == callsBeforeScope,
              "modified \(letter) does not invoke a plain-letter shortcut")
    }
    key(foreign, code: code, characters: letter)
    check(menu() === scopedLetters && destinationCalls() == callsBeforeScope,
          "\(letter) targeted to another window cannot invoke a menu action")
}
foreign.close()
SharedToolActions.cancel(owner: owner)
check(TestPasteboard.board.changeCount == fixtureChangeCount,
      "letter actions preserve the clipboard")

let escaped = open(.text("keep source"))
key(parent, code: kVK_DownArrow)
check(menu() === escaped, "key targeted to another window cannot operate menu")
key(escaped, code: kVK_Escape, characters: "\u{1b}")
check(menu() == nil && parent.isKeyWindow && parentField.stringValue == "unchanged search", "Escape returns to original source without changing search")
let toggled = open(.text("toggle"))
key(toggled, code: kVK_ANSI_K, characters: "k", modifiers: .command)
check(menu() === toggled, "Cmd-K is not an Actions shortcut")
key(toggled, code: kVK_ANSI_Grave, characters: "`", modifiers: [.control, .option])
check(menu() === toggled, "Control-Option grave is reserved for the original accent")
key(toggled, code: kVK_ANSI_Grave, characters: "`", modifiers: .option, accentTagged: true)
check(menu() === toggled, "remapped original accent bypasses the Actions shortcut without closing the menu")
key(toggled, code: kVK_ANSI_Grave, characters: "`", modifiers: .option, repeatPress: true)
check(menu() === toggled, "held Option grave cannot immediately close the newly opened menu")
key(toggled, code: kVK_ANSI_Grave, characters: "`", modifiers: .option)
check(menu() == nil, "Option grave closes its own action menu")
let commandClosed = open(.text("close child only"))
key(commandClosed, code: kVK_ANSI_W, characters: "w", modifiers: .command)
check(menu() == nil && parent.isVisible && parentField.stringValue == "unchanged search",
      "Cmd-W closes action menu and preserves source window")
let nativeClosed = open(.text("native close"))
nativeClosed.close(); drain()
check(menu() == nil && !SharedToolActions.owns(window: nativeClosed, owner: owner),
      "native action window close releases owned menu")

// External selections present the same menu independently of a source NSWindow.
let frontPID = NSWorkspace.shared.frontmostApplication?.processIdentifier
SharedToolActions.present(content: .text("standalone exact \r\ntext"), title: "External fixture", from: nil, owner: owner)
wait { menu() != nil }
let standalone = menu()!
check(standalone.parent == nil && standalone.level == .floating
      && NSScreen.pointerVisibleFrame.contains(standalone.frame), "standalone menu fits pointer screen without attaching to another window")
key(standalone, code: kVK_Escape, characters: "\u{1b}")
check(menu() == nil && NSWorkspace.shared.frontmostApplication?.processIdentifier == frontPID,
      "standalone Escape closes without activating a different application")
SharedToolActions.present(content: .text("standalone exact \r\ntext"), title: "External fixture", from: nil, owner: owner)
wait { menu() != nil }
click(menu()!, title: SnippetCaptureStrings.localized(.enUS).save)
check(SnippetLibraryService.shared.received.last == "standalone exact \r\ntext",
      "standalone menu routes the exact selection without copying")

AppFeature.available = [.textSnippets]
let gated = open(.text("only snippet"))
check(actionButtons(gated).map(\.title) == [SnippetCaptureStrings.localized(.enUS).save], "disabled destinations are absent")
let callsBeforeUnavailable = destinationCalls()
for (letter, code) in letterActions + [("t", kVK_ANSI_T)] where letter != "s" {
    key(gated, code: code, characters: letter)
    check(menu() === gated && destinationCalls() == callsBeforeUnavailable,
          "unavailable \(letter) leaves the menu open without invoking its selected action")
}
AppFeature.available = []
let beforeDisabled = SnippetLibraryService.shared.received.count
key(gated, code: kVK_Return, characters: "\r")
check(SnippetLibraryService.shared.received.count == beforeDisabled, "feature disabled after menu opening is checked again at execution")
check(!SharedToolActions.supports(entry: .init(text: "file", kind: .files)), "files have no unsupported shared actions")
AppFeature.available = [.clipboardHistory]
let noSnippets = open(.text("snippet unavailable"))
let callsWithoutSnippets = destinationCalls()
key(noSnippets, code: kVK_ANSI_S, characters: "s")
check(menu() === noSnippets && destinationCalls() == callsWithoutSnippets,
      "S cannot invoke the selected inspector when snippets are unavailable")
SharedToolActions.cancel(owner: owner)
AppFeature.available = Set(AppFeature.allCases)
let disabledLetter = open(.text("disabled after opening"))
AppFeature.available.remove(.textSnippets)
key(disabledLetter, code: kVK_ANSI_S, characters: "s")
check(destinationCalls() == callsWithoutSnippets,
      "letter execution rechecks a feature disabled after menu opening")
SharedToolActions.cancel(owner: owner)
AppFeature.available = Set(AppFeature.allCases)

// Actual command-bar handoff methods retain search state for clipboard rows.
let bar = Bar(); bar.panel = parent
let selectedEntry = ClipboardHistoryEntry(text: "command bar snapshot")
ClipboardHistoryService.shared.entries = [selectedEntry]
bar.selectedEntry = .init(id: "clipboard." + selectedEntry.id.uuidString)
check(bar.canOpenActions, "command bar recognizes selected clipboard text outside static app catalog")
bar.openActions(); wait { menu() != nil }
check(bar.mode == .search && bar.query == "original query" && bar.savedQuery.isEmpty && bar.layouts == 0,
      "shared clipboard actions retain Command Bar search/query")
ClipboardHistoryService.shared.entries[0].text = "changed in source history"
click(menu()!, title: SharedToolActionStrings.inspect)
check(PayloadInspectorService.shared.received.last == "command bar snapshot", "command bar handoff preserves original entry content")
bar.selectedEntry = .init(id: "app.fixture"); bar.entriesByID = ["app.fixture": bar.selectedEntry!]
bar.openActions()
check(bar.mode == .actions(entryID: "app.fixture") && bar.savedQuery == "original query" && bar.actionIndex == 0 && bar.layouts == 1,
      "ordinary app actions retain existing menu mode and saved query")
bar.mode = .search; bar.selectedEntry = .init(id: "clipboard." + UUID().uuidString)
check(!bar.canOpenActions, "removed clipboard entry cannot open stale actions")

// Delayed original-image loading cannot reopen a closed action menu.
let pixels = image(17), otherPixels = image(9)
for (letter, code) in letterActions where letter == "l" || letter == "r" {
    var selectedPixels = pixels
    let imageLetters = open(.image(selectedPixels))
    selectedPixels = otherPixels
    let calls = destinationCalls()
    key(imageLetters, code: code, characters: letter)
    check(menu() == nil && destinationCalls() == calls + 1
          && ScreenCompareService.shared.received.last?.0 === pixels
          && ScreenCompareService.shared.received.last?.1 == (letter == "l"),
          "\(letter) sends original image identity to the requested comparison side")
}
let imageTextLetters = open(.image(pixels))
let callsBeforeImageLetters = destinationCalls()
for (letter, code) in letterActions + [("t", kVK_ANSI_T)] where ["s", "j", "i", "t"].contains(letter) {
    key(imageTextLetters, code: code, characters: letter)
    check(menu() === imageTextLetters && destinationCalls() == callsBeforeImageLetters,
          "text-only \(letter) cannot invoke a different image action")
}
SharedToolActions.cancel(owner: owner)
for (name, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
    parent.appearance = NSAppearance(named: appearance)
    let screenshotMenu = open(.image(pixels))
    verifyMenuLayout(screenshotMenu)
    capture(screenshotMenu, "/tmp/vorssaint-shared-actions-screenshot-\(name).png")
    SharedToolActions.cancel(owner: owner)
}
parent.appearance = nil
ClipboardImageStore.data = ["original.png": NSBitmapImageRep(cgImage: pixels).representation(using: .png, properties: [:])!,
                            "changed.png": NSBitmapImageRep(cgImage: otherPixels).representation(using: .png, properties: [:])!]
let commandImage = ClipboardHistoryEntry(text: "image command", kind: .image, imageFile: "original.png")
ClipboardHistoryService.shared.entries = [commandImage]
bar.mode = .search; bar.selectedEntry = .init(id: "clipboard." + commandImage.id.uuidString)
check(bar.canOpenActions, "command bar supports an image entry without a text cast")
bar.openActions()
wait { menu().map { actionButtons($0).allSatisfy(\.isEnabled) } == true }
check(bar.mode == .search && bar.query == "original query", "image actions preserve command-bar search query")
click(menu()!, title: SharedToolActionStrings.before)
check(ScreenCompareService.shared.received.last?.0.width == 17 && ScreenCompareService.shared.received.last?.1 == true,
      "command-bar image action routes original pixels to screen comparison Before")
let delayedGate = DispatchSemaphore(value: 0)
ClipboardImageStore.gate = delayedGate
let reads = ClipboardImageStore.readCount()
var imageEntry = ClipboardHistoryEntry(text: "stored image", kind: .image, imageFile: "original.png")
SharedToolActions.present(entry: imageEntry, from: parent, owner: owner)
wait { ClipboardImageStore.readCount() == reads + 1 }
let loading = menu()!
check(actionButtons(loading).allSatisfy { !$0.isEnabled }, "image actions wait for original file pixels")
let callsBeforeLoadingLetters = destinationCalls()
for (letter, code) in letterActions where letter == "l" || letter == "r" {
    key(loading, code: code, characters: letter)
    check(menu() === loading && destinationCalls() == callsBeforeLoadingLetters,
          "\(letter) waits for image loading without dispatching or closing the menu")
}
SharedToolActions.cancel(owner: owner)
delayedGate.signal(); drain(); drain()
check(menu() == nil && ScreenshotService.shared.images.isEmpty, "closing during image load rejects late completion")
check(destinationCalls() == callsBeforeLoadingLetters, "loading shortcuts cannot queue an action after cancellation")
ClipboardImageStore.gate = nil
SharedToolActions.present(entry: imageEntry, from: parent, owner: owner)
imageEntry.imageFile = "changed.png"
wait { menu().map { actionButtons($0).allSatisfy(\.isEnabled) } == true }
click(menu()!, title: SharedToolActionStrings.annotate)
check(ScreenshotService.shared.images.last?.width == 17, "historical image action retains original file identity and pixels")
var annotateOverrides = 0
let genericAnnotations = ScreenshotService.shared.images.count
SharedToolActions.present(content: .image(pixels), title: "preview edit", from: parent, owner: owner,
                          onAnnotate: { annotateOverrides += 1 })
wait { menu() != nil }
click(menu()!, title: SharedToolActionStrings.annotate)
check(annotateOverrides == 1 && ScreenshotService.shared.images.count == genericAnnotations,
      "preview annotate override runs once without invoking generic annotation")
SharedToolActions.present(content: .image(pixels), title: "disabled preview edit", from: parent, owner: owner,
                          onAnnotate: { annotateOverrides += 1 })
wait { menu() != nil }
AppFeature.available.remove(.screenshot)
click(menu()!, title: SharedToolActionStrings.annotate)
check(annotateOverrides == 1 && ScreenshotService.shared.images.count == genericAnnotations,
      "annotation feature is checked again before preview override execution")
AppFeature.available = Set(AppFeature.allCases)
let missing = open(.imageFile("missing.png"))
wait { views(missing.contentView!).compactMap { $0 as? NSTextField }.contains { $0.stringValue == SharedToolActionStrings.unavailable } }
check(actionButtons(missing).allSatisfy { !$0.isEnabled }, "missing historical image disables actions without clipboard fallback")
let callsBeforeMissingLetters = destinationCalls()
for (letter, code) in letterActions where letter == "l" || letter == "r" {
    key(missing, code: code, characters: letter)
    check(menu() === missing && destinationCalls() == callsBeforeMissingLetters,
          "\(letter) cannot dispatch failed image content")
}
SharedToolActions.cancel(owner: owner)

// Both extracted and selected text use one compact transform/editor surface.
func textResults(_ title: String = TextTransformStrings.title) -> [NSWindow] {
    app.windows.filter { $0.isVisible && $0.title == title }
}
func editor(_ window: NSWindow) -> NSTextView { views(window.contentView!).compactMap { $0 as? NSTextView }.first! }
func toolButton(_ window: NSWindow, _ title: String) -> NSButton {
    views(window.contentView!).compactMap { $0 as? NSButton }.first { $0.title == title }!
}
func choose(_ window: NSWindow, _ kind: TextTransform.Kind) {
    let button = toolButton(window, TextTransformStrings.title(for: kind))
    wait { button.isEnabled }; button.performClick(nil); drain()
}
func openText(_ text: String) -> NSWindow {
    let previous = Set(textResults().map(\.windowNumber))
    let toolbar = open(.text(text))
    key(toolbar, code: kVK_ANSI_T, characters: "t")
    check(menu() == nil, "T closes Actions and opens text tools")
    wait { textResults().contains { !previous.contains($0.windowNumber) } }
    return textResults().first { !previous.contains($0.windowNumber) }!
}
func verifyTools(_ window: NSWindow) {
    window.contentView!.layoutSubtreeIfNeeded()
    let buttons = views(window.contentView!).compactMap { $0 as? SharedToolActionButton }
    check(buttons.count == 7, "one row holds five transforms, Edit and Copy")
    let frames = buttons.map { $0.convert($0.bounds, to: window.contentView) }
    check(frames.allSatisfy { $0.width == 32 && $0.height == 32 && window.contentView!.bounds.contains($0) }
          && zip(frames, frames.dropFirst()).allSatisfy { abs($0.minY - $1.minY) < 1 && $0.maxX < $1.minX },
          "all tools use the same small square targets in a thin horizontal bar")
    check(buttons.allSatisfy { $0.image != nil && $0.imagePosition == .imageOnly && $0.accessibilityLabel() == $0.title
          && $0.toolTip?.contains($0.title) == true }, "icons have valid symbols, names and shortcut tooltips")
    check(!views(window.contentView!).contains { $0 is NSPopUpButton }
          && !buttons.contains { $0.title == SharedToolActionStrings.actions || $0.title == SnippetCaptureStrings.localized(.enUS).save },
          "text tools have no dropdown, second Actions menu or Snip button")
}
let sourceText = "  Broken  sentence\n across two lines.\n\nNext paragraph.  "
var entryForTools = ClipboardHistoryEntry(text: sourceText)
SharedToolActions.present(entry: entryForTools, from: parent, owner: owner)
wait { menu() != nil }; entryForTools.text = "later mutation"
key(menu()!, code: kVK_ANSI_T, characters: "t")
wait { textResults().count == 1 }
let toolsWindow = textResults()[0], working = editor(textResults()[0])
check(working.string == sourceText && !working.isEditable && toolButton(toolsWindow, "Copy").isEnabled,
      "selected text is a fixed snapshot, immediately copyable, with explicit Edit")
verifyTools(toolsWindow)
wait { toolButton(toolsWindow, TextTransformStrings.title(for: .joinLines)).isEnabled }
key(toolsWindow, code: kVK_ANSI_J, characters: "j", repeatPress: true)
key(toolsWindow, code: kVK_ANSI_J, characters: "j", modifiers: .command)
key(parent, code: kVK_ANSI_J, characters: "j")
check(working.string == sourceText, "repeat, modified and other-window keys cannot transform text")
key(toolsWindow, code: kVK_ANSI_J, characters: "j")
check(working.string == "Broken  sentence across two lines. Next paragraph." && !working.isEditable,
      "J joins lines and keeps the toolbar ready for another shortcut")
key(toolsWindow, code: kVK_ANSI_Z, characters: "z", modifiers: .command)
check(working.string == sourceText, "Cmd-Z undoes a transformation before entering edit mode")
key(toolsWindow, code: kVK_ANSI_E, characters: "e", modifiers: .command)
check(working.isEditable && toolsWindow.firstResponder === working, "Cmd-E enables editing and focuses the text")
working.setSelectedRange(NSRange(location: 0, length: (working.string as NSString).length))
for (letter, code) in [("j", kVK_ANSI_J), ("s", kVK_ANSI_S), ("f", kVK_ANSI_F), ("u", kVK_ANSI_U), ("b", kVK_ANSI_B)] {
    key(toolsWindow, code: code, characters: letter)
}
check(working.string == "jsfub", "all letter shortcuts become ordinary typing in edit mode")
working.breakUndoCoalescing()
working.insertText("Edited  first\n second line", replacementRange: NSRange(location: 0, length: (working.string as NSString).length))
working.breakUndoCoalescing(); drain()
choose(toolsWindow, .cleanSpacing)
check(working.string == "Edited first\nsecond line", "transformation uses the latest manual edits")
key(toolsWindow, code: kVK_ANSI_Z, characters: "z", modifiers: .command)
check(working.string == "Edited  first\n second line", "undo preserves preceding edits")
let editToggle = toolButton(toolsWindow, TextTransformStrings.edit) as! SharedToolActionButton
let editSelection = NSRange(location: 0, length: 6)
working.setSelectedRange(editSelection)
editToggle.performClick(nil); drain()
check(!working.isEditable && !editToggle.menuSelected && toolsWindow.firstResponder === toolsWindow
      && working.string == "Edited  first\n second line" && working.selectedRange() == editSelection,
      "pencil toggles editing off, retains text/selection, and returns focus to shortcuts")
key(toolsWindow, code: kVK_ANSI_J, characters: "j")
check(working.string == "Edited  first second line" && !working.isEditable,
      "J transforms immediately after editing is toggled off")
key(toolsWindow, code: kVK_ANSI_Z, characters: "z", modifiers: .command)
check(working.string == "Edited  first\n second line", "undo survives the edit-mode toggle")
key(toolsWindow, code: kVK_ANSI_E, characters: "e", modifiers: .command)
key(toolsWindow, code: kVK_ANSI_E, characters: "e", modifiers: .command, repeatPress: true)
check(working.isEditable && editToggle.menuSelected && toolsWindow.firstResponder === working,
      "Cmd-E toggles editing back on once per press and restores text focus")
check(TestPasteboard.board.changeCount == fixtureChangeCount, "editing and transformation do not copy automatically")
for (name, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
    toolsWindow.appearance = NSAppearance(named: appearance); drain()
    capture(toolsWindow, "/tmp/vorssaint-text-tools-\(name).png")
}
toolsWindow.setContentSize(NSSize(width: 360, height: 240)); drain(); verifyTools(toolsWindow)
key(toolsWindow, code: kVK_Escape, characters: "\u{1b}")
check(!toolsWindow.isVisible && TestPasteboard.board.changeCount == fixtureChangeCount, "Escape closes without copying")

for (source, kind, expected) in [("line one\nline two", TextTransform.Kind.joinLines, "line one line two"),
                               (" a   b ", .cleanSpacing, "a b"),
                               (#"{"id":9007199254740993}"#, .formatJSON, "{\n  \"id\": 9007199254740993\n}"),
                               ("Hello%20world%21", .decodeURL, "Hello world!"),
                               ("U0FQLTUzMQ==", .decodeBase64, "SAP-531")] {
    let window = openText(source)
    let operation = toolButton(window, TextTransformStrings.title(for: kind))
    check(operation.toolTip?.hasSuffix(kind.shortcut.uppercased()) == true, "transform tooltip advertises its actual key")
    wait { operation.isEnabled }
    key(window, code: kVK_ANSI_X, characters: kind.shortcut)
    check(editor(window).string == expected, "typed-character shortcut performs \(kind)")
    key(window, code: kVK_ANSI_C, characters: "c", modifiers: .command)
    check(!window.isVisible && TestPasteboard.board.string(forType: .string) == expected,
          "Cmd-C copies the complete transformed result and closes")
}
let directCopy = openText("copy without transforming")
key(directCopy, code: kVK_ANSI_C, characters: "c", modifiers: .command)
check(!directCopy.isVisible && TestPasteboard.board.string(forType: .string) == "copy without transforming",
      "Cmd-C works immediately without choosing an operation")
let selectedCopy = openText("selected remainder")
editor(selectedCopy).setSelectedRange(NSRange(location: 0, length: 8))
key(selectedCopy, code: kVK_ANSI_C, characters: "c", modifiers: .command)
check(!selectedCopy.isVisible && TestPasteboard.board.string(forType: .string) == "selected", "Cmd-C copies the selection and closes")
let emptyWindow = openText("")
let beforeEmpty = TestPasteboard.board.changeCount
key(emptyWindow, code: kVK_Return, characters: "\r")
key(emptyWindow, code: kVK_ANSI_C, characters: "c", modifiers: .command)
check(emptyWindow.isVisible && TestPasteboard.board.changeCount == beforeEmpty, "empty text neither copies nor closes")
emptyWindow.close()
let oversized = openText(String(repeating: "x", count: TextTransform.maxBytes + 1))
check(editor(oversized).string.isEmpty && !toolButton(oversized, "Copy").isEnabled, "oversized input is bounded before rendering")
oversized.close()
TextTransformController.show(text: sourceText); textResults()[0].close(); drain()
check(textResults().isEmpty, "late transform preparation cannot reopen a closed result")
let disabledTools = open(.text(sourceText)); AppFeature.available.remove(.clipboardHistory)
key(disabledTools, code: kVK_ANSI_T, characters: "t")
check(textResults().isEmpty, "T rechecks feature availability")
AppFeature.available = Set(AppFeature.allCases)

// Image extraction has an editable result with the same direct toolbar, never another Actions step.
let extraction = open(.image(pixels)); click(extraction, title: SharedToolActionStrings.extract)
func results() -> [NSWindow] { textResults(SharedToolActionStrings.extract) }
wait { results().count == 1 && ScreenTextService.completions.count == 1 }
let discarded = results()[0]; discarded.close()
let beforeRecognition = TestPasteboard.board.changeCount
ScreenTextService.completions[0](.success("late discarded text")); drain()
check(results().isEmpty && TestPasteboard.board.changeCount == beforeRecognition, "closed extraction rejects late text without copying")
ExtractedTextController.show(image: pixels)
wait { results().count == 1 && ScreenTextService.completions.count == 2 }
let result = results()[0]
ScreenTextService.completions[1](.success("Recognized first line\nsecond line")); drain()
let extracted = editor(result)
check(extracted.isEditable && result.firstResponder === extracted && extracted.allowsUndo,
      "explicit extraction opens directly in edit mode")
verifyTools(result)
extracted.setSelectedRange(NSRange(location: (extracted.string as NSString).length, length: 0))
key(result, code: kVK_Return, characters: "\r", modifiers: .shift)
check(extracted.string == "Recognized first line\nsecond line\n" && result.isVisible
      && TestPasteboard.board.changeCount == beforeRecognition, "Shift-Enter adds a line without copying or closing")
key(result, code: kVK_ANSI_Z, characters: "z", modifiers: .command)
check(extracted.string == "Recognized first line\nsecond line", "Cmd-Z keeps ordinary text undo")
extracted.setSelectedRange(NSRange(location: 0, length: 10))
key(result, code: kVK_Return, characters: "\r")
check(!result.isVisible && TestPasteboard.board.string(forType: .string) == "Recognized first line\nsecond line",
      "Enter copies the full value despite a selection and closes")
ExtractedTextController.show(text: "copy button value")
let copyResult = results()[0]; toolButton(copyResult, "Copy").performClick(nil); drain()
check(!copyResult.isVisible && TestPasteboard.board.string(forType: .string) == "copy button value", "Copy button also copies and closes")

// The OCR confirmation does not take focus; an explicit click opens editing inside the island.
let island = NotchService.shared
let islandPanel = NSPanel(contentRect: NSRect(x: 200, y: 200, width: 600, height: 150),
                          styleMask: [.titled, .nonactivatingPanel], backing: .buffered, defer: false)
islandPanel.isReleasedWhenClosed = false
islandPanel.title = "Island OCR fixture"
island.presentationWindow = islandPanel
parent.makeKeyAndOrderFront(nil); parent.makeFirstResponder(parentField)
let frontBeforePreview = NSWorkspace.shared.frontmostApplication?.processIdentifier
let beforePreview = TestPasteboard.board.changeCount
let fullOCR = "OCR line one\nline two\n" + String(repeating: "untruncated text ", count: 180)
check(ScreenTextPreviewController.shared.show(text: fullOCR), "OCR confirmation appears")
drain()
check(!island.tookFocus && parent.isKeyWindow
      && NSWorkspace.shared.frontmostApplication?.processIdentifier == frontBeforePreview,
      "OCR confirmation keeps keyboard focus and the frontmost app unchanged")
check(SystemShortcutTakeover.claims.contains("screenTextPreviewEditShortcut"), "visible preview registers Command-E")
check(TestPasteboard.board.changeCount == beforePreview, "showing the confirmation itself performs no extra copy")
func pressEdit(_ element: AnyObject) -> Bool {
    if element.accessibilityIdentifier?() == "ocr.edit" { return element.accessibilityPerformPress?() ?? false }
    return (element.accessibilityChildren?() ?? []).contains { pressEdit($0 as AnyObject) }
}
check(pressEdit(islandPanel.contentView!), "island offers an explicit Edit control")
wait { views(islandPanel.contentView!).contains { $0 is NSTextView } && editor(islandPanel).isEditable }
let islandEditor = editor(islandPanel)
wait { islandPanel.firstResponder === islandEditor }
check(island.tookFocus && islandEditor.string == fullOCR && results().isEmpty,
      "clicking the preview opens the complete text in island edit mode, with no separate window")
check(!SystemShortcutTakeover.claims.contains("screenTextPreviewEditShortcut"), "clicking Edit releases the preview hotkey")
check((islandEditor.enclosingScrollView?.contentView.bounds.height ?? 0) >= 120
      && islandEditor.visibleRect.height >= 120 && islandEditor.visibleRect.width > 0,
      "OCR editor keeps a readable viewport inside the island's outer scroll view")
verifyTools(islandPanel)
capture(islandPanel, "/tmp/vorssaint-ocr-island-editor.png")
let activeEditor = island.captureID
RunLoop.main.run(until: Date().addingTimeInterval(3.2))
check(island.captureID == activeEditor && islandPanel.isVisible, "old confirmation timer cannot dismiss the editor")
islandEditor.insertText("  correction\n second line ", replacementRange: NSRange(location: 0, length: (islandEditor.string as NSString).length)); drain()
let islandEditToggle = toolButton(islandPanel, TextTransformStrings.edit) as! SharedToolActionButton
key(islandPanel, code: kVK_ANSI_E, characters: "e", modifiers: .command)
check(!islandEditor.isEditable && !islandEditToggle.menuSelected && islandPanel.firstResponder === islandPanel,
      "Cmd-E turns off automatic OCR editing and makes island shortcuts available")
key(islandPanel, code: kVK_ANSI_S, characters: "s")
check(islandEditor.string == "correction\nsecond line", "island transform uses current edits")
islandEditToggle.performClick(nil); drain()
check(islandEditor.isEditable && islandEditToggle.menuSelected && islandPanel.firstResponder === islandEditor,
      "island pencil toggles editing back on")
islandEditor.setSelectedRange(NSRange(location: (islandEditor.string as NSString).length, length: 0))
key(islandPanel, code: kVK_ANSI_J, characters: "j")
check(islandEditor.string == "correction\nsecond linej", "letters type normally after OCR editing is re-enabled")
key(islandPanel, code: kVK_ANSI_Z, characters: "z", modifiers: .command)
check(islandEditor.string == "correction\nsecond line", "text undo remains intact after switching modes")
islandEditor.setSelectedRange(NSRange(location: 0, length: 10))
key(islandPanel, code: kVK_ANSI_C, characters: "c", modifiers: .command)
check(island.captureID == nil && !islandPanel.isVisible && TestPasteboard.board.string(forType: .string) == "correction",
      "island Cmd-C copies its selection and closes the editor")
parent.makeKeyAndOrderFront(nil)
check(ScreenTextPreviewController.shared.show(text: "expire quietly"), "another no-focus confirmation can open")
let beforeExpiry = TestPasteboard.board.changeCount
RunLoop.main.run(until: Date().addingTimeInterval(3.2))
check(island.captureID == nil && parent.isKeyWindow && TestPasteboard.board.changeCount == beforeExpiry,
      "unattended confirmation expires without stealing focus or changing the clipboard")
check(!SystemShortcutTakeover.claims.contains("screenTextPreviewEditShortcut"), "preview expiry releases Command-E")
weak var displacedController: TextTransformController?
let replacementID = UUID()
autoreleasepool {
    TextTransformController.showInIsland(text: "Replacement lifecycle fixture"); drain()
    displacedController = editor(islandPanel).delegate as? TextTransformController
    check(displacedController != nil, "island editor has a live controller before replacement")
    _ = island.presentCapture(id: replacementID, content: AnyView(Text("Replacement")), height: 150,
                              takeFocus: false, closeOnCollapse: true, fallback: {}, close: {}, hover: { _ in })
}
drain()
check(displacedController == nil && island.captureID == replacementID,
      "replacing the island editor releases it without removing the new capture")
island.removeCapture(id: replacementID)

// Copy-and-close returns the actual frontmost source application for immediate paste.
var helper = Process(); helper.executableURL = URL(fileURLWithPath: CommandLine.arguments[0]); helper.arguments = ["--focus-helper"]
try! helper.run()
wait { NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier }
func helperKeys() -> String { (try? String(contentsOf: helperKeysURL, encoding: .utf8)) ?? "" }
func postHelperKey(_ code: Int) {
    check(NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier,
          "native shortcut probe only posts while its controlled helper is frontmost")
    for down in [true, false] {
        let event = CGEvent(keyboardEventSource: nil, virtualKey: CGKeyCode(code), keyDown: down)!
        event.flags = .maskCommand
        event.setIntegerValueField(.eventSourceUserData, value: previewKeyTag)
        event.post(tap: .cghidEventTap)
    }
}
@MainActor func pumpUntil(_ message: String, _ condition: @MainActor () -> Bool) async {
    let deadline = Date().addingTimeInterval(2)
    while !condition() && Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
    if !condition() {
        fputs("Shortcut delivery: \(message), helper keys=\(helperKeys()), source focused=\(NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier), island key=\(islandPanel.isKeyWindow), preview active=\(island.captureID != nil)\n", stderr)
    }
    check(condition(), message)
}
// Carbon and nonactivating panel focus are dispatched by the real application
// loop. Mixing posted system keys with direct sendEvent calls misses that handoff.
Task { @MainActor in
    let beforeKeyboardPreview = TestPasteboard.board.changeCount
    check(ScreenTextPreviewController.shared.show(text: "Keyboard OCR\nsecond line"), "keyboard preview opens")
    drain()
    check(NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier && !island.tookFocus,
          "preview leaves the other app focused before Command-E")
    postHelperKey(kVK_ANSI_V); await pumpUntil("Command-V reaches the focused source") { helperKeys() == "v" }
    check(!views(islandPanel.contentView!).contains { $0 is NSTextView }, "Command-V reaches the source app without opening Edit")
    postHelperKey(kVK_ANSI_E)
    await pumpUntil("Command-E opens the OCR editor") {
        islandPanel.contentView.map { views($0).contains { $0 is NSTextView } } == true
    }
    let shortcutEditor = editor(islandPanel)
    check(shortcutEditor.string == "Keyboard OCR\nsecond line" && shortcutEditor.isEditable
          && helperKeys() == "v" && !SystemShortcutTakeover.claims.contains("screenTextPreviewEditShortcut")
          && TestPasteboard.board.changeCount == beforeKeyboardPreview,
          "global Command-E consumes only that command, transfers the full text, and releases itself without copying")
    postHelperKey(kVK_ANSI_E); await pumpUntil("native Command-E toggles editing off") { !shortcutEditor.isEditable }
    check(!shortcutEditor.isEditable, "Command-E inside the keyboard-opened editor still toggles editing off")
    postHelperKey(kVK_ANSI_E); await pumpUntil("native Command-E toggles editing on") { shortcutEditor.isEditable }
    check(shortcutEditor.isEditable, "Command-E still toggles editing back on")
    postHelperKey(kVK_ANSI_C); await pumpUntil("native Command-C copies and closes") { island.captureID == nil }
    // Establish a real keyboard target before checking global registration
    // cleanup; frontmostApplication alone does not prove a window has focus.
    helper.terminate(); helper.waitUntilExit()
    helper = Process(); helper.executableURL = URL(fileURLWithPath: CommandLine.arguments[0]); helper.arguments = ["--focus-helper"]
    try! helper.run()
    await pumpUntil("fresh source has focus") { NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier }
    postHelperKey(kVK_ANSI_E); await pumpUntil("Command-E is released after closing") { helperKeys() == "e" }
    check(island.captureID == nil, "after closing, Command-E reaches another app without reopening the editor")
    islandPanel.close(); island.presentationWindow = nil
    app.stop(nil)
    app.postEvent(NSEvent.otherEvent(with: .applicationDefined, location: .zero, modifierFlags: [],
        timestamp: 0, windowNumber: 0, context: nil, subtype: 0, data1: 0, data2: 0)!, atStart: false)
}
app.run()
TextTransformController.show(text: "return to source")
wait { textResults().count == 1 && NSWorkspace.shared.frontmostApplication?.processIdentifier == getpid() }
key(textResults()[0], code: kVK_ANSI_C, characters: "c", modifiers: .command)
wait { NSWorkspace.shared.frontmostApplication?.processIdentifier == helper.processIdentifier }
check(TestPasteboard.board.string(forType: .string) == "return to source" && textResults().isEmpty,
      "copy-and-close restores the external source app ready for paste")
helper.terminate(); helper.waitUntilExit()

let closingParent = open(.text("close parent"))
parent.close(); drain()
check(!closingParent.isVisible && menu() == nil, "closing source closes its action menu")
check(actualClipboard.changeCount == actualChangeCount, "fixture never changes actual system clipboard")
print("PASS: \(checks) native shared action and OCR checks")
'''
ticket_source = 'Sources/Vorssaint/Services/CommandBar/CommandBarTicketSearch.swift'
fixture = fixture.replace('// TICKET_METHODS', '\n'.join(declaration(ticket_source, prefix)
    .replace('NSWorkspace.shared.open(url)', 'TestBrowser.open(url)')
    for prefix in ['    static func ticketKeys(in', '    static func directEntry(query:']))
fixture = fixture.replace('// JSON_FORMATTER', declaration(
    'Sources/Vorssaint/Services/Clipboard/ClipboardHistorySupport.swift', 'enum ClipboardJSONFormat'))
bar_source = 'Sources/Vorssaint/Services/CommandBar/CommandBarService.swift'
fixture = fixture.replace('// BAR_METHODS', '\n'.join(declaration(bar_source, prefix).replace('private ', '', 1)
    for prefix in ['    private func clipboardEntry(for', '    var canOpenActions:', '    func openActions()']))
with tempfile.TemporaryDirectory(prefix='shared-tool-actions-ui-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(fixture)
    binary = folder / 'check'
    paths = ['Sources/Vorssaint/Services/QuickTools/SharedToolActions.swift',
             'Sources/Vorssaint/Services/QuickTools/ExtractedTextController.swift',
             'Sources/Vorssaint/Services/QuickTools/ScreenTextPreviewController.swift',
             'Sources/Vorssaint/Services/QuickTools/QuickToolHotkey.swift',
             'Sources/Vorssaint/Services/QuickTools/TextTransform.swift',
             'Sources/Vorssaint/Services/QuickTools/TextTransformController.swift',
             'Sources/Vorssaint/Core/TextTransformStrings.swift',
             'Sources/Vorssaint/UI/ToolAppearance.swift', 'Sources/Vorssaint/Core/SharedToolActionStrings.swift',
             'Sources/Vorssaint/Core/SharedActionShortcut.swift', 'Sources/Vorssaint/Core/AppKitExtensions.swift',
             'Sources/Vorssaint/Core/SnippetCaptureStrings.swift',
             'Sources/Vorssaint/Services/CommandBar/CommandBarLinks.swift']
    subprocess.run(['swiftc', *[str(repo / path) for path in paths], str(source), '-o', str(binary)], check=True)
    if '--compile-only' not in sys.argv:
        preferences = folder / 'preferences'
        preferences.mkdir()
        subprocess.run([str(binary)], check=True, timeout=120,
                       env={**os.environ, 'CFFIXED_USER_HOME': str(preferences)})
