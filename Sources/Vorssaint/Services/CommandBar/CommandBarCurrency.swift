// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// Direct currency expressions reuse the installed ECB helper and rate cache.
enum CommandBarCurrency {
    static let helper = CommandBarLink(name: "Currency conversion", kind: .script,
                                       destination: "~/.local/bin/vorssaint-fx")
    private static let codes = Set(Locale.commonISOCurrencyCodes.map { $0.lowercased() })
    private static let names = [
        "euro": "EUR", "euros": "EUR",
        "dollar": "USD", "dollars": "USD", "us dollar": "USD", "us dollars": "USD",
        "pound": "GBP", "pounds": "GBP", "sterling": "GBP",
        "british pound": "GBP", "british pounds": "GBP",
        "swiss franc": "CHF", "swiss francs": "CHF",
        "yen": "JPY", "japanese yen": "JPY",
        "canadian dollar": "CAD", "canadian dollars": "CAD",
        "australian dollar": "AUD", "australian dollars": "AUD",
    ]
    private static let expression = try! NSRegularExpression(
        pattern: #"^([+-]?[0-9]{1,12}(?:[.,][0-9]{1,6})?)\s+(.+?)\s+to\s+(.+)$"#)

    static func argument(for query: String) -> String? {
        guard query.count <= 160 else { return nil }
        let text = query.lowercased().split(whereSeparator: \.isWhitespace).joined(separator: " ")
        let range = NSRange(text.startIndex..., in: text)
        guard let match = expression.firstMatch(in: text, range: range) else { return nil }
        let parts = (1...3).map { (text as NSString).substring(with: match.range(at: $0)) }
        func code(_ word: String) -> String? {
            names[word] ?? (codes.contains(word) ? word.uppercased() : nil)
        }
        guard let source = code(parts[1]), let target = code(parts[2]) else { return nil }
        return "\(parts[0]) \(source) to \(target)"
    }
}
