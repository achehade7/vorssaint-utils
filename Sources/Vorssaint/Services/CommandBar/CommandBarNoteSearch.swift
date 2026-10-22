// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Reads local Markdown only on an explicit note or ticket query. Results and
/// file contents are never persisted, and a superseded read cannot update the bar.
final class CommandBarNoteSearch {
    enum Request: Equatable { case previous(String), ticket(String) }
    struct Note {
        let file: URL
        let title: String
        let date: String
        let relativePath: String
        let titleMatch: Bool
    }

    var onResult: (() -> Void)?
    private let vault: URL
    private var task: Task<Void, Never>?
    private var request: Request?
    private var notes: [Note] = []
    private var failed = false
    private var generation = UUID()
    var isAwaiting: Bool { task != nil }

    init(vault: URL = MeetingNoteStore.personal.vault) { self.vault = vault }

    static func query(_ text: String) -> (previous: Bool, filter: String)? {
        var words = text.split(whereSeparator: \.isWhitespace).map(String.init)
        guard words.first?.lowercased() == "note" else { return nil }
        words.removeFirst()
        let previous = words.first?.lowercased() == "prev"
        if previous { words.removeFirst() }
        return (previous, words.joined(separator: " "))
    }

    static func matches(_ title: String, filter: String) -> Bool {
        let title = title.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
        return filter.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
            .split(whereSeparator: \.isWhitespace).allSatisfy { title.contains($0) }
    }

    func reset() {
        generation = UUID()
        task?.cancel(); task = nil
        request = nil; notes = []; failed = false
    }

    func rows(for requested: Request) -> [CommandBarEntry] {
        if request != requested {
            reset()
            request = requested
            let token = generation, vault = vault
            task = Task { @MainActor [weak self] in
                let read = Task.detached(priority: .userInitiated) { try Self.read(vault: vault, request: requested) }
                let result = await withTaskCancellationHandler(operation: { await read.result }, onCancel: { read.cancel() })
                guard let self, !Task.isCancelled, self.generation == token else { return }
                switch result {
                case .success(let notes): self.notes = notes
                case .failure: self.failed = true
                }
                self.task = nil
                self.onResult?()
            }
        }
        if isAwaiting { return [] }
        if notes.isEmpty {
            // A ticket always keeps its Jira result; absence of local matches
            // needs no extra row beside it.
            if case .ticket = requested { return [] }
            return [CommandBarEntry(id: "action.note.history.empty",
                                    title: failed ? MeetingNoteStrings.readFailure(L10n.shared.language)
                                        : FeatureStrings.commandBar(L10n.shared.language).noResultsTitle,
                                    subtitle: "Obsidian · meetings", icon: .symbol("doc.text"),
                                    countsUsage: false, keepsBarOpen: true, run: { _ in })]
        }
        return notes.map { note in
            CommandBarEntry(id: "action.note.file." + note.file.path, title: note.title,
                            subtitle: ["Obsidian", note.date, note.relativePath].filter { !$0.isEmpty }.joined(separator: " · "),
                            icon: .symbol("doc.text"), countsUsage: false, run: { _ in
                // Recheck confinement in case a file was replaced by a symlink
                // between search and activation.
                guard note.file.resolvingSymlinksInPath().path.hasPrefix(self.vault.resolvingSymlinksInPath().path + "/"),
                      FileManager.default.fileExists(atPath: note.file.path),
                      let url = MeetingNoteStore.obsidianURL(note.file) else { return }
                NSWorkspace.shared.open(url)
            })
        }
    }

    static func read(vault: URL, request: Request) throws -> [Note] {
        let root = vault.resolvingSymlinksInPath()
        let folder: URL
        switch request {
        case .previous: folder = root.appendingPathComponent("meetings")
        case .ticket: folder = root
        }
        guard folder.resolvingSymlinksInPath().path == root.path
                || folder.resolvingSymlinksInPath().path.hasPrefix(root.path + "/") else { throw CocoaError(.fileReadNoPermission) }
        let keys: [URLResourceKey] = [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey]
        // Check availability explicitly; enumerator otherwise conflates missing
        // folders with an empty result.
        _ = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        guard let files = FileManager.default.enumerator(at: folder, includingPropertiesForKeys: keys,
                                                        options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return [] }
        let ticket: NSRegularExpression?
        if case .ticket(let key) = request {
            ticket = try NSRegularExpression(pattern: "(?<![A-Za-z0-9_])" + NSRegularExpression.escapedPattern(for: key)
                                             + "(?![A-Za-z0-9_])", options: .caseInsensitive)
        } else { ticket = nil }
        var notes: [Note] = []
        for case let file as URL in files {
            try Task.checkCancellation()
            guard file.pathExtension.lowercased() == "md",
                  let info = try? file.resourceValues(forKeys: Set(keys)), info.isRegularFile == true,
                  info.isSymbolicLink != true, (info.fileSize ?? 0) <= 2_000_000,
                  file.resolvingSymlinksInPath().path.hasPrefix(root.path + "/") else { continue }
            let title = file.deletingPathExtension().lastPathComponent
            if case .previous(let filter) = request, !matches(title, filter: filter) { continue }
            guard let body = try? String(contentsOf: file, encoding: .utf8) else { continue }
            let titleMatch = ticket?.firstMatch(in: title, range: NSRange(title.startIndex..., in: title)) != nil
            if let ticket, !titleMatch,
               ticket.firstMatch(in: body, range: NSRange(body.startIndex..., in: body)) == nil { continue }
            var date = ""
            if body.hasPrefix("---\n"), let end = body.range(of: "\n---", range: body.index(body.startIndex, offsetBy: 4)..<body.endIndex),
               let line = body[..<end.lowerBound].split(separator: "\n").first(where: { $0.hasPrefix("date:") }) {
                date = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces.union(CharacterSet(charactersIn: "\"'")))
            }
            if date.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) == nil {
                date = String(title.prefix(10))
                if date.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) == nil { date = "" }
            }
            notes.append(Note(file: file, title: title, date: date,
                              relativePath: String(file.path.dropFirst(root.path.count + 1)), titleMatch: titleMatch))
        }
        return Array(notes.sorted {
            if $0.titleMatch != $1.titleMatch { return $0.titleMatch }
            if $0.date != $1.date { return $0.date > $1.date }
            return $0.relativePath.localizedStandardCompare($1.relativePath) == .orderedAscending
        }.prefix(40))
    }
}
