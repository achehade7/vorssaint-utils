// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Darwin
import Foundation

/// Local files only. Call from the capture service's serial I/O queue.
struct NotchQuickCaptureStore {
    let vault: URL
    let screenshots: URL
    static let retention: TimeInterval = 14 * 24 * 60 * 60

    enum Failure: Error { case unavailable, busy, write, unsafeLocation, empty }

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

    func append(text: String, pngs: [Data], at date: Date = Date()) throws {
        let text = Self.singleLine(text)
        guard !text.isEmpty || !pngs.isEmpty else { throw Failure.empty }
        var saved: [URL] = []
        var appended = false
        defer {
            if !appended { for url in saved { try? FileManager.default.removeItem(at: url) } }
        }
        try appendLine {
            for png in pngs { saved.append(try saveScreenshot(png, at: date)) }
            var line = "- \(formatter("yyyy-MM-dd HH:mm").string(from: date))"
            if !text.isEmpty { line += " · \(text)" }
            for url in saved { line += " · screenshot: \(url.path)" }
            return line
        }
        appended = true
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

    func appendSession(_ session: Session) throws {
        guard session.count > 0 else { return }
        guard let folder = session.folder else { throw Failure.write }
        try checkScreenshotLocation(folder)
        try appendLine {
            var line = "- \(formatter("yyyy-MM-dd HH:mm").string(from: session.startedAt))"
            if !session.label.isEmpty { line += " · \(session.label)" }
            return line + " · \(session.count) screenshots · \(folder.path)"
        }
    }

    /// One locked O_APPEND write preserves every existing byte, including notes
    /// sorted by hand. No temporary replacement of Captures.md is involved.
    private func appendLine(_ makeLine: () throws -> String) throws {
        let directory = Darwin.open(vault.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard directory >= 0 else { throw Failure.unavailable }
        defer { Darwin.close(directory) }
        let fd = openat(directory, "Captures.md", O_RDWR | O_APPEND | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0o600)
        guard fd >= 0 else { throw Failure.unavailable }
        defer { Darwin.close(fd) }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { throw Failure.busy }
        defer { flock(fd, LOCK_UN) }
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else { throw Failure.unavailable }
        var prefix = ""
        if info.st_size > 0 {
            var last: UInt8 = 0
            guard pread(fd, &last, 1, info.st_size - 1) == 1 else { throw Failure.write }
            if last != 10 { prefix = "\n" }
        }
        let data = Data((prefix + (try makeLine()) + "\n").utf8)
        let count = data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
        guard count == data.count, fsync(fd) == 0 else {
            // Remove only this failed append, never rewrite previous lines.
            if count > 0 { _ = ftruncate(fd, info.st_size); _ = fsync(fd) }
            throw Failure.write
        }
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

    private func saveScreenshot(_ png: Data, at date: Date) throws -> URL {
        // Exclusive creation keeps the existing HHMMSS format for quick bursts.
        for offset in 0..<86_400 {
            let instant = date.addingTimeInterval(Double(offset))
            let day = try dayFolder(at: instant)
            let name = formatter("HHmmss").string(from: instant) + ".png"
            do { try writePNG(png, to: day, name: name) }
            catch Failure.busy { continue }
            return day.appendingPathComponent(name)
        }
        throw Failure.write
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
