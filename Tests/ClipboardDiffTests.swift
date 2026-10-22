// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum ClipboardDiffTests {
    static func run(_ suite: TestSuite) {
        let past = Date(timeIntervalSince1970: 10)
        let history = [
            ClipboardHistoryEntry(text: "pinned", copiedAt: past, pinnedAt: past),
            ClipboardHistoryEntry(text: "", copiedAt: past.addingTimeInterval(5), kind: .image),
            ClipboardHistoryEntry(text: "", copiedAt: past.addingTimeInterval(4), kind: .files),
            ClipboardHistoryEntry(text: "new", copiedAt: past.addingTimeInterval(3)),
            ClipboardHistoryEntry(text: "old", copiedAt: past.addingTimeInterval(2)),
        ]
        let pair = ClipboardDiff.latestPair(in: history)
        suite.expect(pair?.older == "old" && pair?.newer == "new", "diff uses copy times, ignoring pin order, images and files")
        suite.expect(ClipboardDiff.latestPair(in: []) == nil, "empty history can open manual diff")
        suite.expect(ClipboardDiff.latestPair(in: Array(history.prefix(3))) == nil, "one text is not a pair")
        let tie = ClipboardDiff.latestPair(in: [.init(text: "first", copiedAt: past), .init(text: "second", copiedAt: past)])
        suite.expect(tie?.newer == "first" && tie?.older == "second", "equal timestamps retain history order")

        let changed = try! ClipboardDiff.lines(for: .init(older: "same\nold\nend", newer: "same\nnew\nend"))
        suite.expect(changed.map(\.kind) == [.same, .removed, .added, .same], "line replacement keeps context and removes before adding")
        suite.expect(changed.map(\.text) == ["same", "old", "new", "end"], "replacement text is exact")
        suite.expect(changed.map(\.prefix) == ["  ", "− ", "+ ", "  "], "changes have non-color markers")

        let samples = [
            ("", ""), ("", "added"), ("removed", ""),
            ("a\na\nb", "a\nb\na"), ("a\n\nb\n", "a\nb"),
            ("{\n  \"x\": 1\n}", "{\n  \"x\": 2\n}"),
            ("α\n👩🏽‍💻\ncafé", "α\n👩🏽‍💻\ncafe"),
            ("a\r\nb", "a\nb"), (" a\t\n", "a\n")
        ]
        func checkRoundTrip(_ old: String, _ new: String) {
            let lines = try! ClipboardDiff.lines(for: .init(older: old, newer: new))
            suite.expect(lines.filter { $0.kind != .added }.map(\.text).joined(separator: "\n") == old,
                         "diff reconstructs the complete older text")
            suite.expect(lines.filter { $0.kind != .removed }.map(\.text).joined(separator: "\n") == new,
                         "diff reconstructs the complete newer text")
        }
        for (old, new) in samples { checkRoundTrip(old, new) }
        var seed: UInt64 = 17
        func number(_ limit: Int) -> Int {
            seed = seed &* 6364136223846793005 &+ 1
            return Int((seed >> 32) % UInt64(limit))
        }
        for _ in 0..<100 {
            let old = (0..<number(20)).map { _ in String(number(5)) }.joined(separator: "\n")
            let new = (0..<number(20)).map { _ in String(number(5)) }.joined(separator: "\n")
            checkRoundTrip(old, new)
        }
        for text in [String(repeating: "x", count: ClipboardDiff.maxBytes + 1),
                     String(repeating: "é", count: ClipboardDiff.maxBytes / 2 + 1),
                     String(repeating: "\n", count: ClipboardDiff.maxLines)] {
            for pair in [ClipboardDiff.Pair(older: text, newer: "a"), .init(older: "a", newer: text)] {
                do { _ = try ClipboardDiff.lines(for: pair); suite.expect(false, "oversized input must be rejected") }
                catch ClipboardDiff.Failure.tooLarge { suite.expect(true, "oversized input rejected without truncation") }
                catch { suite.expect(false, "unexpected diff failure") }
            }
        }
        for text in [String(repeating: "x", count: ClipboardDiff.maxBytes),
                     String(repeating: "\n", count: ClipboardDiff.maxLines - 1)] {
            let lines = try! ClipboardDiff.lines(for: .init(older: text, newer: text))
            suite.expect(lines.allSatisfy { $0.kind == .same }, "limits are inclusive and identical text has no changes")
        }
        for language in AppLanguage.allCases {
            let strings = ClipboardDiffStrings.localized(language)
            suite.expect([strings.title, strings.subtitle, strings.legend, strings.missing, strings.tooLarge,
                          strings.loading, strings.identical, strings.before, strings.after].allSatisfy { !$0.isEmpty },
                         "diff strings cover every app language")
        }
    }
}
