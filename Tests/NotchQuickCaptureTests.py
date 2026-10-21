#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Real temporary files + production draft service; no user vault or screen access."""
from pathlib import Path
import subprocess
import tempfile
import sys

repo = Path(__file__).resolve().parents[1]
store = repo / 'Sources/Vorssaint/Services/Notch/NotchQuickCaptureStore.swift'
service = repo / 'Sources/Vorssaint/Services/Notch/NotchQuickCaptureService.swift'
view = (repo / 'Sources/Vorssaint/UI/Notch/NotchQuickCaptureView.swift').read_text()
capture_view = view[view.index("struct NotchQuickCaptureView:"):view.index("struct NotchQuickCapturePulse:")]
right_click = view[view.index('struct NotchObsidianRightClick:'):]
code = r'''
import AppKit
import SwiftUI
import Darwin

var checks = 0
func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checks += 1
    if !condition() { fatalError(message) }
}
func fails(_ message: String, _ work: () throws -> Void) {
    do { try work(); fatalError(message) } catch { checks += 1 }
}
func waitUntil(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !predicate(), Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    expect(predicate(), "asynchronous operation must finish")
}
final class NotchService: ObservableObject {
    let geometry = Geometry()
    struct Geometry { let safeContentTop: CGFloat = 24 }
    static let shared = NotchService()
    var showingQuickCapture = true
    var opens = 0, closes = 0
    var signals: [Bool] = []
    let captureChromeWindowIDs: Set<CGWindowID> = []
    func openQuickCapture() { opens += 1; showingQuickCapture = true }
    func collapse() { closes += 1; showingQuickCapture = false }
    func signalQuickCapture(success: Bool) { signals.append(success) }
}
final class Permissions {
    static let shared = Permissions()
    var screenRecording = true
    func requestScreenRecording() {}
}
final class L10n: ObservableObject { static let shared = L10n(); let language = AppLanguage.enUS }
enum AppLanguage { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
final class ScreenshotSelectionController {
    static var isSessionOnScreen = false
    static var last: ScreenshotSelectionController?
    struct Capture { let image: CGImage }
    enum Outcome { case captured(Capture), cancelled, failed }
    let requiresDraggedRegion: Bool
    var completion: ((Outcome) -> Void)?
    init(freeze: Bool, includePointer: Bool, showLastRegion: Bool, hideVorssaintWindows: Bool,
         protectedWindowIDs: @escaping () -> Set<CGWindowID>, purpose: String?, requiresDraggedRegion: Bool) {
        self.requiresDraggedRegion = requiresDraggedRegion
        Self.last = self
    }
    func begin(completion: @escaping (Outcome) -> Void) { self.completion = completion }
    func cancel() { completion?(.cancelled) }
}
enum NotchNeonPalette { static let purple = Color.purple, blue = Color.blue }
enum NotchLayout { static let horizontalInset: CGFloat = 18, bottomInset: CGFloat = 14 }
CAPTURE_VIEW
RIGHT_CLICK

let fm = FileManager.default
let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try fm.createDirectory(at: root, withIntermediateDirectories: true)
defer { try? fm.removeItem(at: root) }
let vault = root.appendingPathComponent("vault")
let captures = root.appendingPathComponent("outside/captures")
let target = vault.appendingPathComponent("Captures.md")
let store = NotchQuickCaptureStore(vault: vault, screenshots: captures)
fails("unavailable vault must fail") { try store.append(text: "keep draft", pngs: []) }
expect(!fm.fileExists(atPath: vault.path), "unavailable vault must not be silently created")
try fm.createDirectory(at: vault, withIntermediateDirectories: true)
fails("empty text without image must not create a note") { try store.append(text: " ", pngs: []) }
expect(!fm.fileExists(atPath: target.path), "empty save creates nothing")
let date = Date(timeIntervalSince1970: 1_792_512_300)
let format = DateFormatter(); format.locale = Locale(identifier: "en_US_POSIX"); format.dateFormat = "yyyy-MM-dd HH:mm"
try store.append(text: "  hello 🪻\nnext\rline\0  ", pngs: [], at: date)
let first = try String(contentsOf: target, encoding: .utf8)
expect(first == "- \(format.string(from: date)) · hello 🪻 next line\n", "one timestamped Unicode entry")
let old = Data("existing bytes without newline".utf8)
try old.write(to: target)
try store.append(text: "second", pngs: [], at: date)
expect(try Data(contentsOf: target).starts(with: old + Data("\n- ".utf8)), "append preserves every prior byte")
let lock = Darwin.open(target.path, O_RDWR)
expect(flock(lock, LOCK_EX | LOCK_NB) == 0, "test lock")
let lockedBytes = try Data(contentsOf: target)
fails("busy append must fail without waiting") { try store.append(text: "locked", pngs: []) }
expect(try Data(contentsOf: target) == lockedBytes, "locked file remains intact")
flock(lock, LOCK_UN); Darwin.close(lock)

let context = CGContext(data: nil, width: 2, height: 2, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
context.setFillColor(NSColor.systemPurple.cgColor)
context.fill(CGRect(x: 0, y: 0, width: 2, height: 2))
let image = context.makeImage()!
let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])!
try store.append(text: "screen", pngs: [png], at: date)
try store.append(text: "screen again", pngs: [png], at: date)
let lines = try String(contentsOf: target, encoding: .utf8).split(separator: "\n")
let paths = lines.suffix(2).map { String($0.components(separatedBy: " · screenshot: ")[1]) }
expect(paths[0] != paths[1], "same-second screenshots never overwrite")
for path in paths {
    expect(path.hasPrefix(captures.path + "/") && !path.hasPrefix(vault.path + "/"), "screenshots outside vault")
    expect(try Data(contentsOf: URL(fileURLWithPath: path)) == png, "PNG contents preserved")
    expect(path.range(of: #"/\d{4}-\d{2}-\d{2}/\d{6}\.png$"#, options: .regularExpression) != nil, "exact dated path format")
}
expect(!lines.suffix(2).joined().contains("![[") && !lines.suffix(2).joined().contains("!["), "plain screenshot path")
let protectedBytes = try Data(contentsOf: target)
let insideStore = NotchQuickCaptureStore(vault: vault, screenshots: vault.appendingPathComponent("screens"))
fails("never put images inside vault") { try insideStore.append(text: "bad", pngs: [png]) }
expect(try Data(contentsOf: target) == protectedBytes, "image failure cannot append text without image")
// Force a short append at the OS boundary; rollback must preserve the old note
// and remove the newly staged screenshot while the draft can retry.
var oldLimit = rlimit()
expect(getrlimit(RLIMIT_FSIZE, &oldLimit) == 0, "read file size limit")
var limit = oldLimit
limit.rlim_cur = rlim_t(protectedBytes.count + 3)
let oldSignal = signal(SIGXFSZ, SIG_IGN)
expect(setrlimit(RLIMIT_FSIZE, &limit) == 0, "set fault injection limit")
fails("partial write must fail") { try store.append(text: String(repeating: "x", count: 1024), pngs: [png, png], at: date) }
expect(setrlimit(RLIMIT_FSIZE, &oldLimit) == 0, "restore file limit")
signal(SIGXFSZ, oldSignal)
expect(try Data(contentsOf: target) == protectedBytes, "partial append rolls back only new bytes")
let screenshotFiles = (fm.enumerator(at: captures, includingPropertiesForKeys: nil)?.allObjects as? [URL] ?? [])
    .filter { $0.pathExtension == "png" }
expect(screenshotFiles.count == 2, "partial append removes its orphan screenshot")
let alias = root.appendingPathComponent("alias")
try fm.createSymbolicLink(at: alias, withDestinationURL: vault)
fails("vault symlink root must be rejected") {
    try NotchQuickCaptureStore(vault: vault, screenshots: alias).append(text: "bad", pngs: [png])
}
try fm.moveItem(at: target, to: vault.appendingPathComponent("original.md"))
try fm.createSymbolicLink(at: target, withDestinationURL: vault.appendingPathComponent("original.md"))
fails("capture note symlink must be rejected") { try store.append(text: "bad", pngs: []) }
try fm.removeItem(at: target)
try fm.moveItem(at: vault.appendingPathComponent("original.md"), to: target)

let day = captures.appendingPathComponent("2020-01-01")
try fm.createDirectory(at: day, withIntermediateDirectories: true)
let now = Date(timeIntervalSince1970: 1_800_000_000)
func file(_ name: String, age: TimeInterval) throws -> URL {
    let url = day.appendingPathComponent(name)
    try png.write(to: url)
    try fm.setAttributes([.modificationDate: now.addingTimeInterval(-age)], ofItemAtPath: url.path)
    return url
}
let expired = try file("000001.png", age: NotchQuickCaptureStore.retention + 1)
let boundary = try file("000002.png", age: NotchQuickCaptureStore.retention)
let recent = try file("000003.png", age: 1)
let unrelated = try file("keep.png", age: NotchQuickCaptureStore.retention + 100)
let symlink = day.appendingPathComponent("000004.png")
try fm.createSymbolicLink(at: symlink, withDestinationURL: unrelated)
let folderAlias = captures.appendingPathComponent("2020-02-01")
try fm.createSymbolicLink(at: folderAlias, withDestinationURL: vault)
try store.removeExpiredScreenshots(now: now)
expect(!fm.fileExists(atPath: expired.path), "older than fourteen days removed")
for file in [boundary, recent, unrelated, symlink, target] {
    expect(fm.fileExists(atPath: file.path), "cleanup preserves boundary/new/unmanaged/symlink/vault files")
}

let draft = NotchQuickCaptureService(store: store)
let island = NotchService.shared
draft.text = "draft survives lock"
let lock2 = Darwin.open(target.path, O_RDWR); flock(lock2, LOCK_EX | LOCK_NB)
draft.save(); waitUntil { !draft.saving }
expect(draft.text == "draft survives lock" && draft.error == .save, "failed save retains draft and error")
expect(island.showingQuickCapture && island.signals.last == false, "failed save stays visible with error pulse")
flock(lock2, LOCK_UN); Darwin.close(lock2)
draft.save(); waitUntil { !draft.saving }
expect(draft.text.isEmpty && draft.error == nil && !island.showingQuickCapture && island.signals.last == true,
       "successful retry clears draft, closes and signals purple")
draft.text = "keep during region selection"
draft.captureRegion()
expect(ScreenshotSelectionController.last!.requiresDraggedRegion, "camera requires region drag")
ScreenshotSelectionController.last!.completion?(.cancelled)
expect(draft.text == "keep during region selection" && island.showingQuickCapture && draft.images.isEmpty,
       "cancel selection returns to unchanged text")
draft.captureRegion()
ScreenshotSelectionController.last!.completion?(.captured(.init(image: image)))
expect(!draft.images.isEmpty, "selected image is held in draft")
draft.captureRegion()
ScreenshotSelectionController.last!.completion?(.captured(.init(image: image)))
expect(draft.images.count == 2 && island.showingQuickCapture, "consecutive screenshots return to same capture field")
let imageLock = Darwin.open(target.path, O_RDWR); flock(imageLock, LOCK_EX | LOCK_NB)
draft.save(); waitUntil { !draft.saving }
expect(draft.images.count == 2 && draft.text == "keep during region selection", "image and text survive failed save together")
flock(imageLock, LOCK_UN); Darwin.close(imageLock)
draft.save(); waitUntil { !draft.saving }
expect(draft.images.isEmpty && draft.text.isEmpty, "successful image save clears draft")
let multiLine = try String(contentsOf: target, encoding: .utf8).split(separator: "\n").last!
expect(multiLine.components(separatedBy: " · screenshot: ").count == 3, "one ordinary capture line contains both image paths")
draft.text = "keep through lock"
draft.captureRegion()
let opened = island.opens
draft.cancelSelection()
expect(island.opens == opened && draft.text == "keep through lock", "lock/stop cancels selection without reopening or losing text")
draft.cancel()
expect(draft.text.isEmpty && !island.showingQuickCapture, "explicit Escape/cancel discards draft")

// Session storage: exact folders, stable order, no overwrite, plain summary.
let sessionVault = root.appendingPathComponent("session-vault")
try fm.createDirectory(at: sessionVault, withIntermediateDirectories: true)
let sessionTarget = sessionVault.appendingPathComponent("Captures.md")
let sessionRoot = root.appendingPathComponent("session-images")
let sessionStore = NotchQuickCaptureStore(vault: sessionVault, screenshots: sessionRoot)
let dayFormat = DateFormatter(); dayFormat.dateFormat = "yyyy-MM-dd"
let minuteFormat = DateFormatter(); minuteFormat.dateFormat = "HHmm"
let relative = dayFormat.string(from: date) + "/" + minuteFormat.string(from: date)
let emptySession = NotchQuickCaptureStore.Session(startedAt: date, label: "empty")
try sessionStore.appendSession(emptySession)
expect(!fm.fileExists(atPath: sessionTarget.path) && !fm.fileExists(atPath: sessionRoot.path), "zero screenshots create neither note nor folder")
var labelled = NotchQuickCaptureStore.Session(startedAt: date, label: "SAP-531 A.B.")
labelled = try sessionStore.saveSessionScreenshot(png, session: labelled, at: date)
labelled = try sessionStore.saveSessionScreenshot(Data("second image".utf8), session: labelled, at: date.addingTimeInterval(5))
expect(labelled.folder?.path == sessionRoot.appendingPathComponent(relative + " SAP-531 A.B").path,
       "labelled folder uses start time and safe label")
expect(labelled.count == 2, "session count advances in capture order")
expect(try Data(contentsOf: labelled.folder!.appendingPathComponent("01.png")) == png, "first session image is 01")
expect(try Data(contentsOf: labelled.folder!.appendingPathComponent("02.png")) == Data("second image".utf8), "second image is 02")
expect(!fm.fileExists(atPath: sessionTarget.path), "session shots do not create per-image notes")
try sessionStore.appendSession(labelled)
let sessionLine = "- \(format.string(from: date)) · SAP-531 A.B. · 2 screenshots · \(labelled.folder!.path)\n"
expect(try String(contentsOf: sessionTarget, encoding: .utf8) == sessionLine, "one exact session summary with plain absolute folder path")
var unlabelled = NotchQuickCaptureStore.Session(startedAt: date, label: " \n ")
unlabelled = try sessionStore.saveSessionScreenshot(png, session: unlabelled, at: date.addingTimeInterval(86_400))
expect(unlabelled.folder?.path == sessionRoot.appendingPathComponent(relative).path, "unlabelled folder uses only session start, even across midnight")
try sessionStore.appendSession(unlabelled)
expect(try String(contentsOf: sessionTarget, encoding: .utf8).hasSuffix("- \(format.string(from: date)) · 1 screenshots · \(unlabelled.folder!.path)\n"),
       "unlabelled summary omits empty label")
let collision = try sessionStore.saveSessionScreenshot(png, session: .init(startedAt: date, label: ""), at: date)
expect(collision.folder?.lastPathComponent == minuteFormat.string(from: date) + " (2)", "same-minute sessions receive distinct folders")
expect(NotchQuickCaptureStore.folderLabel(" ../SAP:/A\\B<>|?*\" \n test  ") == "SAPAB test", "unsafe filename characters and traversal stripped")
expect(NotchQuickCaptureStore.folderLabel(String(repeating: "🪻", count: 90)).utf8.count <= 120, "long Unicode labels fit filesystem limits")
var stale = labelled; stale.count = 0
fails("number collision must fail without overwriting") { _ = try sessionStore.saveSessionScreenshot(png, session: stale, at: date) }
expect(try Data(contentsOf: labelled.folder!.appendingPathComponent("02.png")) == Data("second image".utf8), "number collision preserves existing images")
fails("session images must never enter vault") { _ = try insideStore.saveSessionScreenshot(png, session: emptySession, at: date) }
// Refuse a dated directory symlink, including one outside the vault.
let linkedRoot = root.appendingPathComponent("linked-days")
try fm.createDirectory(at: linkedRoot, withIntermediateDirectories: true)
try fm.createSymbolicLink(at: linkedRoot.appendingPathComponent(dayFormat.string(from: date)), withDestinationURL: sessionRoot)
fails("session day symlink must not be traversed") {
    _ = try NotchQuickCaptureStore(vault: sessionVault, screenshots: linkedRoot)
        .saveSessionScreenshot(png, session: emptySession, at: date)
}
// Retention reaches session images, preserving recent and unrelated files.
let oldSessionFolder = day.appendingPathComponent("1234 old session")
try fm.createDirectory(at: oldSessionFolder, withIntermediateDirectories: true)
let oldSessionPNG = try file("1234 old session/01.png", age: NotchQuickCaptureStore.retention + 1)
let newSessionPNG = try file("1234 old session/02.png", age: 1)
let otherSessionFile = try file("1234 old session/notes.txt", age: NotchQuickCaptureStore.retention + 1)
try fm.createSymbolicLink(at: oldSessionFolder.appendingPathComponent("03.png"), withDestinationURL: unrelated)
let expiredSessionFolder = day.appendingPathComponent("1235")
try fm.createDirectory(at: expiredSessionFolder, withIntermediateDirectories: true)
_ = try file("1235/01.png", age: NotchQuickCaptureStore.retention + 1)
try store.removeExpiredScreenshots(now: now)
expect(!fm.fileExists(atPath: oldSessionPNG.path), "nested session image expires after fourteen days")
expect(!fm.fileExists(atPath: expiredSessionFolder.path), "empty expired session folder is removed")
for file in [newSessionPNG, otherSessionFile, oldSessionFolder.appendingPathComponent("03.png")] {
    expect(fm.fileExists(atPath: file.path), "nested cleanup preserves recent, unrelated and symlink files")
}

// Actual service with a virtual clock; screenshot callbacks stand in for the
// system selector, but disk I/O, ordering, error recovery and timers are real.
let lifecycleVault = root.appendingPathComponent("lifecycle-vault")
try fm.createDirectory(at: lifecycleVault, withIntermediateDirectories: true)
let lifecycleTarget = lifecycleVault.appendingPathComponent("Captures.md")
let lifecycleImages = root.appendingPathComponent("lifecycle-images")
var clock = Date()
let sessionDraft = NotchQuickCaptureService(store: .init(vault: lifecycleVault, screenshots: lifecycleImages), now: { clock })
func capture(_ service: NotchQuickCaptureService) {
    service.captureRegion()
    ScreenshotSelectionController.last!.completion?(.captured(.init(image: image)))
    waitUntil { !service.saving }
}
func summaryCount() throws -> Int {
    guard fm.fileExists(atPath: lifecycleTarget.path) else { return 0 }
    return try String(contentsOf: lifecycleTarget, encoding: .utf8).split(separator: "\n").count
}
// Reproduce four screenshots -> Stop -> Start: all previews must stay in
// the bottom strip until Save/Cancel, while their files remain on disk.
let previewVault = root.appendingPathComponent("preview-vault")
try fm.createDirectory(at: previewVault, withIntermediateDirectories: true)
let previewTarget = previewVault.appendingPathComponent("Captures.md")
let previewDraft = NotchQuickCaptureService(store: .init(vault: previewVault, screenshots: root.appendingPathComponent("preview-images")))
previewDraft.startSession()
for _ in 0..<4 { capture(previewDraft) }
let previewFolder = previewDraft.session!.folder!
expect(previewDraft.images.count == 4, "session screenshots must remain available to the bottom thumbnail strip")
let previewIDs = previewDraft.images.map(\.id)
expect(previewDraft.images.compactMap(\.file).map(\.lastPathComponent) == ["01.png", "02.png", "03.png", "04.png"],
       "saved thumbnail paths match capture order")
previewDraft.removeImage(previewIDs[0])
expect(previewDraft.images.map(\.id) == previewIDs, "saved session previews cannot be removed as unsaved attachments")
previewDraft.stopSession(); waitUntil { !previewDraft.saving }
expect(previewDraft.images.count == 4 && island.showingQuickCapture, "Stop keeps all four previews and the capture field open")
previewDraft.startSession()
expect(previewDraft.images.map(\.id) == previewIDs && previewDraft.session?.count == 0, "Start again keeps the previous session thumbnails")
capture(previewDraft)
expect(previewDraft.images.count == 5, "new session screenshot joins the existing thumbnail strip")
previewDraft.stopSession(); waitUntil { !previewDraft.saving }
let beforePreviewSave = try Data(contentsOf: previewTarget)
expect(previewDraft.canSave, "saved screenshots alone still allow Save to close the capture field")
previewDraft.save(); waitUntil { !previewDraft.saving }
expect(previewDraft.images.isEmpty && !island.showingQuickCapture, "Save clears previews and closes the capture field")
expect(try Data(contentsOf: previewTarget) == beforePreviewSave, "Save never re-saves already recorded session screenshots")
expect(try fm.contentsOfDirectory(atPath: previewFolder.path).sorted() == ["01.png", "02.png", "03.png", "04.png"],
       "clearing previews never deletes saved screenshots")
previewDraft.startSession(); capture(previewDraft)
previewDraft.stopSession(); waitUntil { !previewDraft.saving }
let beforePreviewCancel = try Data(contentsOf: previewTarget)
previewDraft.cancel()
expect(previewDraft.images.isEmpty && !island.showingQuickCapture, "Cancel clears previews and closes")
expect(try Data(contentsOf: previewTarget) == beforePreviewCancel, "Cancel leaves completed session entries intact")

// Keep previews light while preserving the full-resolution saved PNG.
let largeContext = CGContext(data: nil, width: 1600, height: 900, bitsPerComponent: 8, bytesPerRow: 0,
                             space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
previewDraft.startSession(); previewDraft.captureRegion()
ScreenshotSelectionController.last!.completion?(.captured(.init(image: largeContext.makeImage()!)))
waitUntil { !previewDraft.saving }
let smallPreview = previewDraft.images.last!
expect(max(smallPreview.image.width, smallPreview.image.height) <= 176, "saved session previews do not retain full-resolution buffers")
let originalImage = NSBitmapImageRep(data: try Data(contentsOf: smallPreview.file!))!
expect(originalImage.pixelsWide == 1600 && originalImage.pixelsHigh == 900, "thumbnail scaling never resizes the saved screenshot")
previewDraft.stopSession(); waitUntil { !previewDraft.saving }
previewDraft.cancel()

sessionDraft.sessionLabel = "SAP-531 A.B."
sessionDraft.text = "a thought stays separate"
sessionDraft.startSession()
expect(sessionDraft.session?.count == 0 && !fm.fileExists(atPath: lifecycleTarget.path), "one action starts labelled session without a note")
capture(sessionDraft); capture(sessionDraft)
expect(sessionDraft.session?.count == 2 && sessionDraft.images.count == 2 && sessionDraft.images.allSatisfy { $0.file != nil } && sessionDraft.pendingSessionImage == nil,
       "session captures persist immediately and update count without draft attachments")
let sessionFolder = sessionDraft.session!.folder!
expect(try fm.contentsOfDirectory(atPath: sessionFolder.path).sorted() == ["01.png", "02.png"], "service saves consecutive numbered images")
expect(try summaryCount() == 0, "session has no intermediate vault lines")
sessionDraft.stopSession(); sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
sessionDraft.stopSession()
expect(try summaryCount() == 1 && sessionDraft.session == nil, "repeated stop yields exactly one session entry")
expect(sessionDraft.text == "a thought stays separate" && island.showingQuickCapture, "stopping keeps unrelated text draft visible")
expect(island.signals.last == true, "session stop confirms with purple pulse")
sessionDraft.save(); waitUntil { !sessionDraft.saving }
expect(try summaryCount() == 2, "text captures still append independently")
expect(try String(contentsOf: lifecycleTarget, encoding: .utf8).hasSuffix(" · a thought stays separate\n"),
       "saving text never appends the saved session images again")
island.openQuickCapture()
sessionDraft.startSession(); sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
expect(try summaryCount() == 2, "zero-shot stop writes nothing")
expect(island.showingQuickCapture, "empty stop leaves capture field open for a thought")
sessionDraft.startSession()
clock = clock.addingTimeInterval(1800)
sessionDraft.closeSessionIfIdle(); waitUntil { !sessionDraft.saving }
expect(try sessionDraft.session == nil && summaryCount() == 2, "zero-shot session auto-closes without writing")
sessionDraft.startSession(); capture(sessionDraft)
clock = clock.addingTimeInterval(1799)
sessionDraft.closeSessionIfIdle()
expect(sessionDraft.session != nil && !sessionDraft.saving, "session remains open before idle deadline")
capture(sessionDraft)
clock = clock.addingTimeInterval(1799)
sessionDraft.closeSessionIfIdle()
expect(sessionDraft.session?.count == 2 && !sessionDraft.saving, "a new capture resets the idle deadline")
clock = clock.addingTimeInterval(1)
sessionDraft.closeSessionIfIdle(); sessionDraft.closeSessionIfIdle(); waitUntil { !sessionDraft.saving }
expect(try sessionDraft.session == nil && summaryCount() == 3, "30-minute timeout appends exactly one summary")
// Failure at the summary boundary keeps session/count/text and permits retry.
sessionDraft.startSession(); capture(sessionDraft)
sessionDraft.text = "keep this thought"
let summaryLock = Darwin.open(lifecycleTarget.path, O_RDWR); flock(summaryLock, LOCK_EX | LOCK_NB)
clock = clock.addingTimeInterval(1800)
sessionDraft.closeSessionIfIdle(); waitUntil { !sessionDraft.saving }
expect(sessionDraft.session?.count == 1 && sessionDraft.error == .save && sessionDraft.text == "keep this thought",
       "auto-close failure preserves session and draft")
expect(try island.showingQuickCapture && island.signals.last == false && summaryCount() == 3, "failed auto-close shows error without partial summary")
flock(summaryLock, LOCK_UN); Darwin.close(summaryLock)
sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
expect(try sessionDraft.session == nil && summaryCount() == 4, "manual retry after failed timeout appends once")
// A failed PNG is retained in memory. Stop retries it, and a failed summary
// after that retry cannot cause the image to be written twice.
sessionDraft.text = "failed image draft"
sessionDraft.startSession()
let imagesBackup = root.appendingPathComponent("lifecycle-images-backup")
try fm.moveItem(at: lifecycleImages, to: imagesBackup)
try Data("obstruction".utf8).write(to: lifecycleImages)
capture(sessionDraft)
expect(sessionDraft.pendingSessionImage != nil && sessionDraft.session?.count == 0 && sessionDraft.error == .save,
       "failed image stays available for retry without incrementing count")
sessionDraft.cancel()
expect(sessionDraft.pendingSessionImage != nil && sessionDraft.text == "failed image draft", "cancel cannot discard a failed session capture")
try fm.removeItem(at: lifecycleImages)
try fm.moveItem(at: imagesBackup, to: lifecycleImages)
let previewsBeforeRetry = sessionDraft.images.count
let retryLock = Darwin.open(lifecycleTarget.path, O_RDWR); flock(retryLock, LOCK_EX | LOCK_NB)
sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
expect(sessionDraft.pendingSessionImage == nil && sessionDraft.session?.count == 1 && sessionDraft.error == .save,
       "successful image retry survives a subsequent summary failure")
sessionDraft.text = ""
expect(!sessionDraft.canSave, "preview-only Save cannot dismiss a failed session summary as a success")
let retryFolder = sessionDraft.session!.folder!
flock(retryLock, LOCK_UN); Darwin.close(retryLock)
sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
expect(try fm.contentsOfDirectory(atPath: retryFolder.path) == ["01.png"], "summary retry never duplicates the recovered screenshot")
expect(try summaryCount() == 5, "retry adds only one session summary")
expect(sessionDraft.images.count == previewsBeforeRetry + 1, "failed summary retry does not duplicate the saved thumbnail")
sessionDraft.text = ""
island.openQuickCapture()
sessionDraft.startSession(); capture(sessionDraft)
sessionDraft.stopSession(); waitUntil { !sessionDraft.saving }
expect(island.showingQuickCapture && sessionDraft.text.isEmpty && sessionDraft.session == nil,
       "stopping screenshots with no draft leaves an empty editor ready for new text")
// Timer must resume after the system cancels a selection (lock/sleep).
sessionDraft.text = ""
sessionDraft.startSession(); capture(sessionDraft)
sessionDraft.captureRegion()
clock = clock.addingTimeInterval(1800)
sessionDraft.closeSessionIfIdle()
expect(sessionDraft.isSelecting && !sessionDraft.saving, "auto-close defers while selecting")
let beforeCancel = island.opens
sessionDraft.cancelSelection()
waitUntil { sessionDraft.session == nil }
expect(try island.opens == beforeCancel && summaryCount() == 7, "overdue timer closes after selection cancellation without reopening")

// Native event routing: only a right click in this icon consumes an event.
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 100, height: 60), styleMask: .titled,
                      backing: .buffered, defer: false)
let area = NotchObsidianRightClick.Area(frame: NSRect(x: 10, y: 10, width: 22, height: 26))
var homeOpens = 0
area.action = { homeOpens += 1 }
window.contentView!.addSubview(area)
window.orderFrontRegardless()
func click(_ type: NSEvent.EventType, _ point: NSPoint) -> NSEvent {
    NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: 1,
                      windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
}
expect(!area.handle(click(.leftMouseDown, NSPoint(x: 15, y: 15))), "left click remains native")
expect(!area.handle(click(.rightMouseDown, NSPoint(x: 80, y: 15))), "outside click remains native")
expect(area.handle(click(.rightMouseDown, NSPoint(x: 15, y: 15))) && homeOpens == 1, "direct right click opens HOME once")
area.isHidden = true
expect(!area.handle(click(.rightMouseDown, NSPoint(x: 15, y: 15))), "hidden button cannot intercept clicks")
area.stop(); window.orderOut(nil)
// Render only the new field, without capturing any user windows or saving a capture.
draft.text = "A thought to sort later: keep the useful details here while the current window stays open. This should read as a small paragraph, with capture and save at the bottom."
if CommandLine.arguments.contains("--active") {
    draft.sessionLabel = "SAP-531 A.B."
    capture(draft); capture(draft)
    draft.startSession(); capture(draft); capture(draft)
}
let content = NotchQuickCaptureView(service: island, draft: draft)
    .frame(width: 440, height: 270, alignment: .top)
    .foregroundStyle(.white).background(.black).environment(\.colorScheme, .dark)
let host = NSHostingView(rootView: content)
host.frame = NSRect(x: 0, y: 0, width: 440, height: 270)
window.contentView = host
window.setContentSize(host.frame.size)
window.orderFrontRegardless()
RunLoop.main.run(until: Date().addingTimeInterval(0.15))
host.layoutSubtreeIfNeeded()
expect(host.fittingSize.height <= 270, "capture field fits its island height")
if CommandLine.arguments.count > 1, let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
    host.cacheDisplay(in: host.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
}
if CommandLine.arguments.contains("--active") {
    draft.stopSession(); waitUntil { !draft.saving }
    expect(island.showingQuickCapture, "stopping a screenshot session leaves the capture field open")
    for attachment in draft.images { draft.removeImage(attachment.id) }
}
// Exercise the actual SwiftUI editor with window-local key events. All writes
// still use the injected temporary vault, never the user's capture file.
func textView(in view: NSView) -> NSTextView? {
    if let text = view as? NSTextView { return text }
    for child in view.subviews { if let text = textView(in: child) { return text } }
    return nil
}
let editor = textView(in: host)!
expect(editor.isHorizontallyResizable == false, "paragraph wraps instead of growing horizontally")
window.makeKeyAndOrderFront(nil)
window.makeFirstResponder(editor)
editor.setSelectedRange(NSRange(location: (editor.string as NSString).length, length: 0))
func key(_ code: UInt16, _ flags: NSEvent.ModifierFlags = []) {
    let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: flags, timestamp: 1,
                                windowNumber: window.windowNumber, context: nil,
                                characters: code == 53 ? "\u{1b}" : "\r",
                                charactersIgnoringModifiers: code == 53 ? "\u{1b}" : "\r",
                                isARepeat: false, keyCode: code)!
    app.sendEvent(event)
    RunLoop.main.run(until: Date().addingTimeInterval(0.05))
}
key(36, .shift)
expect(draft.text.hasSuffix("\n") && !draft.saving, "Shift-Enter inserts a line without saving")
key(36)
waitUntil { !draft.saving }
expect(draft.text.isEmpty && island.signals.last == true, "Enter in the paragraph saves instead of inserting a line")
draft.text = "cancel this paragraph"
RunLoop.main.run(until: Date().addingTimeInterval(0.05))
window.makeFirstResponder(editor)
key(53)
expect(draft.text.isEmpty && !island.showingQuickCapture, "Escape in the paragraph cancels")
// Render the running state too, including multiple ordinary attachments.
draft.text = "Keep these details while the session gathers screenshots."
capture(draft); capture(draft)
let removable = draft.images[0].id
draft.removeImage(removable)
expect(draft.images.count == 1 && draft.images[0].id != removable, "remove only the selected ordinary attachment")
capture(draft)
draft.sessionLabel = "SAP-531 A.B."
draft.startSession(); capture(draft); capture(draft)
expect(draft.images.count == 4 && draft.images.filter { $0.file == nil }.count == 2 && draft.session?.count == 2, "starting a session preserves existing ordinary attachments")
let activeHost = NSHostingView(rootView: content)
activeHost.frame = host.frame
window.contentView = activeHost
window.orderFrontRegardless()
RunLoop.main.run(until: Date().addingTimeInterval(0.15))
activeHost.layoutSubtreeIfNeeded()
expect(activeHost.fittingSize.height <= 270, "running session and attachments fit the capture panel")
draft.stopSession(); waitUntil { !draft.saving }
window.orderOut(nil)
print("PASS: \(checks) quick capture checks")
'''.replace('RIGHT_CLICK', right_click).replace('CAPTURE_VIEW', capture_view)
# Throwing file reads are evaluated before the nonthrowing expectation closure.
code = code.replace('func expect(_ condition: @autoclosure () -> Bool, _ message: String)',
                    'func expect(_ condition: Bool, _ message: String)').replace('if !condition()', 'if !condition')
with tempfile.TemporaryDirectory(prefix='notch-quick-capture-tests-') as temporary:
    source = Path(temporary) / 'main.swift'
    source.write_text(code)
    binary = Path(temporary) / 'checks'
    subprocess.run(['xcrun', 'swiftc', '-target', 'arm64-apple-macosx14.0', '-sdk',
                    '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk', '-Xfrontend',
                    '-interface-compiler-version', '-Xfrontend', '6.3.2', str(store), str(service),
                    str(repo / 'Sources/Vorssaint/Core/NotchQuickCaptureStrings.swift'), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary), *sys.argv[1:]], check=True)
