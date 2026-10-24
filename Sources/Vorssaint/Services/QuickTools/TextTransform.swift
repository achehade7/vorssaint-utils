// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// Local transformations of a captured selection. Choices are evaluated against the same input.
enum TextTransform {
    enum Kind: CaseIterable, Sendable {
        case joinLines, cleanSpacing, formatJSON, decodeURL, decodeBase64
    }
    struct Choice: Sendable {
        let kind: Kind
        let text: String
    }
    static let maxBytes = ClipboardJSONFormat.maxBytes

    static func choices(for text: String) -> [Choice] {
        guard text.utf8.count <= maxBytes else { return [] }
        return Kind.allCases.compactMap { kind in
            guard let result = apply(kind, to: text), !result.isEmpty,
                  !result.utf8.elementsEqual(text.utf8) else { return nil }
            return Choice(kind: kind, text: result)
        }
    }

    static func apply(_ kind: Kind, to text: String) -> String? {
        guard text.utf8.count <= maxBytes else { return nil }
        switch kind {
        case .joinLines:
            guard text.contains(where: \.isNewline) else { return nil }
            return text.split(whereSeparator: \.isNewline)
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }.joined(separator: " ")
        case .cleanSpacing:
            // Keep line/paragraph boundaries; collapse horizontal spacing and surplus blank lines.
            let lines = text.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline).map {
                $0.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            }
            var cleaned: [String] = []
            for line in lines {
                if !line.isEmpty || (cleaned.last.map { !$0.isEmpty } ?? false) { cleaned.append(line) }
            }
            if cleaned.last == "" { cleaned.removeLast() }
            return cleaned.joined(separator: "\n")
        case .formatJSON:
            // The existing formatter preserves property order, escapes and exact number spelling.
            return ClipboardJSONFormat.pretty(text)
        case .decodeURL:
            guard text.contains("%"), let decoded = text.removingPercentEncoding,
                  isReadable(decoded) else { return nil }
            // '+' is literal URL text; form-urlencoded conversion is a separate operation.
            return decoded
        case .decodeBase64:
            let encoded = text.filter { !$0.isWhitespace }
            guard !encoded.isEmpty, let data = Data(base64Encoded: encoded),
                  let decoded = String(data: data, encoding: .utf8), isReadable(decoded) else { return nil }
            return decoded
        }
    }

    private static func isReadable(_ text: String) -> Bool {
        !text.isEmpty && !text.unicodeScalars.contains {
            $0.properties.generalCategory == .control && !CharacterSet.whitespacesAndNewlines.contains($0)
        }
    }
}
