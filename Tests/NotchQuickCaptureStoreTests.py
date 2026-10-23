#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Headless capture publication against real temporary files and injected I/O failures."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import Darwin

typealias Store = NotchQuickCaptureStore
let files = FileManager.default
let root = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try files.createDirectory(at: root, withIntermediateDirectories: true)
defer { try? files.removeItem(at: root) }
var checks = 0
func check(_ condition: Bool, _ description: String) {
    checks += 1
    precondition(condition, description)
}
func committed(_ result: Store.AppendResult) {
    if case .committed = result { checks += 1 } else { preconditionFailure("expected committed") }
}
func absent(_ result: Store.AppendResult) {
    if case .notCommitted = result { checks += 1 } else { preconditionFailure("expected confirmed absence") }
}
func uncertain(_ result: Store.AppendResult) -> Store.AppendAttempt {
    guard case .uncertain(let attempt) = result else { preconditionFailure("expected uncertain append") }
    checks += 1
    return attempt
}
func fails(_ description: String, _ work: () throws -> Void) {
    do { try work(); preconditionFailure(description) } catch { checks += 1 }
}
let iso = ISO8601DateFormatter()
let began = iso.date(from: "2026-10-23T09:19:00Z")!
let original = Data("Hand-edited note, including 🪻 and no final newline".utf8)
struct Fixture {
    let vault: URL
    let images: URL
    let note: URL
    init() throws {
        let folder = root.appendingPathComponent(UUID().uuidString)
        vault = folder.appendingPathComponent("vault")
        images = folder.appendingPathComponent("images")
        note = vault.appendingPathComponent("Captures.md")
        try files.createDirectory(at: vault, withIntermediateDirectories: true)
        try files.createDirectory(at: images, withIntermediateDirectories: true)
        try original.write(to: note)
    }
    func store(_ operations: Store.FileOperations = .init()) -> Store {
        Store(vault: vault, screenshots: images, operations: operations)
    }
    func contents() throws -> Data { try Data(contentsOf: note) }
    func snapshot(_ body: String = "A complete thought") -> Store.Snapshot {
        .init(id: UUID(), startedAt: began, label: "Review", text: body, meeting: nil, images: [], extracts: [])
    }
}
func appendDirect(_ data: Data, to file: URL) throws {
    let fd = Darwin.open(file.path, O_WRONLY | O_APPEND)
    guard fd >= 0 else { throw CocoaError(.fileWriteUnknown) }
    defer { Darwin.close(fd) }
    check(data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) } == data.count, "fixture append")
}
func blocks(_ data: Data) -> Int {
    String(decoding: data, as: UTF8.self).split(separator: "\n").filter { $0.hasPrefix("## ") }.count
}

// One complete, readable block: acquisition times survive image ordering and
// OCR completion order, and all existing bytes are retained exactly.
let content = try Fixture()
try files.createDirectory(at: content.vault.appendingPathComponent("meetings"), withIntermediateDirectories: true)
let meetingFile = content.vault.appendingPathComponent("meetings/Meeting [review].md")
try Data("Existing meeting".utf8).write(to: meetingFile)
let firstImage = content.images.appendingPathComponent("01.png")
let secondImage = content.images.appendingPathComponent("02.png")
try Data("first image".utf8).write(to: firstImage)
try Data("second image".utf8).write(to: secondImage)
let previousZone = NSTimeZone.default
NSTimeZone.default = TimeZone(identifier: "Europe/Berlin")!
defer { NSTimeZone.default = previousZone }
let full = Store.Snapshot(id: UUID(), startedAt: began, label: "Meeting review", text: "First paragraph\n\nSecond line\nThird line",
    meeting: .init(title: "Weekly [review]", start: began.addingTimeInterval(-600), note: meetingFile),
    images: [.init(id: UUID(), capturedAt: began.addingTimeInterval(13), file: secondImage),
             .init(id: UUID(), capturedAt: began.addingTimeInterval(3), file: firstImage)],
    extracts: [.init(id: UUID(), capturedAt: began.addingTimeInterval(17), text: "column A\ncolumn B\n```code```")])
