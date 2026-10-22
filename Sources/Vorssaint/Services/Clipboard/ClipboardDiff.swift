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
    enum Failure: Error { case tooLarge }
    static let maxBytes = 200_000
    static let maxLines = 2_000

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

    static func lines(for pair: Pair) throws -> [Line] {
        guard pair.older.utf8.count <= maxBytes, pair.newer.utf8.count <= maxBytes else { throw Failure.tooLarge }
        let older = pair.older.components(separatedBy: "\n")
        let newer = pair.newer.components(separatedBy: "\n")
        guard older.count <= maxLines, newer.count <= maxLines else { throw Failure.tooLarge }
        let changes = newer.difference(from: older)
        var removals = Set<Int>(), additions = Set<Int>()
        for change in changes {
            switch change {
            case .remove(let offset, _, _): removals.insert(offset)
            case .insert(let offset, _, _): additions.insert(offset)
            }
        }
        var result: [Line] = [], old = 0, new = 0
        while old < older.count || new < newer.count {
            if removals.contains(old) {
                result.append(Line(kind: .removed, text: older[old])); old += 1
            } else if additions.contains(new) {
                result.append(Line(kind: .added, text: newer[new])); new += 1
            } else {
                result.append(Line(kind: .same, text: older[old])); old += 1; new += 1
            }
        }
        return result
    }
}
