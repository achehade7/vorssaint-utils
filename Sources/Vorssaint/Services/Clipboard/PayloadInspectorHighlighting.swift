// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Color the existing read-only value without decoding, formatting or changing it.
enum PayloadInspectorHighlighting {
    static let propertyColor = ToolAppearance.accent
    private static let booleanColor = NSColor(name: NSColor.Name("Vorssaint.Payload.Boolean")) { appearance in
        if appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua {
            return NSColor(srgbRed: 0.47, green: 0.78, blue: 0.66, alpha: 1)
        }
        return NSColor(srgbRed: 0.13, green: 0.42, blue: 0.31, alpha: 1)
    }

    static func valueColor(for kind: PayloadInspector.Kind) -> NSColor {
        switch kind {
        case .number: return ToolAppearance.before
        case .boolean: return booleanColor
        case .null: return ToolAppearance.secondaryText
        case .object, .array: return ToolAppearance.text
        case .string, .element, .attribute, .text: return ToolAppearance.after
        }
    }

    static func attributed(_ text: String, kind: PayloadInspector.Kind, font: NSFont) -> NSAttributedString {
        let result = NSMutableAttributedString(string: text, attributes: [
            .font: font, .foregroundColor: valueColor(for: kind)
        ])
        // JSON strings and XML leaves are already decoded values. Text resembling
        // JSON or XML inside them must remain a single value, not become syntax.
        guard kind == .object || kind == .array else { return result }
        // UTF-16 offsets match NSAttributedString, including non-BMP property names.
        let units = Array(text.utf16)
        var index = 0
        func paint(_ start: Int, _ end: Int, _ color: NSColor) {
            result.addAttribute(.foregroundColor, value: color, range: NSRange(location: start, length: end - start))
        }
        func isSpace(_ unit: UInt16) -> Bool { unit == 32 || unit == 9 || unit == 10 || unit == 13 }
        while index < units.count {
            let start = index
            switch units[index] {
            case 34: // A quoted token is a property only when followed by a colon.
                index += 1
                while index < units.count {
                    let unit = units[index]
                    index += 1
                    if unit == 92 { index = min(index + 1, units.count) }
                    else if unit == 34 { break }
                }
                var next = index
                while next < units.count && isSpace(units[next]) { next += 1 }
                let property = next < units.count && units[next] == 58
                paint(start, index, property ? propertyColor : valueColor(for: .string))
            case 45, 48...57:
                index += 1
                while index < units.count && ((48...57).contains(units[index])
                    || [45, 43, 46, 69, 101].contains(units[index])) { index += 1 }
                paint(start, index, valueColor(for: .number))
            case 116, 102, 110:
                while index < units.count && (97...122).contains(units[index]) { index += 1 }
                let literal = String(decoding: units[start..<index], as: UTF16.self)
                if literal == "true" || literal == "false" { paint(start, index, valueColor(for: .boolean)) }
                else if literal == "null" { paint(start, index, valueColor(for: .null)) }
            case 123, 125, 91, 93, 58, 44:
                index += 1
                paint(start, index, ToolAppearance.secondaryText)
            default: index += 1
            }
        }
        return result
    }
}