committed(content.store().publish(full))
let body = String(decoding: try content.contents(), as: UTF8.self)
check(try content.contents().starts(with: original), "existing bytes preserved")
check(blocks(try content.contents()) == 1, "one capture heading")
check(body.contains("2026-10-23T11:19:00+02:00"), "capture seconds and local timezone")
check(body.contains("2026-10-23T11:19:13+02:00 · meeting +00:10:13"), "first image keeps its own acquisition time")
check(body.contains("2026-10-23T11:19:03+02:00 · meeting +00:10:03"), "reordered image time is not renumbered")
check(body.contains("2026-10-23T11:19:17+02:00 · meeting +00:10:17"), "OCR timestamp precedes completion")
check(body.contains("First paragraph\n\nSecond line\nThird line"), "thought paragraphs preserved")
check(body.contains("````text\ncolumn A\ncolumn B\n```code```\n````"), "OCR line breaks and embedded fences preserved")
check(body.contains("[Weekly \\[review\\]](<meetings/Meeting%20%5Breview%5D.md>)"), "existing note receives internal relative link")
check(try files.contentsOfDirectory(atPath: content.images.path).sorted() == ["01.png", "02.png"], "OCR creates no image or sidecar")
check(try String(contentsOf: meetingFile, encoding: .utf8) == "Existing meeting", "meeting note stays untouched")

// Empty/unsafe captures fail before opening the publication file.
let empty = try Fixture()
try files.removeItem(at: empty.note)
absent(empty.store().publish(empty.snapshot(" \n ")))
check(!files.fileExists(atPath: empty.note.path), "empty capture creates no note")
let inside = empty.vault.appendingPathComponent("inside.png")
try Data("image".utf8).write(to: inside)
let unsafe = Store.Snapshot(id: UUID(), startedAt: began, label: "", text: "unsafe", meeting: nil,
                           images: [.init(id: UUID(), capturedAt: began, file: inside)], extracts: [])
absent(empty.store().publish(unsafe))
check(!files.fileExists(atPath: empty.note.path), "inside-vault image cannot partially publish")

// No bytes written, lock contention, and a short write with verified rollback
// are confirmed failures. A normal subsequent Save can safely retry.
let zero = try Fixture()
var failedWrite = Store.FileOperations()
failedWrite.write = { _, _ in errno = EIO; return -1 }
absent(zero.store(failedWrite).publish(zero.snapshot()))
check(try zero.contents() == original, "failed write leaves existing bytes unchanged")
let locked = Darwin.open(zero.note.path, O_RDWR)
check(flock(locked, LOCK_EX | LOCK_NB) == 0, "fixture lock held")
absent(zero.store().publish(zero.snapshot()))
flock(locked, LOCK_UN); Darwin.close(locked)
var shortWrite = Store.FileOperations()
shortWrite.write = { fd, data in data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, min(7, $0.count)) } }
absent(zero.store(shortWrite).publish(zero.snapshot()))
check(try zero.contents() == original, "verified short-write rollback restores exact old bytes")
committed(zero.store().publish(zero.snapshot()))
check(blocks(try zero.contents()) == 1, "retry after proven rollback publishes once")

// A full write with failed fsync and a failed truncate may already be present.
// Retry acknowledges it after sync, including when another writer appended.
let fullUncertain = try Fixture()
let retainedImage = fullUncertain.images.appendingPathComponent("01.png")
let retainedPixels = Data("captured pixels".utf8)
try retainedPixels.write(to: retainedImage)
let stable = Store.Snapshot(id: UUID(), startedAt: began, label: "", text: "Retained immutable payload", meeting: nil,
                           images: [.init(id: UUID(), capturedAt: began, file: retainedImage)], extracts: [])
