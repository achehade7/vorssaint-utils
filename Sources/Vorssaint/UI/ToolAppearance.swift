// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Shared chrome for native tools; content keeps its normal AppKit behavior.
enum ToolAppearance {
    static let background = color("background", light: 0xF4F3F8, dark: 0x101015)
    static let surface = color("surface", light: 0xFCFBFF, dark: 0x121218)
    static let raised = color("raised", light: 0xEDEAF3, dark: 0x1B1A23)
    static let border = color("border", light: 0xD6D2DF, dark: 0x2C2934)
    static let accent = color("accent", light: 0x7050A6, dark: 0xBC9AFF)
    static let text = color("text", light: 0x272330, dark: 0xEEEEF5)
    static let secondaryText = color("secondaryText", light: 0x70687C, dark: 0xA5A1B4)
    static let before = color("before", light: 0xA36C25, dark: 0xEFBF7E)
    static let after = color("after", light: 0x356AAB, dark: 0x8CB9FF)

    static func style(_ button: NSButton) {
        button.bezelStyle = .texturedRounded
        button.controlSize = .small
        button.font = .systemFont(ofSize: 11, weight: .medium)
        button.bezelColor = raised
        button.contentTintColor = text
    }

    static func configure(_ panel: NSPanel) {
        panel.backgroundColor = background
        panel.titlebarAppearsTransparent = true
        panel.hasShadow = true
    }

    private static func color(_ name: String, light: UInt32, dark: UInt32) -> NSColor {
        NSColor(name: NSColor.Name("Vorssaint.Tool." + name)) { appearance in
            let value = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 255) / 255,
                           green: CGFloat((value >> 8) & 255) / 255,
                           blue: CGFloat(value & 255) / 255, alpha: 1)
        }
    }
}
