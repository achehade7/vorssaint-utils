// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Darwin
import Foundation
import CryptoKit

/// Local files only. Call from the capture service's serial I/O queue.
struct NotchQuickCaptureStore {
    let vault: URL
    let screenshots: URL
    let operations: FileOperations
    static let retention: TimeInterval = 14 * 24 * 60 * 60

    enum Failure: Error { case unavailable, busy, write, unsafeLocation, empty }

    /// Only publication's destructive system calls are injectable. Tests still
    /// use real files, descriptors, locks, reads and fingerprints.
    struct FileOperations {
        var write: (Int32, Data) -> Int = { fd, data in
            data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
        }
        var synchronize: (Int32) -> Int32 = { Darwin.fsync($0) }
        var truncate: (Int32, off_t) -> Int32 = { Darwin.ftruncate($0, $1) }
    }

    init(vault: URL, screenshots: URL, operations: FileOperations = FileOperations()) {
        self.vault = vault
        self.screenshots = screenshots
        self.operations = operations
    }

    struct Meeting: Sendable {
        let title: String
        let start: Date
        let note: URL?
        var transcriptStart: Date? = nil
    }

    struct Image: Sendable {
        let id: UUID
        let capturedAt: Date
        let file: URL
    }

    struct TextExtract: Identifiable, Sendable {
        let id: UUID
        let capturedAt: Date
        let text: String
    }

    struct Snapshot: Sendable {
        let id: UUID
        let startedAt: Date
        let label: String
        let text: String
        let meeting: Meeting?
        let images: [Image]
        let extracts: [TextExtract]
    }

    /// Retained only while this process is running. A retry must use these
    /// bytes, even if the locale, time zone or draft has subsequently changed.
    struct AppendAttempt: Sendable {
        let snapshotID: UUID
        let device: dev_t
        let inode: ino_t
        let originalLength: off_t
        let prefixFingerprint: Data
        let payload: Data
        var writtenCount: Int
    }

    enum AppendResult {
        case committed
        case notCommitted
        case uncertain(AppendAttempt)
    }

    static var personal: Self {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return .init(vault: home.appendingPathComponent("dev/knowledge", isDirectory: true),
                     screenshots: home.appendingPathComponent("Documents/finn/captures", isDirectory: true))
    }