var fullFailure = Store.FileOperations()
var writes = 0, truncates = 0
fullFailure.write = { fd, data in
    writes += 1
    return data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
}
fullFailure.synchronize = { _ in errno = EIO; return -1 }
fullFailure.truncate = { _, _ in truncates += 1; errno = EIO; return -1 }
let fullAttempt = uncertain(fullUncertain.store(fullFailure).publish(stable))
check(writes == 1 && truncates == 1, "one initial write and failed rollback")
check(fullAttempt.writtenCount == fullAttempt.payload.count, "attempt records actual successful write count")
let following = Data("Later user text\n".utf8)
try appendDirect(following, to: fullUncertain.note)
let beforeReconcile = try fullUncertain.contents()
committed(fullUncertain.store().publish(stable, retry: fullAttempt))
check(try fullUncertain.contents() == beforeReconcile, "complete-block retry does not append or erase later content")
check(blocks(try fullUncertain.contents()) == 1, "uncertain complete block is never duplicated")
check(try Data(contentsOf: retainedImage) == retainedPixels, "uncertain publication retains its referenced image")
check(try files.contentsOfDirectory(atPath: fullUncertain.images.path) == ["01.png"], "retry never duplicates images")

// Retry cannot change the block by passing edited state under the same draft ID.
let editedSnapshot = Store.Snapshot(id: stable.id, startedAt: began, label: "Edited", text: "Changed draft",
                                   meeting: nil, images: [], extracts: [])
committed(fullUncertain.store().publish(editedSnapshot, retry: fullAttempt))
check(try fullUncertain.contents() == beforeReconcile, "reconciliation uses retained bytes, not mutable draft")
_ = uncertain(fullUncertain.store().publish(fullUncertain.snapshot(), retry: fullAttempt))
check(try fullUncertain.contents() == beforeReconcile, "another draft cannot reuse attempt")

// A failed truncate after a short write leaves an exact owned tail. Reconcile
// removes only that tail, verifies sync, then writes the whole original block.
let partial = try Fixture()
let partialSnapshot = partial.snapshot("Partial write then retry")
var partialFailure = shortWrite
partialFailure.truncate = { _, _ in errno = EIO; return -1 }
let partialAttempt = uncertain(partial.store(partialFailure).publish(partialSnapshot))
check(try partial.contents() == original + partialAttempt.payload.prefix(7), "short tail remains as evidence")
committed(partial.store().publish(partialSnapshot, retry: partialAttempt))
check(try partial.contents() == original + partialAttempt.payload, "partial retry produces exactly original plus one block")

// Truncation may succeed but its fsync may fail. The attempt remains uncertain
// until a retry successfully synchronizes the unchanged original EOF.
let rollbackSync = try Fixture()
let rollbackSnapshot = rollbackSync.snapshot()
var rollbackFailure = shortWrite
rollbackFailure.synchronize = { _ in errno = EIO; return -1 }
let rolledBackAttempt = uncertain(rollbackSync.store(rollbackFailure).publish(rollbackSnapshot))
check(try rollbackSync.contents() == original, "rollback completed but durability is uncertain")
let stillUncertain = uncertain(rollbackSync.store(rollbackFailure).publish(rollbackSnapshot, retry: rolledBackAttempt))
check(try rollbackSync.contents() == original, "failed reconciliation fsync cannot issue another write")
committed(rollbackSync.store().publish(rollbackSnapshot, retry: stillUncertain))
check(try rollbackSync.contents() == original + rolledBackAttempt.payload, "confirmed absent attempt retries once")

let syncRollback = try Fixture()
let syncSnapshot = syncRollback.snapshot()
var oneSyncFailure = Store.FileOperations()
var syncCalls = 0
oneSyncFailure.synchronize = { fd in
    syncCalls += 1
    if syncCalls == 1 { errno = EIO; return -1 }
    return Darwin.fsync(fd)
}
absent(syncRollback.store(oneSyncFailure).publish(syncSnapshot))
let afterSyncedRollback = try syncRollback.contents()
check(syncCalls == 2 && afterSyncedRollback == original, "successful rollback fsync proves absence after full write")

