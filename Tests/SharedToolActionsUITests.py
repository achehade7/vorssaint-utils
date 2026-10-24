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
import Carbon.HIToolbox
import ObjectiveC
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
final class NotchService {
    static let shared = NotchService()
    var presentationWindow: NSPanel?
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
    check(content.bounds.width <= 190 && content.bounds.height == 40,
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
      SharedToolActionStrings.inspect, SharedToolActionStrings.before, SharedToolActionStrings.after],
      "text actions put Save snippet first, Inspect second, then comparison sides")
verifyMenuLayout(first)
key(first, code: kVK_Return, characters: "\r")
check(SnippetLibraryService.shared.received.last == "original selected payload" && menu() == nil,
      "Return defaults to Save snippet using the original selected snapshot")
let comparison = open(.text("comparison selected payload"))
key(comparison, code: kVK_DownArrow)
key(comparison, code: kVK_DownArrow)
key(comparison, code: kVK_Return, characters: "\r")
check(ClipboardDiffService.shared.received.last?.0 == "comparison selected payload"
      && ClipboardDiffService.shared.received.last?.1 == true && menu() == nil,
      "two Down presses and Return choose Left after reordered text actions")
let rightComparison = open(.text("right selected payload"))
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
      SharedToolActionStrings.inspect, "Jira", SharedToolActionStrings.before, SharedToolActionStrings.after],
      "Jira follows Snippet and Inspect, before the two comparison icons")
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
for (letter, code) in letterActions {
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
for (letter, code) in letterActions where letter != "s" {
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
for (letter, code) in letterActions where ["s", "j", "i"].contains(letter) {
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

// OCR owns independent editable results; only Copy writes our fixture clipboard.
let imageMenu = open(.image(pixels))
click(imageMenu, title: SharedToolActionStrings.extract)
func results() -> [NSWindow] { app.windows.filter { $0.isVisible && $0.title == SharedToolActionStrings.extract } }
wait { results().count == 1 && ScreenTextService.completions.count == 1 }
let discarded = results()[0]
discarded.close()
ScreenTextService.completions[0](.success("late discarded text")); drain()
check(results().isEmpty && TestPasteboard.board.changeCount == fixtureChangeCount, "closed OCR result rejects recognition without automatic copy")
ExtractedTextController.show(image: pixels)
wait { results().count == 1 && ScreenTextService.completions.count == 2 }
let hiddenResult = results()[0]
hiddenResult.orderOut(nil)
ScreenTextService.completions[1](.success("retained hidden recognition")); drain()
check(!hiddenResult.isVisible && views(hiddenResult.contentView!).compactMap { $0 as? NSTextView }.first!.string == "retained hidden recognition",
      "hiding pending OCR retains recognition without reopening its window")
hiddenResult.close()
ExtractedTextController.show(image: pixels)
wait { results().count == 1 && ScreenTextService.completions.count == 3 }
let result = results()[0]
ScreenTextService.completions[2](.success("Recognized first line\nSecond line")); drain()
let editor = views(result.contentView!).compactMap { $0 as? NSTextView }.first!
check(editor.isEditable && editor.allowsUndo && editor.string == "Recognized first line\nSecond line",
      "OCR returns preserved lines to native editable result")
check(TestPasteboard.board.changeCount == fixtureChangeCount, "recognized OCR does not automatically replace clipboard")
editor.undoManager!.beginUndoGrouping()
editor.insertText("Edited capture\nSecond edited line", replacementRange: NSRange(location: 0, length: (editor.string as NSString).length))
editor.undoManager!.endUndoGrouping()
editor.undoManager!.undo()
check(editor.string == "Recognized first line\nSecond line", "OCR editor native undo restores recognition")
editor.undoManager!.redo()
let edited = editor.string
let resultButtons = views(result.contentView!).compactMap { $0 as? NSButton }
editor.setSelectedRange(NSRange(location: 0, length: 6))
key(result, code: kVK_ANSI_K, characters: "k", modifiers: .command)
check(menu() == nil, "OCR Cmd-K remains available to native text editing")
key(result, code: kVK_ANSI_Grave, characters: "`", modifiers: .option)
wait { menu() != nil }
click(menu()!, title: SnippetCaptureStrings.localized(.enUS).save)
check(SnippetLibraryService.shared.received.last == "Edited", "OCR Option grave saves selected text as snippet")
check(editor.string == edited && editor.undoManager!.canUndo && TestPasteboard.board.changeCount == fixtureChangeCount,
      "selected-text actions preserve native OCR editor, undo and clipboard")
editor.setSelectedRange(NSRange(location: 0, length: 0))
key(result, code: kVK_ANSI_Grave, characters: "`", modifiers: .option)
wait { menu() != nil }
click(menu()!, title: SnippetCaptureStrings.localized(.enUS).save)
check(SnippetLibraryService.shared.received.last == edited, "OCR Option grave without a selection uses all edited text")
result.makeKeyAndOrderFront(nil); result.makeFirstResponder(editor)
editor.undoManager!.undo()
check(editor.string == "Recognized first line\nSecond line", "shared actions leave native OCR undo intact")
editor.undoManager!.redo()
resultButtons.first { $0.title == SnippetCaptureStrings.localized(.enUS).save }!.performClick(nil)
check(SnippetLibraryService.shared.received.last == edited && TestPasteboard.board.changeCount == fixtureChangeCount,
      "snippet handoff uses edited OCR without changing clipboard")
resultButtons.first { $0.title == "Copy" }!.performClick(nil)
check(TestPasteboard.board.string(forType: .string) == edited, "explicit Copy writes exact edited OCR")
result.setContentSize(NSSize(width: 400, height: 260)); drain()
for (name, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
    result.appearance = NSAppearance(named: appearance); drain()
    capture(result, "/tmp/vorssaint-extracted-text-minimum-\(name).png")
}
capture(result, "/tmp/vorssaint-extracted-text-minimum.png")
check(resultButtons.allSatisfy { result.contentView!.bounds.contains($0.convert($0.bounds, to: result.contentView)) },
      "OCR action controls fit minimum window width")
key(result, code: kVK_ANSI_Grave, characters: "`", modifiers: [.control, .option])
check(menu() == nil, "OCR Control-Option grave does not invoke actions")
editor.setMarkedText("に", selectedRange: NSRange(location: 1, length: 0), replacementRange: NSRange(location: NSNotFound, length: 0))
key(result, code: kVK_ANSI_Grave, characters: "`", modifiers: .option)
check(menu() == nil, "OCR IME composition owns Option grave")
editor.unmarkText()
resultButtons.first { $0.title.hasPrefix(SharedToolActionStrings.actions) }!.performClick(nil)
wait { menu() != nil }
let resultMenu = menu()!
result.close()
check(!resultMenu.isVisible && menu() == nil, "closing OCR result cancels its selected-text action menu")

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
