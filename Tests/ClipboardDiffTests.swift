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
            ("a\r\nb", "a\nb"), (" a\t\n", "a\n"),
            ("café", "cafe\u{301}"), ("👩🏽‍💻", "👩🏻‍💻"),
            ("a\n", "a\n\n"), ("\n\n", "\n")
        ]
        func checkRoundTrip(_ old: String, _ new: String) {
            let lines = try! ClipboardDiff.lines(for: .init(older: old, newer: new))
            suite.expect(lines.filter { $0.kind != .added }.map(\.text).joined(separator: "\n").utf8.elementsEqual(old.utf8),
                         "diff reconstructs the complete older text")
            suite.expect(lines.filter { $0.kind != .removed }.map(\.text).joined(separator: "\n").utf8.elementsEqual(new.utf8),
                         "diff reconstructs the complete newer text")
            let comparison = try! ClipboardDiff.compare(.init(older: old, newer: new))
            for (source, rows) in [(old, comparison.rows.compactMap(\.before)),
                                   (new, comparison.rows.compactMap(\.after))] {
                suite.expect(rows.map(\.number) == Array(1...rows.count), "source lines retain their real line numbers")
                suite.expect(rows.map(\.text).joined(separator: "\n").utf8.elementsEqual(source.utf8),
                             "aligned rows never insert, drop or normalize editable content")
                for line in rows {
                    suite.expect((source as NSString).substring(with: line.range).utf8.elementsEqual(line.text.utf8),
                                 "every source range indexes the exact original UTF-16 text")
                    var boundaries: Set<Int> = [line.range.location]
                    var location = line.range.location
                    for character in line.text { location += character.utf16.count; boundaries.insert(location) }
                    suite.expect(line.changedRanges.allSatisfy {
                        boundaries.contains($0.location) && boundaries.contains(NSMaxRange($0))
                    }, "highlights never split a composed character or extend outside its line")
                }
            }
            suite.expect(comparison.rows.filter { $0.kind == .same }.allSatisfy {
                $0.before!.text.utf8.elementsEqual($0.after!.text.utf8)
            }, "unchanged rows use byte-exact equality")
            suite.expect(comparison.isIdentical == old.utf8.elementsEqual(new.utf8),
                         "identical state means exact original content")
            for row in comparison.rows where row.kind == .changed {
                let before = row.before!, after = row.after!
                var oldOffset = before.range.location, newOffset = after.range.location
                suite.expect(before.changedRanges.count == after.changedRanges.count,
                             "each intraline change has an opposite span or insertion anchor")
                for (oldRange, newRange) in zip(before.changedRanges, after.changedRanges) {
                    let unchangedOld = (old as NSString).substring(with: NSRange(location: oldOffset, length: oldRange.location - oldOffset))
                    let unchangedNew = (new as NSString).substring(with: NSRange(location: newOffset, length: newRange.location - newOffset))
                    suite.expect(unchangedOld.utf8.elementsEqual(unchangedNew.utf8),
                                 "text between highlighted spans is byte-exact on both sides")
                    oldOffset = NSMaxRange(oldRange); newOffset = NSMaxRange(newRange)
                }
                let suffixOld = (old as NSString).substring(with: NSRange(location: oldOffset, length: NSMaxRange(before.range) - oldOffset))
                let suffixNew = (new as NSString).substring(with: NSRange(location: newOffset, length: NSMaxRange(after.range) - newOffset))
                suite.expect(suffixOld.utf8.elementsEqual(suffixNew.utf8), "no changed suffix escapes highlighting")
            }
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
        let unicodeTokens = ["α", "é", "e\u{301}", "👩🏽‍💻", "👩🏻‍💻", " ", "\t", "x"]
        for _ in 0..<50 {
            let old = (0..<number(20)).map { _ in unicodeTokens[number(unicodeTokens.count)] }.joined()
            let new = (0..<number(20)).map { _ in unicodeTokens[number(unicodeTokens.count)] }.joined()
            checkRoundTrip(old, new)
        }
        let aligned = try! ClipboardDiff.compare(.init(older: "heading\nold\nkeep\nend",
                                                       newer: "heading\nnew\nextra\nkeep\nlast"))
        suite.expect(aligned.rows.map(\.kind) == [.same, .changed, .added, .same, .changed],
                     "replacement rows pair text while insertions create an absent opposite line")
        suite.expect(aligned.rows[2].before == nil && aligned.rows[2].after?.number == 3,
                     "a missing line is metadata, never fake text")
        suite.expect(aligned.groups == [1..<3, 4..<5], "navigation groups contiguous changed rows")
        suite.expect(aligned.changedLines == 2 && aligned.addedLines == 1 && aligned.removedLines == 0,
                     "summary counts replacements once and additions separately")

        let correction = try! ClipboardDiff.compare(.init(older: "total = 100", newer: "total = 120"))
        suite.expect(correction.rows[0].before?.changedRanges == [NSRange(location: 9, length: 1)]
                     && correction.rows[0].after?.changedRanges == [NSRange(location: 9, length: 1)],
                     "a one-character correction highlights exactly that character")
        let separated = try! ClipboardDiff.compare(.init(older: "foo = 10; bar = 20", newer: "foo = 11; bar = 21"))
        suite.expect(separated.rows[0].before?.changedRanges == [NSRange(location: 7, length: 1), NSRange(location: 17, length: 1)],
                     "independent edits within one line retain their separate narrow highlights")
        let unicode = try! ClipboardDiff.compare(.init(older: "top\nx👩🏽‍💻y café", newer: "top\nx👩🏻‍💻y cafe\u{301}"))
        suite.expect(unicode.rows[1].before?.changedRanges == [NSRange(location: 5, length: 7), NSRange(location: 17, length: 1)]
                     && unicode.rows[1].after?.changedRanges == [NSRange(location: 5, length: 7), NSRange(location: 17, length: 2)],
                     "emoji are highlighted whole and canonical-equivalent code units remain visible")
        let inserted = try! ClipboardDiff.compare(.init(older: "cat", newer: "cats"))
        suite.expect(inserted.rows[0].before?.changedRanges == [NSRange(location: 3, length: 0)]
                     && inserted.rows[0].after?.changedRanges == [NSRange(location: 3, length: 1)],
                     "an intraline insertion preserves an exact zero-width anchor on the other side")
        let crlf = try! ClipboardDiff.compare(.init(older: "a\r\nb", newer: "a\nb"))
        suite.expect(crlf.rows[0].before?.changedRanges == [NSRange(location: 1, length: 1)]
                     && crlf.rows[1].before?.range == NSRange(location: 3, length: 1)
                     && crlf.rows[1].after?.range == NSRange(location: 2, length: 1),
                     "CRLF remains an observable difference and offsets include all original separators")
        let whitespace = try! ClipboardDiff.compare(.init(older: "x \t", newer: "x  "))
        suite.expect(whitespace.rows[0].before?.changedRanges == [NSRange(location: 2, length: 1)],
                     "whitespace-only changes remain visible")

        let longPrefix = String(repeating: "x", count: 99_999)
        let longSuffix = String(repeating: "y", count: 100_000)
        let longCorrection = try! ClipboardDiff.compare(.init(older: longPrefix + "a" + longSuffix,
                                                              newer: longPrefix + "b" + longSuffix))
        suite.expect(longCorrection.rows[0].before?.changedRanges == [NSRange(location: 99_999, length: 1)],
                     "a narrow edit stays narrow at the maximum byte length")
        let unrelated = try! ClipboardDiff.compare(.init(older: String(repeating: "a", count: 200_000),
                                                         newer: String(repeating: "b", count: 200_000)))
        suite.expect(unrelated.rows[0].before?.changedRanges == [NSRange(location: 0, length: 200_000)],
                     "unrelated long lines complete with bounded intraline work")
        let manyLines = try! ClipboardDiff.compare(.init(older: (0..<2_000).map { "old \($0)" }.joined(separator: "\n"),
                                                        newer: (0..<2_000).map { "new \($0)" }.joined(separator: "\n")))
        suite.expect(manyLines.changedLines == 2_000 && manyLines.groups == [0..<2_000],
                     "unrelated maximum-line inputs complete and retain every line")

        let finished = DispatchSemaphore(value: 0)
        Task.detached {
            withUnsafeCurrentTask { $0?.cancel() }
            defer { finished.signal() }
            do {
                _ = try ClipboardDiff.compare(.init(older: "old", newer: "new"))
                suite.expect(false, "cancelled comparison must stop")
            } catch is CancellationError {
                suite.expect(true, "background comparison honors task cancellation")
            } catch {
                suite.expect(false, "unexpected cancellation error")
            }
        }
        suite.expect(finished.wait(timeout: .now() + 5) == .success, "cancelled background work returns promptly")
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
        jsonFormatting(suite)
        for language in AppLanguage.allCases {
            let strings = ClipboardDiffStrings.localized(language)
            suite.expect([strings.title, strings.subtitle, strings.legend, strings.missing, strings.tooLarge,
                          strings.loading, strings.identical, strings.before, strings.after].allSatisfy { !$0.isEmpty },
                         "diff strings cover every app language")
        }
    }

    private static func jsonFormatting(_ suite: TestSuite) {
        let source = #"{"z":[1.2300,{},[true,false,null]],"a":900719925474099312345,"a":-0.00000000000000000001e+20,"s":"\u0061\/\\\"é"}"#
        let expected = #"""
        {
          "z": [
            1.2300,
            {},
            [
              true,
              false,
              null
            ]
          ],
          "a": 900719925474099312345,
          "a": -0.00000000000000000001e+20,
          "s": "\u0061\/\\\"é"
        }
        """#
        let formatted = try! ClipboardDiff.formatJSON(source)
        suite.expect(formatted.utf8.elementsEqual(expected.utf8),
                     "JSON formatting preserves key order, duplicate keys, precise numeric tokens and literal Unicode escapes")
        suite.expect((try! ClipboardDiff.formatJSON(formatted)).utf8.elementsEqual(formatted.utf8),
                     "formatting an already formatted JSON draft is unchanged")
        suite.expect(try! ClipboardDiff.formatJSON("[1,{\"a\":2},[]]") == "[\n  1,\n  {\n    \"a\": 2\n  },\n  []\n]",
                     "top-level JSON arrays and nested objects use the existing two-space layout")
        suite.expect(try! ClipboardDiff.formatJSON(" { } \r\n") == "{}", "empty objects format without extra blank lines")

        func rejects(_ text: String, as expected: ClipboardDiff.Failure) {
            do {
                _ = try ClipboardDiff.formatJSON(text)
                suite.expect(false, "formatting must reject \(expected)")
            } catch let actual as ClipboardDiff.Failure {
                suite.expect(actual == expected, "formatting reports \(expected), received \(actual)")
            } catch {
                suite.expect(false, "unexpected JSON formatting failure: \(error)")
            }
        }
        for invalid in ["", "plain text", "42", "null", #"{"a":}"#, #"[1] trailing"#, #"{"a":"\q"}"#] {
            rejects(invalid, as: .invalidJSON)
        }
        // Match the shared formatter's native parser compatibility without
        // repairing or dropping trailing commas in the user's draft.
        let trailingComma = #"{"a":[1,],}"#
        if let shared = ClipboardJSONFormat.pretty(trailingComma) {
            suite.expect((try! ClipboardDiff.formatJSON(trailingComma)).utf8.elementsEqual(shared.utf8),
                         "native-parser trailing comma compatibility preserves the original comma tokens")
        } else {
            rejects(trailingComma, as: .invalidJSON)
        }

        let atInputByteLimit = "[" + String(repeating: " ", count: ClipboardDiff.maxBytes - 2) + "]"
        suite.expect(try! ClipboardDiff.formatJSON(atInputByteLimit) == "[]", "input byte limit is inclusive")
        rejects(atInputByteLimit + " ", as: .tooLarge)
        rejects("[\"" + String(repeating: "é", count: ClipboardDiff.maxBytes / 2) + "\"]", as: .tooLarge)
        suite.expect(try! ClipboardDiff.formatJSON(String(repeating: "\n", count: ClipboardDiff.maxLines - 1) + "[]") == "[]",
                     "input line limit is inclusive")
        rejects(String(repeating: "\n", count: ClipboardDiff.maxLines) + "[]", as: .tooLarge)

        let atOutputByteLimit = "[\"" + String(repeating: "x", count: ClipboardDiff.maxBytes - 8) + "\"]"
        suite.expect((try! ClipboardDiff.formatJSON(atOutputByteLimit)).utf8.count == ClipboardDiff.maxBytes,
                     "actual formatted output byte limit is inclusive")
        rejects("[\"" + String(repeating: "x", count: ClipboardDiff.maxBytes - 7) + "\"]", as: .formattedTooLarge)
        let atOutputLineLimit = "[" + Array(repeating: "0", count: ClipboardDiff.maxLines - 2).joined(separator: ",") + "]"
        suite.expect((try! ClipboardDiff.formatJSON(atOutputLineLimit)).components(separatedBy: "\n").count == ClipboardDiff.maxLines,
                     "formatted output line limit is inclusive")
        let beyondOutputLines = "[" + Array(repeating: "0", count: ClipboardDiff.maxLines - 1).joined(separator: ",") + "]"
        rejects(beyondOutputLines, as: .formattedTooLarge)
    }
}
