// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import Darwin

/// The vault's simple investigation properties, not a general YAML reader.
enum InvestigationNoteLookup {
    static func key(in query: String) -> String? {
        let words = query.split(whereSeparator: \.isWhitespace)
        guard words.count == 2, words[0].lowercased() == "o" else { return nil }
        let key = words[1].uppercased()
        return key.range(of: #"^[A-Z][A-Z0-9]*-[0-9]+$"#, options: .regularExpression) != nil ? key : nil
    }

    static func matches(_ header: [String], key: String) -> Bool {
        func scalar(_ text: String) -> String {
            var value = text.replacingOccurrences(of: #"(?:^|\s+)#.*$"#, with: "", options: .regularExpression)
                .trimmingCharacters(in: .whitespaces)
            if value.count >= 2, let first = value.first, first == value.last, first == "\"" || first == "'" {
                value = String(value.dropFirst().dropLast())
            }
            return value
        }
        var type: String?, tickets: [String]?, block = false
        for line in header {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }
            if !line.hasPrefix(" "), !line.hasPrefix("\t"), let colon = line.firstIndex(of: ":") {
                block = false
                let property = String(line[..<colon])
                let value = scalar(String(line[line.index(after: colon)...]))
                if property == "type" {
                    guard type == nil else { return false }
                    type = value
                } else if property == "jira" {
                    guard tickets == nil else { return false }
                    tickets = []
                    if value.isEmpty { block = true }
                    else if value.hasPrefix("["), value.hasSuffix("]") {
                        tickets = value.dropFirst().dropLast().split(separator: ",").map { scalar(String($0)) }
                    } else { return false }
                }
            } else if block {
                let item = line.trimmingCharacters(in: .whitespaces)
                if item.hasPrefix("- ") || item.hasPrefix("-\t") { tickets?.append(scalar(String(item.dropFirst()))) }
            }
        }
        return type == "investigation" && tickets?.contains(where: { $0.uppercased() == key.uppercased() }) == true
    }

    static func safe(_ file: URL, root: URL, directory: Bool) -> Bool {
        guard file.path.hasPrefix(root.path + "/"), file.resolvingSymlinksInPath().path == file.path,
              let info = try? file.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey, .isRegularFileKey]),
              info.isSymbolicLink != true else { return false }
        return directory ? info.isDirectory == true : info.isRegularFile == true
    }

    /// Stop at the closing fence; never load or search the note body.
    static func header(_ file: URL) throws -> [String] {
        let fd = open(file.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { throw CocoaError(.fileReadNoPermission) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              let stream = fdopen(fd, "r") else { close(fd); throw CocoaError(.fileReadNoPermission) }
        defer { fclose(stream) }
        var buffer: UnsafeMutablePointer<CChar>?, capacity = 0
        defer { free(buffer) }
        var lines: [String] = [], bytes = 0, first = true
        while true {
            try Task.checkCancellation()
            let count = getline(&buffer, &capacity, stream)
            guard count >= 0 else { return [] }
            bytes += count
            guard bytes <= 65_536, let buffer,
                  var line = String(bytes: UnsafeRawBufferPointer(start: buffer, count: count), encoding: .utf8) else { return [] }
            line = line.trimmingCharacters(in: .newlines)
            if first {
                first = false
                if line.hasPrefix("\u{FEFF}") { line.removeFirst() }
                guard line.trimmingCharacters(in: .whitespaces) == "---" else { return [] }
            } else if line.trimmingCharacters(in: .whitespaces) == "---" { return lines }
            else { lines.append(line) }
        }
    }

    static func read(vault: URL, key: String) throws -> [URL] {
        let root = vault.standardizedFileURL
        guard root.resolvingSymlinksInPath() == root else { throw CocoaError(.fileReadNoPermission) }
        let projects = root.appendingPathComponent("projects")
        guard safe(projects, root: root, directory: true) else { throw CocoaError(.fileReadNoPermission) }
        let fm = FileManager.default
        var matches: [URL] = []
        for name in try fm.contentsOfDirectory(atPath: projects.path) where !name.hasPrefix(".") {
            let project = projects.appendingPathComponent(name)
            try Task.checkCancellation()
            guard safe(project, root: root, directory: true) else { continue }
            let folder = project.appendingPathComponent("investigations")
            guard safe(folder, root: root, directory: true) else { continue }
            for name in try fm.contentsOfDirectory(atPath: folder.path) where !name.hasPrefix(".") {
                let file = folder.appendingPathComponent(name)
                guard file.pathExtension == "md", safe(file, root: root, directory: false) else { continue }
                if try self.matches(header(file), key: key) { matches.append(file) }
            }
        }
        return matches.sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
    }

    static func openURL(file: URL, vault: URL, key: String) -> URL? {
        let root = vault.standardizedFileURL
        guard root.resolvingSymlinksInPath() == root,
              safe(file, root: root, directory: false),
              let header = try? header(file), matches(header, key: key) else { return nil }
        let relative = String(file.path.dropFirst(root.path.count + 1))
        let parts = relative.split(separator: "/")
        guard parts.count == 4, parts[0] == "projects", parts[2] == "investigations", file.pathExtension == "md" else { return nil }
        var url = URLComponents()
        url.scheme = "obsidian"; url.host = "open"
        url.queryItems = [URLQueryItem(name: "vault", value: root.lastPathComponent),
                          URLQueryItem(name: "file", value: String(relative.dropLast(3)))]
        return url.url
    }
}
