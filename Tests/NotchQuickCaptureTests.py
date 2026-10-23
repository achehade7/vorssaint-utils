#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Native capture UI with production state/storage, temporary vaults and mocked pixels.

This opens windows and sends window-local editor events. Run only when native
interaction is allowed; lifecycle/fault tests live in the headless suites.
Optional CLI: [screenshot.png] [--active], retained for the island updater.
"""
from quick_capture_fixture import run

run(r'''
var checks = 0
func expect(_ value: Bool, _ message: String) {
    checks += 1
    precondition(value, message)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let enhancedAttribute = "AXEnhancedUserInterface"
let getter = NSSelectorFromString("accessibilityAttributeValue:")
let setter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
let previousEnhanced = app.perform(getter, with: enhancedAttribute)?.takeUnretainedValue()
app.perform(setter, with: true, with: enhancedAttribute)
defer { app.perform(setter, with: previousEnhanced, with: enhancedAttribute) }
func drain(_ interval: TimeInterval = 0.06) {
    let deadline = Date().addingTimeInterval(interval)
    while Date() < deadline {
        if let event = app.nextEvent(matching: .any, until: Date().addingTimeInterval(0.002), inMode: .default, dequeue: true) {
            app.sendEvent(event)
        }
        RunLoop.main.run(until: Date().addingTimeInterval(0.002))
    }
}
func waitUntil(_ message: @autoclosure () -> String = "asynchronous operation finishes", _ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !predicate(), Date() < deadline { drain(0.01) }
    expect(predicate(), message())
}
func find(_ element: AnyObject, id: String) -> AnyObject? {
    if element.accessibilityIdentifier?() == id { return element }
    for child in element.accessibilityChildren?() ?? [] {
        if let match = find(child as AnyObject, id: id) { return match }
    }
    return nil
}
func press(_ element: AnyObject, id: String) -> Bool {
    find(element, id: id)?.accessibilityPerformPress?() ?? false
}
func textView(in view: NSView) -> NSTextView? {
    if let text = view as? NSTextView { return text }
    for child in view.subviews { if let text = textView(in: child) { return text } }
    return nil
}
let files = FileManager.default
let root = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
let vault = root.appendingPathComponent("vault")
try files.createDirectory(at: vault.appendingPathComponent("meetings"), withIntermediateDirectories: true)
defer { try? files.removeItem(at: root) }
let meetingFile = vault.appendingPathComponent("meetings/2026-10-23 Design sync.md")
try Data("# Design sync\n".utf8).write(to: meetingFile)
let clock = Date(timeIntervalSince1970: 1_792_750_800)
let choice = NotchQuickCaptureService.MeetingChoice(id: "ongoing", title: "Design sync · SAP-531 and capture workflows",
    input: .init(identity: "event", title: "Design sync", start: clock.addingTimeInterval(-1800),
                 end: clock.addingTimeInterval(1800), people: []))
var recognition: Result<String, Error> = .success("Column A\n00123\nA line with spaces")
let draft = NotchQuickCaptureService(store: .init(vault: vault, screenshots: root.appendingPathComponent("images")),
    now: { clock }, loadMeetings: { _, complete in complete(.success([choice])) },
    resolveNote: { _, complete in complete(.success(meetingFile)) },
    recognize: { _, complete in complete(recognition) })
let island = NotchService.shared
let window = NSPanel(contentRect: NSRect(x: 100, y: 100, width: 440, height: 298),
                     styleMask: [.titled, .closable, .nonactivatingPanel], backing: .buffered, defer: false)
window.isReleasedWhenClosed = false
island.presentationWindow = window
let selectorWindow = NSPanel(contentRect: NSRect(x: 150, y: 150, width: 120, height: 90),
                             styleMask: [.titled, .closable, .nonactivatingPanel], backing: .buffered, defer: false)
selectorWindow.isReleasedWhenClosed = false
defer { draft.stop(); window.orderOut(nil); selectorWindow.orderOut(nil) }
let pixels = CGContext(data: nil, width: 320, height: 180, bitsPerComponent: 8, bytesPerRow: 0,
                       space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
pixels.setFillColor(NSColor.systemPurple.cgColor); pixels.fill(CGRect(x: 0, y: 0, width: 320, height: 180))
let image = pixels.makeImage()!
func screenshot() {
    draft.receiveImage(image, capturedAt: clock.addingTimeInterval(Double(draft.imageCount)))
    waitUntil { draft.pendingCount == 0 }
}
let content = NotchQuickCaptureView(service: island, draft: draft)
    .frame(width: 440, height: 298, alignment: .top)
    .foregroundStyle(.white).background(.black).environment(\.colorScheme, .dark)
let host = NSHostingView(rootView: content)
host.frame = NSRect(x: 0, y: 0, width: 440, height: 298)
window.contentView = host
window.makeKeyAndOrderFront(nil); app.activate(ignoringOtherApps: true)
func editorState() -> String {
    let editor = textView(in: host)
    return "key=\(window.isKeyWindow), focused=\(window.firstResponder === editor), "
        + "textMatches=\(editor?.string == draft.text), caret=\(String(describing: editor?.selectedRange())), "
        + "selecting=\(draft.isSelecting)"
}
func focusEditor() -> NSTextView {
    window.makeKeyAndOrderFront(nil)
    waitUntil("paragraph is ready before focusing: \(editorState())") {
        guard let editor = textView(in: host) else { return false }
        return window.isKeyWindow && editor.window === window && editor.isEditable && editor.string == draft.text
    }
    let editor = textView(in: host)!
    expect(window.makeFirstResponder(editor) && window.firstResponder === editor,
           "paragraph accepts keyboard focus: \(editorState())")
    editor.setSelectedRange(NSRange(location: (editor.string as NSString).length, length: 0))
    return editor
}
func reopen() {
    island.openQuickCapture(); draft.open()
    _ = focusEditor(); drain()
}
func key(_ code: UInt16, _ flags: NSEvent.ModifierFlags = [], target: NSWindow? = nil) {
    let destination = target ?? window
    let characters: String
    switch code {
    case 53: characters = "\u{1b}"
    case 5: characters = "g"
    case 15: characters = "r"
    case 17: characters = "t"
    case 1: characters = "s"
    case 6: characters = "z"
    case 13: characters = "w"
    default: characters = "\r"
    }
    for type in [NSEvent.EventType.keyDown, .keyUp] {
        let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: flags,
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: destination.windowNumber,
            context: nil, characters: characters, charactersIgnoringModifiers: characters,
            isARepeat: false, keyCode: code)!
        app.sendEvent(event)
    }
    drain()
}
func finishSelector() {
    guard let selector = ScreenshotSelectionController.last else { preconditionFailure("selector exists") }
    selector.onSelectionBegan?([])
    selector.complete(.captured(.init(image: image, capturedAt: clock)))
}
func fit(_ state: String) {
    drain(); host.layoutSubtreeIfNeeded()
    expect(host.fittingSize.height <= 298, state + " fits the island height")
    let surface = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
    for id in ["text", "region", "ocr", "undo", "discard", "save", "count"] {
        guard let element = find(host, id: "notch.quickCapture." + id),
              let frame = element.accessibilityFrame?(), !frame.isEmpty else {
            preconditionFailure(state + " has visible " + id)
        }
        expect(surface.contains(frame), state + " keeps " + id + " inside the island")
    }
    expect(textView(in: host)!.isHorizontallyResizable == false, state + " wraps the thought")
}
func currentPreviewWindow() -> NSWindow? {
    app.windows.first { $0 !== window && $0 !== selectorWindow && $0.isVisible
        && $0.contentView.flatMap { find($0, id: "notch.quickCapture.previewText") } != nil }
}
func openTextPreview() -> (NSWindow, NSTextView) {
    let extractID = "notch.quickCapture.extract." + draft.extracts[0].id.uuidString
    expect(press(host, id: extractID), "OCR thumbnail opens its preview")
    waitUntil { currentPreviewWindow() != nil }
    let preview = currentPreviewWindow()!
    guard let editor = textView(in: preview.contentView!) else { preconditionFailure("OCR preview has a native editor") }
    waitUntil { preview.firstResponder === editor }
    expect(editor.isEditable, "OCR preview is editable and automatically focused")
    return (preview, editor)
}

// Actual paragraph editing and command routing, with no capture of user windows.
draft.text = "A thought about the capture flow."
let editor = focusEditor(); editor.undoManager?.removeAllActions()
var expectedTyping = draft.text
for (code, letter): (UInt16, String) in [(5, "g"), (15, "r"), (17, "t")] {
    key(code)
    expectedTyping += letter
    waitUntil("ordinary \(letter) reaches the paragraph: \(editorState())") {
        editor.string == expectedTyping && draft.text == expectedTyping
    }
    expect(!draft.isSelecting, "typing \(letter) without Command does not start capture")
}
let menu = NSMenu(); let editItem = NSMenuItem(); menu.addItem(editItem)
let editMenu = NSMenu(title: "Edit"); editItem.submenu = editMenu
editMenu.addItem(NSMenuItem(title: "Undo", action: Selector(("undo:")), keyEquivalent: "z"))
let windowItem = NSMenuItem(); menu.addItem(windowItem)
let windowMenu = NSMenu(title: "Window"); windowItem.submenu = windowMenu
windowMenu.addItem(NSMenuItem(title: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"))
app.mainMenu = menu
screenshot(); _ = focusEditor()
let beforeTyping = draft.text
editor.undoManager?.removeAllActions()
editor.insertText("temporary typing", replacementRange: editor.selectedRange()); drain()
key(6, .command)
expect(draft.text == beforeTyping && draft.imageCount == 1, "Cmd-Z undoes typing without removing a screenshot")
key(6, [.command, .control]); waitUntil { draft.pendingCount == 0 }
expect(draft.imageCount == 0 && draft.text == beforeTyping, "Cmd-Control-Z undoes the latest screenshot")
key(36, .shift)
expect(draft.text.hasSuffix("\n") && !draft.saving, "Shift-Enter inserts a line")
key(36); waitUntil { !draft.saving }
expect(draft.text.isEmpty && draft.imageCount == 0 && island.signals.last == true,
       "Enter publishes and resets the draft")
reopen(); draft.text = "Saved with the command shortcut"; drain(); _ = focusEditor()
key(1, .command); waitUntil { !draft.saving }
expect(draft.text.isEmpty && island.signals.last == true, "Cmd-S publishes the capture")
reopen(); draft.text = "Keep this thought on Escape"; screenshot(); drain(); _ = focusEditor()
let retainedID = draft.images[0].id
key(53)
expect(!island.showingQuickCapture && draft.text == "Keep this thought on Escape" && draft.images[0].id == retainedID,
       "Escape hides without clearing text or attachments")
window.orderOut(nil); reopen()
expect(draft.text == "Keep this thought on Escape" && draft.images[0].id == retainedID,
       "reopening resumes the same capture")

key(5, .command)
expect(draft.capturingGroup && draft.isSelecting && ScreenshotSelectionController.last?.freeze == false,
       "Cmd-G starts repeated live selection from the focused paragraph")
finishSelector(); waitUntil { draft.isSelecting && draft.imageCount == 2 }
ScreenshotSelectionController.last!.protectedWindowIDs = [CGWindowID(selectorWindow.windowNumber)]
selectorWindow.makeKeyAndOrderFront(nil)
key(53, target: selectorWindow)
expect(!draft.capturingGroup && !draft.isSelecting && draft.imageCount == 2 && island.showingQuickCapture,
       "selector Escape pauses repeated capture and keeps every image")
selectorWindow.orderOut(nil); reopen()
key(15, .command)
expect(draft.isSelecting && !draft.capturingGroup && ScreenshotSelectionController.last!.freeze,
       "Cmd-R takes a single frozen region after a repeated capture")
finishSelector(); waitUntil { draft.pendingCount == 0 }
expect(draft.imageCount == 3 && !draft.isSelecting && island.showingQuickCapture,
       "one region returns to the editor without restarting repetition")
reopen()
let pasteboardBefore = NSPasteboard.general.changeCount
key(17, .command)
expect(draft.isSelecting && !draft.capturingGroup, "Cmd-T opens one text-region selection")
finishSelector(); waitUntil { draft.pendingCount == 0 }
expect(draft.extracts.count == 1 && draft.extracts[0].text == "Column A\n00123\nA line with spaces",
       "text-region capture keeps multiline OCR")
expect(draft.imageCount == 3 && NSPasteboard.general.changeCount == pasteboardBefore,
       "capture OCR adds no image and leaves the clipboard unchanged")
reopen(); fit("meeting + images + OCR")
if let output = CommandLine.arguments.dropFirst().first(where: { !$0.hasPrefix("--") }),
   let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
    host.cacheDisplay(in: host.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
}
let (previewWindow, previewEditor) = openTextPreview()
let originalExtract = draft.extracts[0], originalImages = draft.images.map(\.id)
let originalThought = draft.text
expect(previewEditor.string == originalExtract.text, "preview exposes the exact multiline extract")
previewEditor.setSelectedRange(NSRange(location: (previewEditor.string as NSString).length, length: 0))
previewEditor.undoManager?.removeAllActions()
previewEditor.insertText(" temporary typo", replacementRange: previewEditor.selectedRange()); drain()
expect(draft.extracts[0].text.hasSuffix(" temporary typo"), "typing immediately updates the draft extract")
key(6, .command, target: previewWindow)
expect(draft.extracts[0].text == originalExtract.text && draft.images.map(\.id) == originalImages,
       "Cmd-Z in OCR preview undoes text without removing an image")
let savesBeforePreviewEnter = island.signals.count
key(36, target: previewWindow)
expect(draft.extracts[0].text == originalExtract.text + "\n" && !draft.saving
       && island.signals.count == savesBeforePreviewEnter, "Enter in OCR preview inserts a newline without saving")
previewEditor.insertText("Edited OCR answer", replacementRange: previewEditor.selectedRange()); drain()
let editedExtract = originalExtract.text + "\nEdited OCR answer"
expect(draft.extracts[0].text == editedExtract && draft.extracts[0].id == originalExtract.id
       && draft.extracts[0].capturedAt == originalExtract.capturedAt, "OCR editing preserves capture identity and time")
key(13, .command, target: previewWindow)
waitUntil { currentPreviewWindow() == nil }
expect(draft.extracts[0].text == editedExtract && draft.images.map(\.id) == originalImages
       && draft.text == originalThought && island.showingQuickCapture,
       "Cmd-W closes only the OCR preview and retains its edits and the full draft")
reopen()
let (reopenedPreview, reopenedEditor) = openTextPreview()
expect(reopenedEditor.string == editedExtract, "reopening OCR preview retains live edits")
key(53, target: reopenedPreview)
waitUntil { currentPreviewWindow() == nil }
expect(draft.extracts[0].text == editedExtract && draft.images.map(\.id) == originalImages
       && island.showingQuickCapture, "preview Escape retains edits and leaves the draft open")
// Shortcut monitors must ignore another native window in this same process.
let foreignEditor = NSTextView(frame: NSRect(x: 0, y: 0, width: 120, height: 90))
selectorWindow.contentView = foreignEditor
selectorWindow.makeKeyAndOrderFront(nil); selectorWindow.makeFirstResponder(foreignEditor)
let savesBeforeForeignKeys = island.signals.count
key(1, .command, target: selectorWindow); key(13, .command, target: selectorWindow)
expect(draft.extracts[0].text == editedExtract && draft.images.map(\.id) == originalImages
       && draft.text == originalThought && island.signals.count == savesBeforeForeignKeys,
       "Cmd-S and Cmd-W in an unrelated window cannot save or discard the capture")
expect(!selectorWindow.isVisible, "unrelated-window Cmd-W keeps native Window Close behavior")
selectorWindow.orderOut(nil)
reopen()
recognition = .failure(CocoaError(.fileReadCorruptFile))
draft.receiveTextImage(image, capturedAt: clock)
expect(draft.hasFailedAttachments && !draft.canSave, "failed OCR requires explicit retry or removal")
let (blockedPreview, _) = openTextPreview()
let savesBeforeBlockedPreview = island.signals.count
key(1, .command, target: blockedPreview)
expect(currentPreviewWindow() === blockedPreview && draft.extracts[0].text == editedExtract
       && !draft.saving && island.signals.count == savesBeforeBlockedPreview,
       "rejected Cmd-S keeps the OCR preview open and preserves edits")
key(13, .command, target: blockedPreview)
waitUntil { currentPreviewWindow() == nil }
reopen()
for language in AppLanguage.allCases {
    L10n.shared.language = language
    fit("full capture with error / " + language.rawValue)
}
L10n.shared.language = .enUS; drain()
expect(press(host, id: "notch.quickCapture.discard"), "explicit Discard is reachable through its native action")
drain()
expect(draft.text.isEmpty && draft.images.isEmpty && draft.extracts.isEmpty && draft.meeting == nil
       && draft.pendingCount == 0 && !draft.capturingGroup && !island.showingQuickCapture,
       "Discard resets every part of the current capture")

// Saving from OCR preview publishes the entire capture with edited text.
reopen(); draft.text = "Thought saved from OCR preview"; screenshot()
recognition = .success("Original OCR to correct")
draft.receiveTextImage(image, capturedAt: clock); waitUntil { draft.pendingCount == 0 }; drain()
let (savingPreview, savingEditor) = openTextPreview()
let correctedText = "Corrected OCR for publication\nsecond line"
savingEditor.selectAll(nil); savingEditor.insertText(correctedText, replacementRange: savingEditor.selectedRange()); drain()
let note = vault.appendingPathComponent("Captures.md")
let beforePreviewSave = try String(contentsOf: note, encoding: .utf8)
key(1, .command, target: savingPreview)
waitUntil { !draft.saving && currentPreviewWindow() == nil }
let afterPreviewSave = try String(contentsOf: note, encoding: .utf8)
expect(draft.text.isEmpty && draft.images.isEmpty && draft.extracts.isEmpty && island.signals.last == true,
       "accepted Cmd-S closes OCR preview and resets the published capture")
let savedBlock = String(afterPreviewSave.dropFirst(beforePreviewSave.count))
expect(afterPreviewSave.hasPrefix(beforePreviewSave) && savedBlock.contains("Thought saved from OCR preview")
       && savedBlock.contains(correctedText) && savedBlock.contains("01.png")
       && !savedBlock.contains("Original OCR to correct"), "preview save publishes edited OCR, thought and image together")
expect(NSPasteboard.general.changeCount == pasteboardBefore, "OCR edits, undo and preview save leave the clipboard unchanged")

// Main-editor Cmd-W is explicit discard, unlike closing the OCR preview.
reopen(); draft.text = "Discard this complete capture"; screenshot()
draft.receiveTextImage(image, capturedAt: clock); waitUntil { draft.pendingCount == 0 }; drain(); _ = focusEditor()
key(13, .command)
expect(draft.text.isEmpty && draft.images.isEmpty && draft.extracts.isEmpty && draft.meeting == nil
       && !island.showingQuickCapture, "Cmd-W in the main editor discards the full capture")
expect(window.isVisible, "main Cmd-W is consumed before native Window Close")
let afterMainClose = try String(contentsOf: note, encoding: .utf8)
expect(afterMainClose == afterPreviewSave, "main-editor Cmd-W does not publish the discarded draft")

// The icon's secondary-click listener remains limited to its own visible window.
window.orderOut(nil)
let iconWindow = NSPanel(contentRect: NSRect(x: 100, y: 100, width: 100, height: 60),
                         styleMask: [.titled, .nonactivatingPanel], backing: .buffered, defer: false)
let area = NotchObsidianRightClick.Area(frame: NSRect(x: 10, y: 10, width: 22, height: 26))
var homeOpens = 0
area.action = { homeOpens += 1 }
iconWindow.contentView!.addSubview(area); iconWindow.orderFrontRegardless(); drain()
func click(_ type: NSEvent.EventType, _ point: NSPoint, target: NSWindow = iconWindow) -> NSEvent {
    NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
        windowNumber: target.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
}
expect(!area.handle(click(.leftMouseDown, NSPoint(x: 15, y: 15))), "left click stays native")
expect(!area.handle(click(.rightMouseDown, NSPoint(x: 80, y: 15))), "right click outside icon stays native")
expect(!area.handle(click(.rightMouseDown, NSPoint(x: 15, y: 15), target: window)), "other windows cannot open HOME")
expect(area.handle(click(.rightMouseDown, NSPoint(x: 15, y: 15))) && homeOpens == 1, "own icon right click opens HOME")
area.isHidden = true
expect(!area.handle(click(.rightMouseDown, NSPoint(x: 15, y: 15))), "hidden icon cannot intercept clicks")
area.stop(); iconWindow.orderOut(nil)
print("PASS: \(checks) native quick capture checks; all vault and acquisition boundaries isolated")
''', include_view=True)