// A changed prefix, replacement file, or data following a partial tail removes
// our right to repair anything. Repeated retry remains read-only and uncertain.
for kind in ["changed prefix", "replacement", "later tail", "mismatched tail", "missing"] {
    let altered = try Fixture()
    let snapshot = altered.snapshot()
    let evidence = uncertain(altered.store(partialFailure).publish(snapshot))
    switch kind {
    case "changed prefix":
        let fd = Darwin.open(altered.note.path, O_WRONLY)
        let change = Data("X".utf8)
        check(change.withUnsafeBytes { pwrite(fd, $0.baseAddress, 1, 0) } == 1, "fixture prefix edit")
        Darwin.close(fd)
    case "replacement":
        try files.moveItem(at: altered.note, to: altered.vault.appendingPathComponent("old.md"))
        try (original + evidence.payload.prefix(7)).write(to: altered.note)
    case "later tail": try appendDirect(Data("User appended after partial capture".utf8), to: altered.note)
    case "mismatched tail":
        let fd = Darwin.open(altered.note.path, O_WRONLY)
        let change = Data("X".utf8)
        check(change.withUnsafeBytes { pwrite(fd, $0.baseAddress, 1, off_t(original.count)) } == 1, "fixture tail edit")
        Darwin.close(fd)
    default: try files.removeItem(at: altered.note)
    }
    let before = try? altered.contents()
    var forbidden = Store.FileOperations()
    forbidden.write = { _, _ in preconditionFailure("must not write after \(kind)") }
    forbidden.truncate = { _, _ in preconditionFailure("must not truncate after \(kind)") }
    _ = uncertain(altered.store(forbidden).publish(snapshot, retry: evidence))
    check((try? altered.contents()) == before, "ambiguous \(kind) is preserved")
}

// An intervening write during our write call also prevents destructive rollback.
let racing = try Fixture()
var raceOperations = shortWrite
raceOperations.write = { fd, data in
    let amount = data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, min(7, $0.count)) }
    let later = Data("Concurrent writer".utf8)
    _ = later.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
    return amount
}
raceOperations.truncate = { _, _ in preconditionFailure("do not truncate concurrent writer") }
_ = uncertain(racing.store(raceOperations).publish(racing.snapshot()))
check(try racing.contents().suffix(Data("Concurrent writer".utf8).count) == Data("Concurrent writer".utf8), "concurrent suffix survives")

let linked = try Fixture()
let linkedSnapshot = linked.snapshot()
let linkedAttempt = uncertain(linked.store(partialFailure).publish(linkedSnapshot))
try files.moveItem(at: linked.note, to: linked.vault.appendingPathComponent("other.md"))
try files.createSymbolicLink(at: linked.note, withDestinationURL: linked.vault.appendingPathComponent("other.md"))
let beforeLinkRetry = try linked.contents()
_ = uncertain(linked.store().publish(linkedSnapshot, retry: linkedAttempt))
check(try linked.contents() == beforeLinkRetry, "retry refuses a symlink replacement without following it")

// Existing safety, numbering and retention behavior remains part of the
// unified store contract; none of these fixtures touches the personal vault.
let missingVault = root.appendingPathComponent("missing-vault")
absent(Store(vault: missingVault, screenshots: root.appendingPathComponent("missing-images"))
    .publish(empty.snapshot("Keep this unavailable-vault draft")))
check(!files.fileExists(atPath: missingVault.path), "Save never silently creates an unavailable vault")

let numbered = try Fixture()
try files.removeItem(at: numbered.note)
let numberedStore = numbered.store()
let pixels = [Data("first image".utf8), Data("second image".utf8), Data("third image".utf8)]
var session = Store.Session(startedAt: began, label: "SAP-531 A.B.")
for (index, data) in pixels.enumerated() {
    session = try numberedStore.saveSessionScreenshot(data, session: session, at: began.addingTimeInterval(Double(index)))
}
let folder = session.folder!
check(folder.path == numbered.images.appendingPathComponent("2026-10-23/1119 SAP-531 A.B").path,
      "folder uses draft start, local minute and sanitized label")
check(session.count == 3 && session.lastCaptureAt == began.addingTimeInterval(2), "numbering follows acquisition order")
check(!files.fileExists(atPath: numbered.note.path), "persisting images does not independently publish")
func numberedBytes() throws -> [Data] {
    try (1...3).map { try Data(contentsOf: folder.appendingPathComponent(String(format: "%02d.png", $0))) }
}
check(try numberedBytes() == pixels, "all original PNG bytes preserved")
let sameMinute = try numberedStore.saveSessionScreenshot(pixels[0], session: .init(startedAt: began, label: "SAP-531 A.B."), at: began)
check(sameMinute.folder != session.folder && sameMinute.folder?.lastPathComponent.hasSuffix(" (2)") == true,
      "same-minute drafts never overwrite each other")