    static func singleLine(_ text: String) -> String {
        text.components(separatedBy: .newlines).joined(separator: " ")
            .replacingOccurrences(of: "\0", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    struct Session {
        let startedAt: Date
        let label: String
        var lastCaptureAt: Date
        var folder: URL?
        var count = 0

        init(startedAt: Date, label: String) {
            self.startedAt = startedAt
            self.lastCaptureAt = startedAt
            self.label = String(NotchQuickCaptureStore.singleLine(label).prefix(80))
        }
    }

    static func folderLabel(_ label: String) -> String {
        let forbidden = CharacterSet.controlCharacters.union(CharacterSet(charactersIn: "/:\\<>|?*\""))
        let stripped = String(label.unicodeScalars.filter { !forbidden.contains($0) })
        var safe = stripped.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }.joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        safe = String(safe.prefix(60))
        while safe.utf8.count > 120 { safe.removeLast() }
        return safe.trimmingCharacters(in: CharacterSet(charactersIn: ". "))
    }

    /// Publish a fixed, already-persisted capture. Failure never deletes image
    /// files: the note may contain their paths even when durability is unknown.
    func publish(_ snapshot: Snapshot, retry: AppendAttempt? = nil) -> AppendResult {
        if let retry, retry.snapshotID != snapshot.id { return .uncertain(retry) }
        let block: Data
        if retry == nil {
            do { block = Data(try markdown(snapshot).utf8) }
            catch { return .notCommitted }
        } else { block = Data() }
        let directory = Darwin.open(vault.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard directory >= 0 else { return retry.map(AppendResult.uncertain) ?? .notCommitted }
        defer { Darwin.close(directory) }
        let flags = O_RDWR | O_APPEND | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK
        let fd = openat(directory, "Captures.md", flags | (retry == nil ? O_CREAT : 0), 0o600)
        guard fd >= 0 else { return retry.map(AppendResult.uncertain) ?? .notCommitted }
        defer { Darwin.close(fd) }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else {
            return retry.map(AppendResult.uncertain) ?? .notCommitted
        }
        defer { flock(fd, LOCK_UN) }
        if let retry { return reconcile(retry, fd: fd, directory: directory) }
        do {
            return try appendBlock(block, snapshotID: snapshot.id, fd: fd, directory: directory)
        } catch { return .notCommitted }
    }

    private func markdown(_ snapshot: Snapshot) throws -> String {
        let thought = Self.multiline(snapshot.text)
        guard !thought.isEmpty || !snapshot.images.isEmpty || !snapshot.extracts.isEmpty else { throw Failure.empty }
        let label = Self.singleLine(snapshot.label)
        var block = "## " + timestamp(snapshot.startedAt) + (label.isEmpty ? "" : " · " + label) + "\n\n"
        if let meeting = snapshot.meeting {
            var title = Self.singleLine(meeting.title)
            if let note = meeting.note {
                let root = vault.resolvingSymlinksInPath().standardizedFileURL.path
                let path = note.resolvingSymlinksInPath().standardizedFileURL.path
                if path.hasPrefix(root + "/") {
                    let relative = String(path.dropFirst(root.count + 1))
                    let allowed = CharacterSet.urlPathAllowed.subtracting(CharacterSet(charactersIn: "?#()<>[]"))
                    if let target = relative.addingPercentEncoding(withAllowedCharacters: allowed) {
                        let escaped = title.replacingOccurrences(of: "\\", with: "\\\\")
                            .replacingOccurrences(of: "[", with: "\\[").replacingOccurrences(of: "]", with: "\\]")
                        title = "[" + escaped + "](<" + target + ">)"
                    }
                }
            }
            block += "Meeting: " + title + " · " + timestamp(meeting.start) + "\n\n"
        }
        if !thought.isEmpty { block += thought + "\n\n" }
        if !snapshot.images.isEmpty {
            block += "### Screenshots\n\n"
            for image in snapshot.images {
                try checkScreenshotLocation(image.file)
                let info = try image.file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                guard info.isRegularFile == true, info.isSymbolicLink != true else { throw Failure.unsafeLocation }
                block += "- " + attachmentTime(image.capturedAt, meeting: snapshot.meeting) + transcriptOffset(image.capturedAt, start: snapshot.meeting?.transcriptStart)
                    + " · " + image.file.path + "\n"
            }
            block += "\n"
        }
        if !snapshot.extracts.isEmpty {
            block += "### Text extracts\n\n"
            for extract in snapshot.extracts {
                let text = Self.multiline(extract.text)
                guard !text.isEmpty else { throw Failure.empty }
                // A captured code example may itself contain a Markdown fence.
                let longest = text.split(whereSeparator: { $0 != "`" }).map(\.count).max() ?? 0
                let fence = String(repeating: "`", count: max(3, longest + 1))
                block += "**" + attachmentTime(extract.capturedAt, meeting: snapshot.meeting) + "**\n\n"
                    + fence + "text\n" + text + "\n" + fence + "\n\n"
            }
        }
        return block
    }

    static func multiline(_ text: String) -> String {
        text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "\0", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func timestamp(_ date: Date) -> String {
        formatter("yyyy-MM-dd'T'HH:mm:ssxxx").string(from: date)
    }

    private func attachmentTime(_ date: Date, meeting: Meeting?) -> String {
        guard let meeting else { return timestamp(date) }
        let offset = date.timeIntervalSince(meeting.start)
        guard offset.isFinite, abs(offset) < Double(Int.max) else { return timestamp(date) }
        let seconds = Int(abs(offset).rounded(.down))
        return timestamp(date) + " · meeting " + (offset < 0 ? "−" : "+")
            + String(format: "%02d:%02d:%02d", seconds / 3600, (seconds / 60) % 60, seconds % 60)
    }

    private func transcriptOffset(_ date: Date, start: Date?) -> String {
        guard let start else { return "" }
        let offset = date.timeIntervalSince(start)
        guard offset.isFinite, abs(offset) < Double(Int.max) else { return "" }
        let seconds = Int(abs(offset).rounded(.down))
        return " · transcript " + (offset < 0 ? "−" : "+")
            + String(format: "%02d:%02d:%02d", seconds / 3600, (seconds / 60) % 60, seconds % 60)
    }

    private func appendBlock(_ block: Data, snapshotID: UUID, fd: Int32, directory: Int32) throws -> AppendResult {
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else { throw Failure.unavailable }
        let fingerprint = try prefixFingerprint(fd, length: info.st_size)
        var prefix = Data()
        if info.st_size > 0 {
            let last = try bytes(fd, offset: info.st_size - 1, count: 1)
            if last.first != 10 { prefix.append(10) }
            prefix.append(10)
        }
        let attempt = AppendAttempt(snapshotID: snapshotID, device: info.st_dev, inode: info.st_ino,
                                    originalLength: info.st_size, prefixFingerprint: fingerprint,
                                    payload: prefix + block, writtenCount: 0)
        guard matchesOriginal(attempt, fd: fd, directory: directory), fileLength(fd) == attempt.originalLength else {
            throw Failure.busy
        }
        return writeAttempt(attempt, fd: fd, directory: directory)
    }

    private func writeAttempt(_ original: AppendAttempt, fd: Int32, directory: Int32) -> AppendResult {
        var attempt = original
        attempt.writtenCount = operations.write(fd, attempt.payload)
        guard attempt.writtenCount > 0 else { return .notCommitted }
        if attempt.writtenCount == attempt.payload.count, operations.synchronize(fd) == 0,
           completeBlockMatches(attempt, fd: fd, directory: directory) { return .committed }
        // flock coordinates participating writers, not Obsidian. Never truncate
        // a replacement, a changed prefix, or bytes beyond this exact write.
        if rollback(attempt, fd: fd, directory: directory) { return .notCommitted }
        return .uncertain(attempt)
    }

    private func reconcile(_ attempt: AppendAttempt, fd: Int32, directory: Int32) -> AppendResult {
        guard matchesOriginal(attempt, fd: fd, directory: directory), let length = fileLength(fd) else {
            return .uncertain(attempt)
        }
        if length == attempt.originalLength {
            guard operations.synchronize(fd) == 0,
                  matchesOriginal(attempt, fd: fd, directory: directory),
                  fileLength(fd) == attempt.originalLength else { return .uncertain(attempt) }
            return writeAttempt(attempt, fd: fd, directory: directory)
        }
        if completeBlockMatches(attempt, fd: fd, directory: directory) {
            guard operations.synchronize(fd) == 0,
                  completeBlockMatches(attempt, fd: fd, directory: directory) else { return .uncertain(attempt) }
            return .committed
        }
        guard attempt.writtenCount < attempt.payload.count,
              rollback(attempt, fd: fd, directory: directory) else { return .uncertain(attempt) }
        return writeAttempt(attempt, fd: fd, directory: directory)
    }

    private func rollback(_ attempt: AppendAttempt, fd: Int32, directory: Int32) -> Bool {
        guard attempt.writtenCount > 0, attempt.writtenCount <= attempt.payload.count,
              matchesOriginal(attempt, fd: fd, directory: directory), let length = fileLength(fd),
              length >= attempt.originalLength,
              length - attempt.originalLength == off_t(attempt.writtenCount),
              (try? bytes(fd, offset: attempt.originalLength, count: attempt.writtenCount))
                == Data(attempt.payload.prefix(attempt.writtenCount)),
              operations.truncate(fd, attempt.originalLength) == 0,
              operations.synchronize(fd) == 0 else { return false }
        return matchesOriginal(attempt, fd: fd, directory: directory) && fileLength(fd) == attempt.originalLength
    }

    private func completeBlockMatches(_ attempt: AppendAttempt, fd: Int32, directory: Int32) -> Bool {
        guard matchesOriginal(attempt, fd: fd, directory: directory), let length = fileLength(fd),
              length >= attempt.originalLength, length - attempt.originalLength >= off_t(attempt.payload.count) else { return false }
        return (try? bytes(fd, offset: attempt.originalLength, count: attempt.payload.count)) == attempt.payload
    }

    private func matchesOriginal(_ attempt: AppendAttempt, fd: Int32, directory: Int32) -> Bool {
        var descriptor = stat(), current = stat()
        guard fstat(fd, &descriptor) == 0, (descriptor.st_mode & S_IFMT) == S_IFREG,
              fstatat(directory, "Captures.md", &current, AT_SYMLINK_NOFOLLOW) == 0,
              (current.st_mode & S_IFMT) == S_IFREG,
              descriptor.st_dev == attempt.device, descriptor.st_ino == attempt.inode,
              current.st_dev == attempt.device, current.st_ino == attempt.inode,
              descriptor.st_size >= attempt.originalLength else { return false }
        return (try? prefixFingerprint(fd, length: attempt.originalLength)) == attempt.prefixFingerprint
    }

    private func fileLength(_ fd: Int32) -> off_t? {
        var info = stat()
        return fstat(fd, &info) == 0 ? info.st_size : nil
    }

    private func prefixFingerprint(_ fd: Int32, length: off_t) throws -> Data {
        guard length >= 0 else { throw Failure.write }
        var hash = SHA256(), offset: off_t = 0
        while offset < length {
            let data = try bytes(fd, offset: offset, count: Int(min(65_536, length - offset)))
            hash.update(data: data)
            offset += off_t(data.count)
        }
        return Data(hash.finalize())
    }

    private func bytes(_ fd: Int32, offset: off_t, count: Int) throws -> Data {
        var data = Data(count: count), readCount = 0
        while readCount < count {
            let amount = data.withUnsafeMutableBytes {
                pread(fd, $0.baseAddress!.advanced(by: readCount), count - readCount, offset + off_t(readCount))
            }
            if amount < 0, errno == EINTR { continue }
            guard amount > 0 else { throw Failure.write }
            readCount += amount
        }
        return data
    }

    func saveSessionScreenshot(_ png: Data, session: Session, at date: Date) throws -> Session {
        var result = session
        let folder = try session.folder ?? makeSessionFolder(session)
        let created = session.folder == nil
        do {
            try checkScreenshotLocation(folder)
            try writePNG(png, to: folder, name: String(format: "%02d.png", session.count + 1))
        } catch {
            if created { _ = rmdir(folder.path) }
            throw error
        }
        result.folder = folder
        result.count += 1
        result.lastCaptureAt = date
        return result
    }

    /// Build the new numbering with hard links, then atomically exchange folders.
    /// Until the exchange succeeds, every original path and byte stays intact.
    func reorderSession(_ session: Session, order: [Int]) throws {
        guard session.count > 0, let folder = session.folder,
              order.count == session.count, Set(order) == Set(1...session.count) else { throw Failure.write }
        guard order != Array(1...session.count) else { return }
        try replaceSessionImages(session, folder: folder, order: order)
    }

    /// Remove exactly one capture and compact numbering in the same atomic
    /// folder exchange as reordering. Failure leaves every original untouched.
    func removeSessionScreenshot(_ session: Session, number: Int) throws -> Session {
        guard session.count > 0, let folder = session.folder,
              (1...session.count).contains(number) else { throw Failure.write }
        try replaceSessionImages(session, folder: folder, order: (1...session.count).filter { $0 != number })
        var updated = session
        updated.count -= 1
        return updated
    }

    private func replaceSessionImages(_ session: Session, folder: URL, order: [Int]) throws {
        try checkScreenshotLocation(folder)
        let files = FileManager.default
        let folderInfo = try folder.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard folderInfo.isDirectory == true, folderInfo.isSymbolicLink != true else { throw Failure.unsafeLocation }
        let names = (1...session.count).map { String(format: "%02d.png", $0) }
        guard Set(try files.contentsOfDirectory(atPath: folder.path)) == Set(names) else { throw Failure.busy }
        // A dated sibling remains eligible for normal retention if the process
        // exits between the exchange and removal of the old directory.
        let staging = folder.deletingLastPathComponent().appendingPathComponent(
            folder.lastPathComponent + " (reorder " + UUID().uuidString + ")", isDirectory: true)
        guard mkdir(staging.path, 0o700) == 0 else { throw Failure.write }
        defer { try? files.removeItem(at: staging) }
        for (index, original) in order.enumerated() {
            let source = folder.appendingPathComponent(names[original - 1])
            let info = try source.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true else { throw Failure.unsafeLocation }
            guard Darwin.link(source.path, staging.appendingPathComponent(names[index]).path) == 0 else { throw Failure.write }
        }
        guard renamex_np(staging.path, folder.path, UInt32(RENAME_SWAP)) == 0 else { throw Failure.write }
    }

    private func formatter(_ format: String) -> DateFormatter {
        let value = DateFormatter()
        value.locale = Locale(identifier: "en_US_POSIX")
        value.calendar = Calendar(identifier: .gregorian)
        value.timeZone = .current
        value.dateFormat = format
        return value
    }

    private func checkScreenshotLocation(_ url: URL) throws {
        let target = url.resolvingSymlinksInPath().standardizedFileURL.path
        let vaultPath = vault.resolvingSymlinksInPath().standardizedFileURL.path
        guard target != vaultPath, !target.hasPrefix(vaultPath + "/") else { throw Failure.unsafeLocation }
    }

    private func dayFolder(at date: Date) throws -> URL {
        try checkScreenshotLocation(screenshots)
        let files = FileManager.default
        try files.createDirectory(at: screenshots, withIntermediateDirectories: true,
                                  attributes: [.posixPermissions: 0o700])
        let day = screenshots.appendingPathComponent(formatter("yyyy-MM-dd").string(from: date), isDirectory: true)
        try checkScreenshotLocation(day)
        try files.createDirectory(at: day, withIntermediateDirectories: true,
                                  attributes: [.posixPermissions: 0o700])
        let directory = Darwin.open(day.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard directory >= 0 else { throw Failure.unsafeLocation }
        Darwin.close(directory)
        return day
    }

    private func makeSessionFolder(_ session: Session) throws -> URL {
        let day = try dayFolder(at: session.startedAt)
        let safe = Self.folderLabel(session.label)
        let base = formatter("HHmm").string(from: session.startedAt) + (safe.isEmpty ? "" : " " + safe)
        for suffix in 1...10_000 {
            let name = base + (suffix == 1 ? "" : " (\(suffix))")
            let folder = day.appendingPathComponent(name, isDirectory: true)
            if mkdir(folder.path, 0o700) == 0 { return folder }
            if errno != EEXIST { throw Failure.write }
        }
        throw Failure.write
    }

    private func writePNG(_ png: Data, to folder: URL, name: String) throws {
        let directory = Darwin.open(folder.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard directory >= 0 else { throw Failure.unsafeLocation }
        defer { Darwin.close(directory) }
        let fd = openat(directory, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw errno == EEXIST ? Failure.busy : Failure.write }
        let count = png.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
        let complete = count == png.count && fsync(fd) == 0
        Darwin.close(fd)
        guard complete else { unlinkat(directory, name, 0); throw Failure.write }
    }

    /// Only this feature's dated PNGs are eligible; never follow folder/file
    /// symlinks or touch neighbouring documents, hidden files, or the vault.
    func removeExpiredScreenshots(now: Date = Date()) throws {
        let files = FileManager.default
        guard files.fileExists(atPath: screenshots.path) else { return }
        try checkScreenshotLocation(screenshots)
        let keys: Set<URLResourceKey> = [.isDirectoryKey, .isSymbolicLinkKey, .isRegularFileKey, .contentModificationDateKey]
        let cutoff = now.addingTimeInterval(-Self.retention)
        for day in try files.contentsOfDirectory(at: screenshots, includingPropertiesForKeys: Array(keys)) {
            guard day.lastPathComponent.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil else { continue }
            let attributes = try day.resourceValues(forKeys: keys)
            guard attributes.isDirectory == true, attributes.isSymbolicLink != true else { continue }
            try checkScreenshotLocation(day)
            for entry in try files.contentsOfDirectory(at: day, includingPropertiesForKeys: Array(keys)) {
                let attributes = try entry.resourceValues(forKeys: keys)
                guard attributes.isSymbolicLink != true else { continue }
                if attributes.isDirectory == true,
                   entry.lastPathComponent.range(of: #"^\d{4}(?: .+)?$"#, options: .regularExpression) != nil {
                    try checkScreenshotLocation(entry)
                    for file in try files.contentsOfDirectory(at: entry, includingPropertiesForKeys: Array(keys)) {
                        try removeExpiredPNG(file, pattern: #"^\d{2,}\.png$"#, cutoff: cutoff, keys: keys)
                    }
                    if try files.contentsOfDirectory(atPath: entry.path).isEmpty { try files.removeItem(at: entry) }
                } else {
                    try removeExpiredPNG(entry, pattern: #"^\d{6}\.png$"#, cutoff: cutoff, keys: keys)
                }
            }
            if try files.contentsOfDirectory(atPath: day.path).isEmpty { try files.removeItem(at: day) }
        }
    }

    private func removeExpiredPNG(_ file: URL, pattern: String, cutoff: Date,
                                  keys: Set<URLResourceKey>) throws {
        guard file.lastPathComponent.range(of: pattern, options: .regularExpression) != nil else { return }
        let values = try file.resourceValues(forKeys: keys)
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let modified = values.contentModificationDate, modified < cutoff else { return }
        try FileManager.default.removeItem(at: file)
    }
}
