#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise the production AppKit inspector in its own process; never send global keys."""
from pathlib import Path
import subprocess
import os
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
import ObjectiveC

enum AppLanguage: CaseIterable { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n { static var shared = Self(); var language = AppLanguage.enUS }
enum AppFeature { case clipboardHistory; static var enabled = true; var isAvailable: Bool { Self.enabled } }
struct ClipboardHistoryEntry { enum Kind { case text, image, files }; var text: String; var copiedAt: Date; var kind = Kind.text }
final class ClipboardHistoryService { static let shared = ClipboardHistoryService(); var entries: [ClipboardHistoryEntry] = [] }
final class TestSuite {
    var checks = 0
    func expect(_ condition: Bool, _ message: @autoclosure () -> String) { checks += 1; precondition(condition, message()) }
}
let suite = TestSuite()
PayloadInspectorTests.run(suite)
let modelChecks = suite.checks
func expect(_ condition: Bool, _ message: String) { suite.expect(condition, message) }
func until(_ predicate: () -> Bool) -> Bool {
    let end = Date().addingTimeInterval(6)
    repeat { if predicate() { return true }; RunLoop.main.run(until: Date().addingTimeInterval(0.01)) } while Date() < end
    return false
}
func drain(_ seconds: TimeInterval = 0.15) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
func views(_ root: NSView) -> [NSView] { [root] + root.subviews.flatMap(views) }
guard (CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native payload checks require an unlocked Mac. No input was sent.\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let service = PayloadInspectorService.shared
let strings = PayloadInspectorStrings.localized(.enUS)
let pasteboardCount = NSPasteboard.general.changeCount
final class PayloadTestPasteboard: NSObject {
    static let board = NSPasteboard.withUniqueName()
    @objc class func replacementGeneral() -> NSPasteboard { board }
}
func checkCopies(_ window: NSWindow, value: String, path: String) {
    // Redirect this fixture process only, so production button actions can be
    // exercised without ever replacing the user's actual system clipboard.
    let original = class_getClassMethod(NSPasteboard.self, NSSelectorFromString("generalPasteboard"))!
    let replacement = class_getClassMethod(PayloadTestPasteboard.self, #selector(PayloadTestPasteboard.replacementGeneral))!
    method_exchangeImplementations(original, replacement)
    defer { method_exchangeImplementations(original, replacement) }
    view(window, "copyValue", NSButton.self).performClick(nil)
    expect(PayloadTestPasteboard.board.string(forType: .string) == value, "Copy value writes the exact selected value")
    view(window, "copyPath", NSButton.self).performClick(nil)
    expect(PayloadTestPasteboard.board.string(forType: .string) == path, "Copy path writes the exact selected path")
}
let history = ClipboardHistoryService.shared
history.entries = [.init(text: "saved original", copiedAt: Date())]
func window() -> NSWindow { app.windows.first { $0.isVisible && $0.title == PayloadInspectorStrings.localized(L10n.shared.language).title }! }
func view<T: NSView>(_ window: NSWindow, _ id: String, _: T.Type = T.self) -> T {
    views(window.contentView!).first { $0.identifier?.rawValue == "payload." + id } as! T
}
func summary(_ window: NSWindow) -> String { view(window, "summary", NSTextField.self).stringValue }
func edit(_ window: NSWindow, _ text: String) {
    let source = view(window, "source", NSTextView.self)
    source.insertText(text, replacementRange: NSRange(location: 0, length: (source.string as NSString).length))
}
func settled(_ window: NSWindow) -> Bool { until { summary(window) != strings.loading } }
func mode(_ window: NSWindow, _ index: Int) {
    let segment = view(window, "mode", NSSegmentedControl.self)
    segment.selectedSegment = index
    app.sendAction(segment.action!, to: segment.target, from: segment)
}
func select(_ window: NSWindow, _ path: String) -> Bool {
    let tree = view(window, "tree", NSOutlineView.self)
    tree.expandItem(nil, expandChildren: true)
    for row in 0..<tree.numberOfRows {
        tree.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
        if view(window, "path", NSTextField.self).stringValue == path { return true }
    }
    return false
}
func capture(_ window: NSWindow, _ name: String, width: CGFloat = 920, height: CGFloat = 650) {
    window.setContentSize(NSSize(width: width, height: height))
    for (label, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
        window.appearance = NSAppearance(named: appearance)
        drain()
        let content = window.contentView!
        content.layoutSubtreeIfNeeded(); content.displayIfNeeded()
        let bitmap = content.bitmapImageRepForCachingDisplay(in: content.bounds)!
        content.cacheDisplay(in: content.bounds, to: bitmap)
        try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/payload-inspector-\(name)-\(label).png"))
        let segment = view(window, "mode", NSSegmentedControl.self)
        let search = view(window, "search", NSSearchField.self)
        expect(segment.frame.maxX + 12 <= search.frame.minX, "header controls do not overlap at \(width) in \(label)")
        for id in ["copyValue", "copyPath", "openJSON"] {
            let button = view(window, id, NSButton.self)
            expect(button.convert(button.bounds, to: content).maxX <= content.bounds.maxX, "\(id) stays inside \(name) in \(label)")
        }
        if segment.selectedSegment == 0 {
            let detail = view(window, "detail", NSView.self)
            let tree = view(window, "tree", NSOutlineView.self)
            let treeFrame = tree.enclosingScrollView!.convert(tree.enclosingScrollView!.bounds, to: content)
            expect(treeFrame.maxX <= detail.frame.minX && detail.frame.width >= 286,
                   "tree and readable detail pane stay separate at \(width) in \(label)")
            let path = view(window, "path", NSTextField.self)
            expect(path.alignmentRect(forFrame: path.frame).maxX <= detail.bounds.maxX - 18,
                   "monospaced path stays within detail pane")
        }
    }
}
func paneWidths(_ window: NSWindow, width: CGFloat) -> (tree: CGFloat, detail: CGFloat) {
    window.setContentSize(NSSize(width: width, height: 650))
    drain()
    let content = window.contentView!
    content.layoutSubtreeIfNeeded()
    let tree = view(window, "tree", NSOutlineView.self).enclosingScrollView!
    let detail = view(window, "detail", NSView.self)
    expect(abs(content.bounds.width - width) < 1, "inspector can reach requested content width \(width)")
    expect(detail.frame.width >= tree.frame.width,
           "value detail is at least as wide as navigation at \(width)")
    expect(tree.frame.width >= 260 && tree.frame.width <= 421,
           "navigation remains readable and capped at wide sizes")
    return (tree.frame.width, detail.frame.width)
}
func color(_ text: NSTextView, token: String) -> NSColor {
    let range = (text.string as NSString).range(of: token)
    expect(range.location != NSNotFound, "detail contains token \(token)")
    let color = text.textStorage!.attribute(.foregroundColor, at: range.location, effectiveRange: nil) as? NSColor
    expect(color != nil, "detail has a foreground color for \(token)")
    return color!
}
func verifyJSONColors(_ window: NSWindow) {
    let detail = view(window, "value", NSTextView.self)
    for appearance in [NSAppearance.Name.aqua, .darkAqua] {
        window.appearance = NSAppearance(named: appearance)
        drain()
        window.effectiveAppearance.performAsCurrentDrawingAppearance {
            let property = color(detail, token: "\"status\"").usingColorSpace(.deviceRGB)!
            let string = color(detail, token: "approved").usingColorSpace(.deviceRGB)!
            let number = color(detail, token: "1.2300e+4").usingColorSpace(.deviceRGB)!
            let boolean = color(detail, token: "false").usingColorSpace(.deviceRGB)!
            expect(!property.isEqual(string) && !property.isEqual(number) && !property.isEqual(boolean),
                   "property names differ from scalar values in \(appearance.rawValue)")
            expect(!string.isEqual(number) && !number.isEqual(boolean) && !string.isEqual(boolean),
                   "string, numeric and boolean values remain distinguishable in \(appearance.rawValue)")
        }
    }
}
let json = #"{"orders":[{"id":900719925474099312345,"amount":1.2300e+4,"status":"approved","paid":false},{"id":900719925474099312346,"status":"pending"}],"environment":"Q","body":"{\"status\":\"ok\",\"count\":2}"}"#
service.show(text: json)
let first = window()
expect(first.styleMask.contains(.resizable), "inspector is resizable")
expect(settled(first), "initial payload parses automatically")
let tree = view(first, "tree", NSOutlineView.self)
expect(until { tree.numberOfRows > 1 }, "native tree shows root fields")
expect(select(first, #"$["orders"][0]["amount"]"#), "tree expands down to the selected scalar")
expect(view(first, "value", NSTextView.self).string == "1.2300e+4", "detail retains exact numeric spelling")
expect(view(first, "copyValue", NSButton.self).isEnabled && view(first, "copyPath", NSButton.self).isEnabled, "selected value and path are copyable")
checkCopies(first, value: "1.2300e+4", path: #"$["orders"][0]["amount"]"#)
capture(first, "json")
capture(first, "json-small", width: 640, height: 460)
_ = paneWidths(first, width: 640)
let normalPanes = paneWidths(first, width: 920)
let widePanes = paneWidths(first, width: 1500)
expect(widePanes.detail - normalPanes.detail > 500 && widePanes.tree - normalPanes.tree < 80,
       "widening the inspector gives almost all extra room to the value detail")
expect(select(first, #"$["orders"][0]"#), "composite JSON object can be inspected")
let composite = #"{"id":900719925474099312345,"amount":1.2300e+4,"status":"approved","paid":false}"#
expect(view(first, "value", NSTextView.self).string == composite,
       "colored composite detail keeps original spelling and numeric precision")
verifyJSONColors(first)
checkCopies(first, value: composite, path: #"$["orders"][0]"#)
capture(first, "json-composite")
capture(first, "json-wide", width: 1500, height: 650)
capture(first, "json-composite-small", width: 640, height: 460)

let search = view(first, "search", NSSearchField.self)
search.stringValue = "approved"
search.delegate?.controlTextDidChange?(Notification(name: NSControl.textDidChangeNotification, object: search))
expect(until { tree.numberOfRows == 4 }, "search keeps the matched field and its ancestors")
capture(first, "search", width: 760, height: 540)
search.stringValue = "does not exist"
search.delegate?.controlTextDidChange?(Notification(name: NSControl.textDidChangeNotification, object: search))
expect(until { tree.numberOfRows == 0 }, "search has a clear no-match state")
search.stringValue = ""
search.delegate?.controlTextDidChange?(Notification(name: NSControl.textDidChangeNotification, object: search))
expect(until { tree.numberOfRows > 0 }, "clearing search restores the tree")
expect(select(first, #"$["body"]"#), "embedded string is selectable")
expect(view(first, "openJSON", NSButton.self).isEnabled, "embedded JSON offers explicit drill-in")
let rawEmbedded = view(first, "value", NSTextView.self)
expect(rawEmbedded.string == #"{"status":"ok","count":2}"#,
       "embedded JSON string remains decoded text until explicit drill-in")
expect(color(rawEmbedded, token: "status").isEqual(color(rawEmbedded, token: "ok")),
       "embedded JSON text does not acquire structural highlighting before drill-in")
view(first, "openJSON", NSButton.self).performClick(nil)
expect(until { view(first, "back", NSButton.self).isEnabled }, "drill-in offers Back")
expect(until { tree.numberOfRows == 3 }, "escaped JSON becomes a tree")
expect(select(first, #"$["status"]"#) && view(first, "value", NSTextView.self).string == "ok", "decoded nested value is exact")
expect(view(first, "source", NSTextView.self).string == json, "drill-in never changes original source")
capture(first, "embedded", width: 760, height: 540)
view(first, "back", NSButton.self).performClick(nil)
expect(until { !view(first, "back", NSButton.self).isEnabled && tree.numberOfRows == 4 }, "Back restores the outer payload")

mode(first, 1)
let source = view(first, "source", NSTextView.self)
expect(source.isEditable && source.isSelectable && source.allowsUndo, "source retains native editable text and undo")
source.undoManager!.removeAllActions()
source.undoManager!.beginUndoGrouping()
edit(first, "{\"status\":\"ready ✓\"}")
source.undoManager!.endUndoGrouping()
let caret = source.selectedRange()
expect(settled(first) && source.selectedRange() == caret, "parse completion preserves the caret")
source.undoManager!.undo()
expect(source.string == json && settled(first), "undo restores the exact original payload")
source.undoManager!.redo()
expect(source.string == "{\"status\":\"ready ✓\"}" && settled(first), "redo survives result updates")
source.setSelectedRange(NSRange(location: 2, length: 4))
let selected = source.selectedRange()
drain()
expect(source.selectedRange() == selected, "background work preserves the selection")
let privateClipboard = NSPasteboard.withUniqueName()
let pasted = "{\r\n  \"name\": \"cafe\u{301} 👩🏽‍💻\",\r\n\t\"x\": 1\n}\n"
privateClipboard.setString(pasted, forType: .string)
source.selectAll(nil)
expect(source.readSelection(from: privateClipboard), "native paste reads plain text")
expect(source.string.utf8.elementsEqual(pasted.utf8) && settled(first), "Unicode, CRLF, tabs and blank lines are not normalized")
privateClipboard.releaseGlobally()
capture(first, "source", width: 760, height: 540)

let xml = "<orders environment=\"Q\">\n  <order id=\"10023\"><status>approved</status><amount currency=\"EUR\">1250.00</amount></order>\n  <order id=\"10024\"><status>pending</status></order>\n</orders>"
edit(first, xml)
expect(settled(first), "editing automatically switches the parser to XML")
mode(first, 0)
expect(until { tree.numberOfRows > 1 }, "XML appears in the outline")
expect(select(first, "/orders[1]/order[1]/amount[1]/@currency"), "XML attribute can be inspected")
expect(view(first, "value", NSTextView.self).string == "EUR", "XML attribute detail is exact")
checkCopies(first, value: "EUR", path: "/orders[1]/order[1]/amount[1]/@currency")
capture(first, "xml")

edit(first, "{\"broken\":")
expect(until { summary(first).contains("Invalid JSON") }, "malformed input shows a parse error")
expect(tree.numberOfRows == 0 && !view(first, "copyValue", NSButton.self).isEnabled, "invalid source clears stale fields and copy actions")
capture(first, "invalid", width: 640, height: 460)
edit(first, String(repeating: "x", count: PayloadInspector.maxBytes + 1))
expect(until { summary(first) == strings.tooLarge }, "oversized input has an explicit limit state")
expect(source.string.utf8.count == PayloadInspector.maxBytes + 1, "oversized source is never truncated")
capture(first, "oversized", width: 640, height: 460)
edit(first, "[" + Array(repeating: "0", count: 9_000).joined(separator: ",") + "]")
drain(0.18)
edit(first, "{\"latest\":true}")
expect(settled(first) && until { tree.numberOfRows == 2 }, "new source replaces any stale in-flight result")
expect(select(first, #"$["latest"]"#), "only the newest input is installed")
edit(first, "")
expect(until { summary(first) == strings.empty }, "empty input has clear instructions")
capture(first, "empty", width: 640, height: 460)
expect(history.entries.count == 1 && history.entries[0].text == "saved original", "inspection and edits leave saved history unchanged")
expect(NSPasteboard.general.changeCount == pasteboardCount, "inspection, editing, search and drill-in never touch the system clipboard")
first.close()

L10n.shared.language = .de
service.show(text: json)
let german = window()
expect(until { view(german, "tree", NSOutlineView.self).numberOfRows > 0 }, "localized inspector opens")
capture(german, "german-small", width: 640, height: 460)
german.close()
L10n.shared.language = .enUS
service.show(text: "")
let empty = window()
expect(view(empty, "mode", NSSegmentedControl.self).selectedSegment == 1, "empty launch opens the paste editor")
expect(until { summary(empty) == strings.empty }, "empty launch settles before capture")
capture(empty, "empty-source", width: 640, height: 460)
edit(empty, json)
empty.close()
service.show(text: "")
let reopened = window()
expect(until { summary(reopened) == strings.empty } && view(reopened, "source", NSTextView.self).string.isEmpty, "closed-window results never enter a reopened inspector")
reopened.close()

// Action handoff preserves current editor/undo until replacement is confirmed.
let incoming = #"{"incoming":"selected clipboard item"}"#
service.receive("")
let emptyDestination = window()
service.receive(json)
let handoff = window()
expect(!emptyDestination.isVisible && handoff.attachedSheet == nil
       && view(handoff, "source", NSTextView.self).string == json,
       "empty inspector receives source directly without replacement confirmation")
expect(settled(handoff), "handoff opens a fresh inspector")
mode(handoff, 1)
let handoffSource = view(handoff, "source", NSTextView.self)
handoffSource.undoManager!.removeAllActions()
handoffSource.undoManager!.beginUndoGrouping()
edit(handoff, #"{"draft":"edited source"}"#)
handoffSource.undoManager!.endUndoGrouping()
handoffSource.setSelectedRange(NSRange(location: 2, length: 5))
let handoffSelection = handoffSource.selectedRange(), draftText = handoffSource.string
service.receive(draftText)
expect(window() === handoff && handoff.attachedSheet == nil && handoffSource.selectedRange() == handoffSelection
       && handoffSource.undoManager!.canUndo, "same incoming source preserves window, selection and undo without prompt")
service.receive(incoming)
expect(until { handoff.attachedSheet != nil } && handoffSource.string == draftText,
       "different incoming payload requires confirmation before changing edited source")
let cancelledSheet = handoff.attachedSheet!
service.receive(#"{"later":"another handoff"}"#)
expect(handoff.attachedSheet === cancelledSheet && handoffSource.string == draftText,
       "another handoff cannot replace pending confirmation or current editor")
handoff.endSheet(cancelledSheet, returnCode: .alertSecondButtonReturn)
expect(until { handoff.attachedSheet == nil } && handoffSource.string == draftText
       && handoffSource.undoManager!.canUndo, "Cancel preserves editor text and native undo")
service.receive(incoming)
expect(until { handoff.attachedSheet != nil }, "replacement can be requested again after cancellation")
handoff.endSheet(handoff.attachedSheet!, returnCode: .alertFirstButtonReturn)
expect(until { !handoff.isVisible && app.windows.contains { $0.isVisible && $0.title == strings.title } },
       "confirmed handoff replaces the inspector once")
let accepted = window()
expect(view(accepted, "source", NSTextView.self).string == incoming && settled(accepted),
       "confirmed handoff installs exact incoming source")
mode(accepted, 1)
service.receive(json)
expect(until { accepted.attachedSheet != nil }, "second replacement prompts for current source")
edit(accepted, #"{"newer":"edit while confirmation was open"}"#)
let newest = view(accepted, "source", NSTextView.self).string
accepted.endSheet(accepted.attachedSheet!, returnCode: .alertFirstButtonReturn)
expect(until { accepted.attachedSheet == nil } && window() === accepted
       && view(accepted, "source", NSTextView.self).string == newest,
       "stale confirmation cannot overwrite source edited after the prompt")
service.receive(json)
expect(until { accepted.attachedSheet != nil }, "close-race fixture has an outstanding replacement")
accepted.close()
service.receive(incoming)
let afterClose = window()
expect(settled(afterClose) && view(afterClose, "source", NSTextView.self).string == incoming,
       "closed-editor confirmation cannot affect a newly opened inspector")
AppFeature.enabled = false
service.receive(json)
expect(afterClose.attachedSheet == nil && view(afterClose, "source", NSTextView.self).string == incoming,
       "disabled clipboard feature cannot hand off into an existing inspector")
afterClose.close()
AppFeature.enabled = false
service.show(text: json)
expect(!app.windows.contains { $0.isVisible }, "unavailable clipboard feature cannot open inspector")
expect(NSPasteboard.general.changeCount == pasteboardCount, "handoff and confirmation never write the system clipboard")
print("PASS: \(modelChecks) payload model and \(suite.checks - modelChecks) native UI checks; screenshots /tmp/payload-inspector-*.png")
'''
with tempfile.TemporaryDirectory(prefix="payload-inspector-ui-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    executable = folder / "check"
    sources = [
        "Sources/Vorssaint/Services/Clipboard/PayloadInspector.swift",
        "Sources/Vorssaint/Services/Clipboard/PayloadInspectorService.swift",
        "Sources/Vorssaint/Services/Clipboard/PayloadInspectorHighlighting.swift",
        "Sources/Vorssaint/Core/PayloadInspectorStrings.swift",
        "Sources/Vorssaint/Core/SharedToolActionStrings.swift",
        "Sources/Vorssaint/UI/ToolAppearance.swift",
        "Tests/PayloadInspectorTests.swift",
    ]
    subprocess.run(["swiftc", *[str(repo / path) for path in sources], str(main), "-o", str(executable)], check=True)
    if "--compile-only" not in sys.argv:
        preferences = folder / "preferences"
        preferences.mkdir()
        subprocess.run([str(executable)], check=True, timeout=120,
                       env={**os.environ, "CFFIXED_USER_HOME": str(preferences)})
