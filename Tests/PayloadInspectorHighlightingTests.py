#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Check detail-only token colors and exact payload preservation without opening UI."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit

var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    precondition(condition, message)
}
let font = NSFont.monospacedSystemFont(ofSize: 15, weight: .regular)
func color(_ value: NSAttributedString, at index: Int) -> NSColor {
    value.attribute(.foregroundColor, at: index, effectiveRange: nil) as! NSColor
}
func resolved(_ color: NSColor) -> NSColor { color.usingColorSpace(.sRGB)! }
func matches(_ left: NSColor, _ right: NSColor) -> Bool {
    let a = resolved(left), b = resolved(right)
    return abs(a.redComponent - b.redComponent) < 0.001
        && abs(a.greenComponent - b.greenComponent) < 0.001
        && abs(a.blueComponent - b.blueComponent) < 0.001
}
func token(_ token: String, in value: NSAttributedString, is expected: NSColor) {
    let range = (value.string as NSString).range(of: token)
    expect(range.location != NSNotFound, "fixture token exists: \(token)")
    for offset in range.location..<NSMaxRange(range) {
        expect(matches(color(value, at: offset), expected), "token keeps one semantic color: \(token)")
    }
}
func uniform(_ text: String, kind: PayloadInspector.Kind) {
    let value = PayloadInspectorHighlighting.attributed(text, kind: kind, font: font)
    expect(value.string.utf8.elementsEqual(text.utf8), "scalar value bytes stay exact")
    for offset in 0..<value.length {
        expect(matches(color(value, at: offset), PayloadInspectorHighlighting.valueColor(for: kind)),
               "decoded scalar is not reinterpreted as syntax")
        expect(value.attribute(.font, at: offset, effectiveRange: nil) as? NSFont == font,
               "caller font is preserved")
    }
}

let json = "\r\n\t" + #"{"escaped\"key":"slash\\ and quote\" and colon:","emoji 👩🏽‍💻":"cafe\u0301","n":9007199254740993123456789,"exponent":-12.3400E+008,"enabled":true,"disabled":false,"missing":null,"values":["looks: like a key",42]}"# + "\n"
let parsed = try PayloadInspector.parse(json)
expect(parsed.root.kind == .object, "JSON fixture is valid")
for appearance in [NSAppearance.Name.aqua, .darkAqua] {
    NSAppearance(named: appearance)!.performAsCurrentDrawingAppearance {
        let value = PayloadInspectorHighlighting.attributed(json, kind: .object, font: font)
        expect(value.string.utf8.elementsEqual(json.utf8), "JSON spelling, CRLF, tabs and Unicode remain exact")
        token(#""escaped\"key""#, in: value, is: PayloadInspectorHighlighting.propertyColor)
        token(#""emoji 👩🏽‍💻""#, in: value, is: PayloadInspectorHighlighting.propertyColor)
        token(#""slash\\ and quote\" and colon:""#, in: value, is: PayloadInspectorHighlighting.valueColor(for: .string))
        token(#""cafe\u0301""#, in: value, is: PayloadInspectorHighlighting.valueColor(for: .string))
        token(#""looks: like a key""#, in: value, is: PayloadInspectorHighlighting.valueColor(for: .string))
        token("9007199254740993123456789", in: value, is: PayloadInspectorHighlighting.valueColor(for: .number))
        token("-12.3400E+008", in: value, is: PayloadInspectorHighlighting.valueColor(for: .number))
        token("true", in: value, is: PayloadInspectorHighlighting.valueColor(for: .boolean))
        token("false", in: value, is: PayloadInspectorHighlighting.valueColor(for: .boolean))
        token("null", in: value, is: PayloadInspectorHighlighting.valueColor(for: .null))
        token("{", in: value, is: ToolAppearance.secondaryText)
        let palette = [PayloadInspectorHighlighting.propertyColor] + [.string, .number, .boolean, .null].map {
            PayloadInspectorHighlighting.valueColor(for: $0)
        }
        for first in palette.indices {
            for second in palette.indices where first < second {
                expect(!matches(palette[first], palette[second]), "keys and value types are distinguishable in both appearances")
            }
        }
        uniform(#"{"looks":"JSON","number":123}"#, kind: .string)
        uniform("<tag attribute=\"value\"> & text 👩🏽‍💻\r\n", kind: .text)
        uniform("<not-a-tag> & café", kind: .attribute)
        uniform("decoded < and > text", kind: .element)
        uniform("-0.000000001e+100", kind: .number)
        uniform("false", kind: .boolean)
        uniform("null", kind: .null)
        uniform("", kind: .string)
        let array = #"["x:y",{"property":"value"},false,-1.20e-3]"#
        let arrayValue = PayloadInspectorHighlighting.attributed(array, kind: .array, font: font)
        expect(arrayValue.string == array, "array spelling stays exact")
        token(#""property""#, in: arrayValue, is: PayloadInspectorHighlighting.propertyColor)
        token(#""value""#, in: arrayValue, is: PayloadInspectorHighlighting.valueColor(for: .string))
        token("-1.20e-3", in: arrayValue, is: PayloadInspectorHighlighting.valueColor(for: .number))
    }
}
let xml = try PayloadInspector.parse(#"<root code="&lt;tag&gt;"><text>&lt;b&gt;Hi&lt;/b&gt;</text><mixed><![CDATA[{"not":"syntax"}]]></mixed></root>"#)
let xmlAttribute = xml.root.children.first { $0.kind == .attribute }!
let xmlText = xml.root.children.first { $0.name == "text" }!
let xmlCDATA = xml.root.children.first { $0.name == "mixed" }!
uniform(xmlAttribute.value!, kind: xmlAttribute.kind)
uniform(xmlText.value!, kind: xmlText.kind)
uniform(xmlCDATA.value!, kind: xmlCDATA.kind)

// A future caller passing incomplete input still gets exact text and finite scanning.
for text in [#"{"unfinished\""#, "[1e+", "{\"a\":truth}", ""] {
    let value = PayloadInspectorHighlighting.attributed(text, kind: .object, font: font)
    expect(value.string == text, "incomplete text cannot be changed or crash the color scanner")
}
print("PASS: \(checks) payload detail highlighting checks")
'''

with tempfile.TemporaryDirectory(prefix="payload-highlighting-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    executable = folder / "check"
    sources = [
        "Sources/Vorssaint/Services/Clipboard/PayloadInspector.swift",
        "Sources/Vorssaint/Services/Clipboard/PayloadInspectorHighlighting.swift",
        "Sources/Vorssaint/UI/ToolAppearance.swift",
    ]
    subprocess.run(["swiftc", *[str(repo / path) for path in sources], str(main), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=30)
