// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum ClipboardDiff {
    struct Pair: Sendable {
        let older: String
        let newer: String
    }
    enum Kind: Equatable, Sendable { case same, removed, added }
    struct Line: Equatable, Sendable {
        let kind: Kind
        let text: String
        var prefix: String {
            switch kind { case .same: return "  "; case .removed: return "− "; case .added: return "+ " }
        }
    }
    enum RowKind: Equatable, Sendable { case same, changed, removed, added }
    struct SourceLine: Equatable, Sendable {
        let number: Int
        let text: String
        // Ranges are in the original editor's UTF-16 coordinates. LF separators
        // are excluded; CR, whitespace and trailing empty lines remain exact.
        let range: NSRange
        var changedRanges: [NSRange] = []
    }
    struct Row: Equatable, Sendable {
        let before: SourceLine?
        let after: SourceLine?
        let kind: RowKind
    }
    struct Comparison: Sendable {
        let rows: [Row]
        let groups: [Range<Int>]
        let addedLines: Int
        let removedLines: Int
        let changedLines: Int
        var isIdentical: Bool { groups.isEmpty }
    }
    enum Failure: Error { case tooLarge, invalidJSON, formattedTooLarge }
    static let maxBytes = 200_000
    static let maxLines = 2_000

    static func formatJSON(_ text: String) throws -> String {
        try Task.checkCancellation()
        guard text.utf8.count <= maxBytes, text.components(separatedBy: "\n").count <= maxLines else {
            throw Failure.tooLarge
        }
        guard let formatted = ClipboardJSONFormat.pretty(text) else { throw Failure.invalidJSON }
        try Task.checkCancellation()
        guard formatted.utf8.count <= maxBytes, formatted.components(separatedBy: "\n").count <= maxLines else {
            throw Failure.formattedTooLarge
        }
        return formatted
    }

    // History's display order puts pinned entries first. Compare copy times,
    // and leave images, files and the history itself untouched.
    static func latestPair(in entries: [ClipboardHistoryEntry]) -> Pair? {
        let texts = entries.enumerated().filter { $0.element.kind == .text }
            .sorted {
                if $0.element.copiedAt == $1.element.copiedAt { return $0.offset < $1.offset }
                return $0.element.copiedAt > $1.element.copiedAt
            }.prefix(2).map(\.element.text)
        guard texts.count == 2 else { return nil }
        return Pair(older: texts[1], newer: texts[0])
    }

    static func compare(_ pair: Pair) throws -> Comparison {
        try Task.checkCancellation()
        guard pair.older.utf8.count <= maxBytes, pair.newer.utf8.count <= maxBytes else { throw Failure.tooLarge }
        let older = sourceLines(pair.older)
        let newer = sourceLines(pair.newer)
        guard older.count <= maxLines, newer.count <= maxLines else { throw Failure.tooLarge }

        // Swift String equality folds canonical Unicode equivalents. The editor
        // must instead reveal differences in the original clipboard contents.
        var identifiers: [Data: Int] = [:]
        func ids(_ lines: [SourceLine]) -> [Int] {
            lines.map { line in
                let key = Data(line.text.utf8)
                if let id = identifiers[key] { return id }
                let id = identifiers.count
                identifiers[key] = id
                return id
            }
        }
        let oldIDs = ids(older), newIDs = ids(newer)
        let matches = try matchingPairs(oldCount: older.count, newCount: newer.count) { oldIDs[$0] == newIDs[$1] }
        var rows: [Row] = [], old = 0, new = 0
        // Bound total intraline work as well as each individual replacement.
        var characterBudget = 1_000_000
        for (oldMatch, newMatch) in matches + [(older.count, newer.count)] {
            try Task.checkCancellation()
            while old < oldMatch || new < newMatch {
                if old < oldMatch && new < newMatch {
                    var before = older[old], after = newer[new]
                    (before.changedRanges, after.changedRanges) = try changedRanges(
                        before: before, after: after, budget: &characterBudget)
                    rows.append(Row(before: before, after: after, kind: .changed))
                    old += 1; new += 1
                } else if old < oldMatch {
                    var before = older[old]
                    before.changedRanges = [before.range]
                    rows.append(Row(before: before, after: nil, kind: .removed))
                    old += 1
                } else {
                    var after = newer[new]
                    after.changedRanges = [after.range]
                    rows.append(Row(before: nil, after: after, kind: .added))
                    new += 1
                }
            }
            if oldMatch < older.count {
                rows.append(Row(before: older[oldMatch], after: newer[newMatch], kind: .same))
                old += 1; new += 1
            }
        }
        var groups: [Range<Int>] = []
        for index in rows.indices where rows[index].kind != .same {
            if let last = groups.last, last.upperBound == index {
                groups[groups.count - 1] = last.lowerBound..<(index + 1)
            } else {
                groups.append(index..<(index + 1))
            }
        }
        return Comparison(rows: rows, groups: groups,
                          addedLines: rows.filter { $0.kind == .added }.count,
                          removedLines: rows.filter { $0.kind == .removed }.count,
                          changedLines: rows.filter { $0.kind == .changed }.count)
    }

    static func lines(for pair: Pair) throws -> [Line] {
        let comparison = try compare(pair)
        var result: [Line] = [], index = 0
        while index < comparison.rows.count {
            let row = comparison.rows[index]
            if row.kind == .same {
                result.append(Line(kind: .same, text: row.before!.text))
                index += 1
            } else {
                let start = index
                while index < comparison.rows.count && comparison.rows[index].kind != .same { index += 1 }
                let group = comparison.rows[start..<index]
                result += group.compactMap { $0.before.map { Line(kind: .removed, text: $0.text) } }
                result += group.compactMap { $0.after.map { Line(kind: .added, text: $0.text) } }
            }
        }
        return result
    }

    private static func sourceLines(_ text: String) -> [SourceLine] {
        var location = 0
        return text.components(separatedBy: "\n").enumerated().map { number, text in
            let range = NSRange(location: location, length: text.utf16.count)
            location += range.length + 1
            return SourceLine(number: number + 1, text: text, range: range)
        }
    }

    // Prefix/suffix trimming makes identical inputs and a small edit in a long
    // line linear. The remaining LCS matrix is bounded by the input line limit
    // or the explicit character budget below, and checks cancellation per row.
    private static func matchingPairs(oldCount: Int, newCount: Int,
                                      equal: (Int, Int) -> Bool) throws -> [(Int, Int)] {
        var prefix = 0, suffix = 0
        while prefix < min(oldCount, newCount), equal(prefix, prefix) {
            if prefix % 1024 == 0 { try Task.checkCancellation() }
            prefix += 1
        }
        while suffix < min(oldCount, newCount) - prefix,
              equal(oldCount - suffix - 1, newCount - suffix - 1) {
            if suffix % 1024 == 0 { try Task.checkCancellation() }
            suffix += 1
        }
        let oldMiddle = oldCount - prefix - suffix, newMiddle = newCount - prefix - suffix
        var result = (0..<prefix).map { ($0, $0) }
        if oldMiddle > 0 && newMiddle > 0 {
            let width = newMiddle + 1
            var lengths = [UInt16](repeating: 0, count: (oldMiddle + 1) * width)
            for old in stride(from: oldMiddle - 1, through: 0, by: -1) {
                try Task.checkCancellation()
                for new in stride(from: newMiddle - 1, through: 0, by: -1) {
                    let index = old * width + new
                    lengths[index] = equal(old + prefix, new + prefix)
                        ? lengths[index + width + 1] + 1
                        : max(lengths[index + width], lengths[index + 1])
                }
            }
            var old = 0, new = 0
            while old < oldMiddle && new < newMiddle {
                if equal(old + prefix, new + prefix) {
                    result.append((old + prefix, new + prefix)); old += 1; new += 1
                } else if lengths[(old + 1) * width + new] >= lengths[old * width + new + 1] {
                    old += 1
                } else {
                    new += 1
                }
            }
        }
        result += (0..<suffix).map { (oldCount - suffix + $0, newCount - suffix + $0) }
        return result
    }

    private struct Grapheme {
        let range: NSRange
        let hash: UInt64
    }

    private static func graphemes(_ text: String, units: [UInt16]) throws -> [Grapheme] {
        var result: [Grapheme] = [], location = 0
        for character in text {
            if result.count % 1024 == 0 { try Task.checkCancellation() }
            let length = character.utf16.count
            var hash: UInt64 = 14695981039346656037
            for unit in units[location..<(location + length)] { hash = (hash ^ UInt64(unit)) &* 1099511628211 }
            result.append(Grapheme(range: NSRange(location: location, length: length), hash: hash))
            location += length
        }
        return result
    }

    private static func changedRanges(before: SourceLine, after: SourceLine,
                                      budget: inout Int) throws -> ([NSRange], [NSRange]) {
        let oldUnits = Array(before.text.utf16), newUnits = Array(after.text.utf16)
        let older = try graphemes(before.text, units: oldUnits)
        let newer = try graphemes(after.text, units: newUnits)
        func equal(_ old: Int, _ new: Int) -> Bool {
            let a = older[old], b = newer[new]
            return a.hash == b.hash && a.range.length == b.range.length
                && oldUnits[a.range.location..<NSMaxRange(a.range)]
                    .elementsEqual(newUnits[b.range.location..<NSMaxRange(b.range)])
        }
        var prefix = 0, suffix = 0
        while prefix < min(older.count, newer.count), equal(prefix, prefix) {
            if prefix % 1024 == 0 { try Task.checkCancellation() }
            prefix += 1
        }
        while suffix < min(older.count, newer.count) - prefix,
              equal(older.count - suffix - 1, newer.count - suffix - 1) {
            if suffix % 1024 == 0 { try Task.checkCancellation() }
            suffix += 1
        }
        let oldEnd = older.count - suffix, newEnd = newer.count - suffix
        let cells = (oldEnd - prefix) * (newEnd - prefix)
        var matches: [(Int, Int)] = []
        if cells <= min(budget, 250_000) {
            budget -= cells
            matches = try matchingPairs(oldCount: oldEnd - prefix, newCount: newEnd - prefix) {
                equal($0 + prefix, $1 + prefix)
            }.map { ($0.0 + prefix, $0.1 + prefix) }
        }
        func span(_ atoms: [Grapheme], from start: Int, to end: Int, line: SourceLine) -> NSRange {
            let location = start < atoms.count ? atoms[start].range.location : line.range.length
            let finish = end > start ? NSMaxRange(atoms[end - 1].range) : location
            return NSRange(location: line.range.location + location, length: finish - location)
        }
        var old = prefix, new = prefix, oldRanges: [NSRange] = [], newRanges: [NSRange] = []
        for (oldMatch, newMatch) in matches + [(oldEnd, newEnd)] {
            if old < oldMatch || new < newMatch {
                oldRanges.append(span(older, from: old, to: oldMatch, line: before))
                newRanges.append(span(newer, from: new, to: newMatch, line: after))
            }
            old = oldMatch + 1; new = newMatch + 1
        }
        return (oldRanges, newRanges)
    }
}