let crossingMidnight = try numberedStore.saveSessionScreenshot(pixels[0], session: .init(startedAt: began, label: ""),
                                                               at: began.addingTimeInterval(86_400))
check(crossingMidnight.folder?.path == numbered.images.appendingPathComponent("2026-10-23/1119").path,
      "acquisition after midnight still belongs to original draft folder")
check(Store.folderLabel(" ../SAP:/A\\B<>|?*\" \n test \0 ") == "SAPAB test", "filename traversal, controls and unsafe characters stripped")
let unicodeLabel = Store.folderLabel(String(repeating: "🪻", count: 90))
check(unicodeLabel.utf8.count <= 120 && !unicodeLabel.isEmpty && !unicodeLabel.contains("�"),
      "Unicode label remains valid and fits byte limit")
check(Store.folderLabel(String(repeating: "a", count: 90)).count == 60, "label retains character limit")
var staleSession = session; staleSession.count = 0
fails("existing sequence number must not be overwritten") {
    _ = try numberedStore.saveSessionScreenshot(Data("replacement".utf8), session: staleSession, at: began)
}
check(try numberedBytes() == pixels, "number collision preserves every image")

let insideStore = Store(vault: numbered.vault, screenshots: numbered.vault.appendingPathComponent("images"))
fails("image root inside vault must be refused") {
    _ = try insideStore.saveSessionScreenshot(pixels[0], session: .init(startedAt: began, label: ""), at: began)
}
let alias = root.appendingPathComponent("vault-alias")
try files.createSymbolicLink(at: alias, withDestinationURL: numbered.vault)
fails("resolved image root inside vault must be refused") {
    _ = try Store(vault: numbered.vault, screenshots: alias)
        .saveSessionScreenshot(pixels[0], session: .init(startedAt: began, label: ""), at: began)
}
check(try files.contentsOfDirectory(atPath: numbered.vault.path).isEmpty, "unsafe roots create nothing in vault")
let dayAliasRoot = root.appendingPathComponent("day-alias")
try files.createDirectory(at: dayAliasRoot, withIntermediateDirectories: true)
try files.createSymbolicLink(at: dayAliasRoot.appendingPathComponent("2026-10-23"), withDestinationURL: numbered.images)
fails("dated folder symlink must not be followed even outside vault") {
    _ = try Store(vault: numbered.vault, screenshots: dayAliasRoot)
        .saveSessionScreenshot(pixels[0], session: .init(startedAt: began, label: ""), at: began)
}

try numberedStore.reorderSession(session, order: [3, 1, 2])
let reorderedPixels = [pixels[2], pixels[0], pixels[1]]
check(try numberedBytes() == reorderedPixels, "atomic reorder renumbers bytes in desired order")
fails("duplicate reorder indices rejected") { try numberedStore.reorderSession(session, order: [1, 1, 3]) }
fails("missing reorder indices rejected") { try numberedStore.reorderSession(session, order: [1, 2]) }
fails("out-of-range remove rejected") { _ = try numberedStore.removeSessionScreenshot(session, number: 4) }
let outsider = folder.appendingPathComponent("notes.txt")
let outsiderBytes = Data("Keep this unrelated document".utf8)
try outsiderBytes.write(to: outsider)
fails("reorder must preserve unowned files") { try numberedStore.reorderSession(session, order: [3, 2, 1]) }
fails("remove must preserve unowned files") { _ = try numberedStore.removeSessionScreenshot(session, number: 1) }
check(try numberedBytes() == reorderedPixels, "failed reorder/remove preserve numbered bytes")
check(try Data(contentsOf: outsider) == outsiderBytes, "failed reorder/remove preserve outsider")
try files.removeItem(at: outsider)
let outsideImage = root.appendingPathComponent("outside.png")
try outsiderBytes.write(to: outsideImage)
let thirdFile = folder.appendingPathComponent("03.png")
try files.removeItem(at: thirdFile)
try files.createSymbolicLink(at: thirdFile, withDestinationURL: outsideImage)
fails("reorder cannot include a symlink") { try numberedStore.reorderSession(session, order: [2, 1, 3]) }
fails("remove cannot renumber a symlink") { _ = try numberedStore.removeSessionScreenshot(session, number: 1) }
check(try Data(contentsOf: folder.appendingPathComponent("01.png")) == reorderedPixels[0],
      "failure after staging links preserves original numbering")
