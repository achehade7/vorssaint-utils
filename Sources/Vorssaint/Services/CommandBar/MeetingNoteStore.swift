// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import Darwin
import NaturalLanguage

/// Only these selected calendar fields cross the note-writing boundary.
/// Descriptions, locations, participant URLs and conferencing details never do.
struct MeetingNoteInput: Sendable {
    let identity: String?
    let title: String
    let start: Date
    let end: Date
    let people: [MeetingNotePerson]
}

struct MeetingNoteStore {
    let vault: URL
    enum Failure: Error { case unavailable, template, unsafe, write }

    static var personal: Self {
        .init(vault: FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("dev/knowledge"))
    }

    static func date(_ date: Date, format: String) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = format
        return formatter.string(from: date)
    }

    static func topic(_ text: String, people: [MeetingNotePerson]) -> String {
        var value = text
        // Remove contact data before considering names or file-name punctuation.
        for pattern in [#"https?://\S+"#, #"\S*@\S*"#, #"\+?\d[\d ()-]{6,}\d"#] {
            value = value.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
        }
        // Longest aliases first so a full name becomes one set of initials.
        let aliases = people.flatMap { person -> [(String, String)] in
            guard !person.initials.isEmpty else { return [] }
            let words = person.name.split(whereSeparator: { !$0.isLetter }).map(String.init)
            return ([person.name] + words.filter { $0.count > 1 }).map {
                ($0, person.isCurrentUser ? "" : person.initials)
            }
        }.sorted { $0.0.count > $1.0.count }
        for (name, replacement) in aliases {
            let pattern = #"(?i)(?<![\p{L}\p{N}])"# + NSRegularExpression.escapedPattern(for: name) + #"(?![\p{L}\p{N}])"#
            value = value.replacingOccurrences(of: pattern, with: replacement, options: .regularExpression)
        }
        // Local macOS name recognition catches names in the title that are not attendees.
        let tagger = NLTagger(tagSchemes: [.nameType])
        tagger.string = value
        var names: [Range<String.Index>] = []
        tagger.enumerateTags(in: value.startIndex..<value.endIndex, unit: .word, scheme: .nameType,
                            options: [.omitWhitespace, .omitPunctuation, .joinNames]) { tag, range in
            if tag == .personalName { names.append(range) }
            return true
        }
        for range in names.reversed() {
            let initials = MeetingNotePerson(name: String(value[range])).initials
            value.replaceSubrange(range, with: initials)
        }
        value = value.replacingOccurrences(of: ##"[/\\:<>|?*\"#\[\]{}\x00-\x1F\x7F]"##, with: " ", options: .regularExpression)
            .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: " -·&"))
        while value.hasPrefix(".") { value.removeFirst() }
        value = String(value.prefix(80))
        while value.utf8.count > 160 { value.removeLast() }
        if value.isEmpty { return "Meeting" }
        if value.replacingOccurrences(of: #"[\p{Lu}\.\s&-]"#, with: "", options: .regularExpression).isEmpty,
           value.contains(".") { value += " one-on-one" }
        return value
    }

    static func suggestedTopic(_ input: MeetingNoteInput) -> String { topic(input.title, people: input.people) }

    static func purpose(_ input: MeetingNoteInput) -> String {
        var seen = Set<String>()
        let participants = input.people.map(\.initials).filter { !$0.isEmpty && seen.insert($0).inserted }.joined(separator: ", ")
        return date(input.start, format: "HH:mm") + "–" + date(input.end, format: "HH:mm")
            + (participants.isEmpty ? "" : ", " + participants)
    }

    private func project(for title: String) throws -> String? {
        let expression = try NSRegularExpression(pattern: #"\b[A-Z][A-Z0-9]+-\d+\b"#)
        let keys = Set(expression.matches(in: title, range: NSRange(title.startIndex..., in: title))
            .compactMap { Range($0.range, in: title).map { String(title[$0]) } })
        guard !keys.isEmpty else { return nil }
        var projects = Set<String>()
        for name in ["sap-support", "abs"] {
            let folder = vault.appendingPathComponent("projects/" + name)
            guard let files = FileManager.default.enumerator(at: folder, includingPropertiesForKeys: [.isSymbolicLinkKey],
                                                            options: [.skipsHiddenFiles]) else { continue }
            for case let file as URL in files where file.pathExtension == "md" {
                guard file.resolvingSymlinksInPath().path.hasPrefix(folder.resolvingSymlinksInPath().path + "/"),
                      let text = try? String(contentsOf: file, encoding: .utf8), text.hasPrefix("---\n"),
                      let end = text.range(of: "\n---", range: text.index(text.startIndex, offsetBy: 4)..<text.endIndex) else { continue }
                let lines = text[..<end.lowerBound].components(separatedBy: .newlines)
                var inJira = false
                for line in lines {
                    if line.hasPrefix("jira:") { inJira = true }
                    else if !line.hasPrefix(" ") { inJira = false }
                    guard inJira else { continue }
                    let found = expression.matches(in: line, range: NSRange(line.startIndex..., in: line))
                        .compactMap { Range($0.range, in: line).map { String(line[$0]) } }
                    if !keys.isDisjoint(with: found) { projects.insert(name) }
                }
            }
        }
        return projects.count == 1 ? projects.first : nil
    }

    static func eventID(in text: String) -> String? {
        guard text.hasPrefix("---\n"), let end = text.range(of: "\n---", range: text.index(text.startIndex, offsetBy: 4)..<text.endIndex) else { return nil }
        guard let line = text[..<end.lowerBound].components(separatedBy: .newlines).first(where: { $0.hasPrefix("calendar_event:") }) else { return nil }
        let value = line.dropFirst("calendar_event:".count).trimmingCharacters(in: .whitespaces)
        if value.hasPrefix("\"") { return try? JSONDecoder().decode(String.self, from: Data(value.utf8)) }
        if value.hasPrefix("'"), value.hasSuffix("'") { return String(value.dropFirst().dropLast()).replacingOccurrences(of: "''", with: "'") }
        return value.isEmpty ? nil : value.components(separatedBy: " #")[0]
    }

    func prepare(_ input: MeetingNoteInput, topic requestedTopic: String) throws -> URL {
        let files = FileManager.default
        let folder = vault.appendingPathComponent("meetings", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard files.fileExists(atPath: folder.path, isDirectory: &isDirectory), isDirectory.boolValue,
              folder.resolvingSymlinksInPath().path.hasPrefix(vault.resolvingSymlinksInPath().path + "/") else { throw Failure.unavailable }
        let topic = Self.topic(requestedTopic, people: input.people)
        let title = Self.date(input.start, format: "yyyy-MM-dd") + " " + topic
        let destination = folder.appendingPathComponent(title + ".md")
        let existing = try files.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        var sameTopic: URL?
        for file in existing where file.pathExtension == "md" {
            let info = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true else {
                if file.lastPathComponent.lowercased() == destination.lastPathComponent.lowercased() { throw Failure.unsafe }
                continue
            }
            if let identity = input.identity,
               Self.eventID(in: try String(contentsOf: file, encoding: .utf8)) == identity { return file }
            if file.lastPathComponent.lowercased() == destination.lastPathComponent.lowercased() { sameTopic = file }
        }
        if let sameTopic { return sameTopic }
        let template = vault.appendingPathComponent("templates/Meeting.md")
        guard template.resolvingSymlinksInPath().path.hasPrefix(vault.resolvingSymlinksInPath().path + "/"),
              var text = try? String(contentsOf: template, encoding: .utf8),
              text.hasPrefix("---\n"), text.contains("date: {{date:YYYY-MM-DD}}"),
              text.contains("calendar_event:\n"), text.contains("type: meeting"), text.contains("project: []"), text.contains("topics: []"),
              text.contains("folded: false"), text.contains("# {{title}}"), text.contains("## Purpose\n") else { throw Failure.template }
        text = text.replacingOccurrences(of: "{{date:YYYY-MM-DD}}", with: Self.date(input.start, format: "yyyy-MM-dd"))
            .replacingOccurrences(of: "{{title}}", with: title)
            .replacingOccurrences(of: "project: []", with: "project: [" + (try project(for: input.title) ?? "") + "]")
            .replacingOccurrences(of: "## Purpose\n", with: "## Purpose\n\n" + Self.purpose(input) + "\n")
        if let identity = input.identity {
            let eventID = String(data: try JSONEncoder().encode(identity), encoding: .utf8)!
            text = text.replacingOccurrences(of: "calendar_event:\n", with: "calendar_event: " + eventID + "\n")
        }
        let temporary = folder.appendingPathComponent(".meeting-" + UUID().uuidString + ".tmp")
        defer { try? files.removeItem(at: temporary) }
        try Data(text.utf8).write(to: temporary, options: .withoutOverwriting)
        try files.setAttributes([.posixPermissions: 0o600], ofItemAtPath: temporary.path)
        // Atomic publication with no replacement, including a racing writer.
        guard Darwin.link(temporary.path, destination.path) == 0 else {
            if errno == EEXIST {
                let info = try destination.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                guard info.isRegularFile == true, info.isSymbolicLink != true else { throw Failure.unsafe }
                return destination
            }
            throw Failure.write
        }
        return destination
    }
}
