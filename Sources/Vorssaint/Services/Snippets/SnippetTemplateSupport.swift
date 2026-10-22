// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// Simple named fields; the existing date/time/clipboard variables keep their meaning.
enum SnippetTemplateSupport {
    private static let regex = try! NSRegularExpression(pattern: #"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}"#)
    private static let reserved: Set<String> = ["date", "time", "datetime", "clipboard"]

    static func fields(in text: String) -> [String] {
        var seen = Set<String>()
        return regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap { match in
            guard let range = Range(match.range(at: 1), in: text) else { return nil }
            let name = String(text[range])
            return !reserved.contains(name) && seen.insert(name).inserted ? name : nil
        }
    }

    static func fill(_ text: String, values: [String: String]) -> String {
        var result = text
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).reversed() {
            guard let nameRange = Range(match.range(at: 1), in: text),
                  !reserved.contains(String(text[nameRange])), let value = values[String(text[nameRange])],
                  let range = Range(match.range, in: result) else { continue }
            result.replaceSubrange(range, with: value)
        }
        return result
    }
}