check(try Data(contentsOf: outsideImage) == outsiderBytes, "atomic mutation never edits symlink target")
try files.removeItem(at: thirdFile); try reorderedPixels[2].write(to: thirdFile)
session = try numberedStore.removeSessionScreenshot(session, number: 2)
let remainingNames = try files.contentsOfDirectory(atPath: folder.path).sorted()
check(session.count == 2 && remainingNames == ["01.png", "02.png"], "remove compacts numbering atomically")
check(try Data(contentsOf: folder.appendingPathComponent("02.png")) == reorderedPixels[2], "compaction retains later image identity")

let retention = try Fixture()
let oldDay = retention.images.appendingPathComponent("2020-01-01")
let now = Date(timeIntervalSince1970: 1_800_000_000)
func agedFile(_ name: String, age: TimeInterval = Store.retention + 1) throws -> URL {
    let url = oldDay.appendingPathComponent(name)
    try files.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try pixels[0].write(to: url)
    try files.setAttributes([.modificationDate: now.addingTimeInterval(-age)], ofItemAtPath: url.path)
    return url
}
let oldStandalone = try agedFile("000001.png")
let boundaryStandalone = try agedFile("000002.png", age: Store.retention)
let newStandalone = try agedFile("000003.png", age: 1)
let unmanagedStandalone = try agedFile("keep.png")
let standaloneAlias = oldDay.appendingPathComponent("000004.png")
try files.createSymbolicLink(at: standaloneAlias, withDestinationURL: unmanagedStandalone)
let oldGrouped = try agedFile("1234 group/01.png")
let boundaryGrouped = try agedFile("1234 group/02.png", age: Store.retention)
let newGrouped = try agedFile("1234 group/03.png", age: 1)
let unmanagedGrouped = try agedFile("1234 group/notes.txt")
let groupedAlias = oldDay.appendingPathComponent("1234 group/04.png")
try files.createSymbolicLink(at: groupedAlias, withDestinationURL: outsideImage)
let unmanagedFolder = try agedFile("project/01.png")
let hidden = try agedFile("1234 group/.01.png")
let emptyGroupImage = try agedFile("1235/01.png")
let vaultDayAlias = retention.images.appendingPathComponent("2020-02-01")
try files.createSymbolicLink(at: vaultDayAlias, withDestinationURL: retention.vault)
let vaultGroupAlias = oldDay.appendingPathComponent("1236 alias")
try files.createSymbolicLink(at: vaultGroupAlias, withDestinationURL: retention.vault)
try retention.store().removeExpiredScreenshots(now: now)
check(!files.fileExists(atPath: oldStandalone.path), "historic HHMMSS screenshot expires after fourteen days")
check(!files.fileExists(atPath: oldGrouped.path), "group NN screenshot expires after fourteen days")
check(!files.fileExists(atPath: emptyGroupImage.deletingLastPathComponent().path), "empty expired group folder removed")
for preserved in [boundaryStandalone, newStandalone, unmanagedStandalone, standaloneAlias, boundaryGrouped,
                  newGrouped, unmanagedGrouped, groupedAlias, unmanagedFolder, hidden, vaultDayAlias, vaultGroupAlias] {
    check(files.fileExists(atPath: preserved.path), "retention preserves boundary/new/unmanaged/hidden/symlink: \(preserved.lastPathComponent)")
}
check(try retention.contents() == original, "retention never enters vault through symlink")
check(try Data(contentsOf: outsideImage) == outsiderBytes, "retention never removes external symlink target")

print("PASS: \(checks) headless quick capture store checks")
'''

with tempfile.TemporaryDirectory(prefix='quick-capture-store-tests-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(code)
    binary = folder / 'checks'
    subprocess.run(['xcrun', 'swiftc', '-target', 'arm64-apple-macosx14.0', '-sdk',
                    '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk',
                    str(repo / 'Sources/Vorssaint/Services/Notch/NotchQuickCaptureStore.swift'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
