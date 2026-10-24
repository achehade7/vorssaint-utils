#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Text-tool transformations, exact content preservation and invalid-input handling."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import Foundation
enum AppLanguage: CaseIterable { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n { static let shared = Self(); let language = AppLanguage.enUS }
// FORMATTER
var checks = 0
func check(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
func expect(_ kind: TextTransform.Kind, _ source: String, _ expected: String?) {
    let actual = TextTransform.apply(kind, to: source)
    check(actual.map { Array($0.utf8) } == expected.map { Array($0.utf8) }, "\(kind) transforms \(source.debugDescription) exactly")
}
expect(.joinLines, "OCR broke this\nsentence over\nthree lines.", "OCR broke this sentence over three lines.")
expect(.joinLines, "  first\r\n\r\n\tsecond  \rthird\u{2028}fourth  ", "first second third fourth")
expect(.joinLines, "one  space\ntwo", "one  space two")
expect(.joinLines, "already one line", nil)
expect(.joinLines, "word-\nwrap", "word- wrap") // No guessed dehyphenation or content rewriting.
expect(.cleanSpacing, "  one\t \t two  \r\n  three  \r\n\r\n\r\n four \n\n", "one two\nthree\n\nfour")
expect(.cleanSpacing, "first\r\nsecond", "first\nsecond")
expect(.cleanSpacing, "\n\nfirst\n\nsecond\n\n", "first\n\nsecond")
expect(.cleanSpacing, "- one\n- two\n\nparagraph", "- one\n- two\n\nparagraph")
expect(.cleanSpacing, "  café\u{00A0}\u{00A0}👩🏽‍💻  cafe\u{0301}\n日本語  ", "café 👩🏽‍💻 cafe\u{0301}\n日本語")
for whitespace in ["", " ", "\n", "\r\n\t\n"] {
    check(TextTransform.choices(for: whitespace).isEmpty, "whitespace-only input does not offer an empty result")
}
let preciseJSON = #"{"large":9007199254740993123456789,"decimal":-12.3400E+008,"text":"line\nquote\"slash\/","empty":[]}"#
expect(.formatJSON, preciseJSON, "{\n  \"large\": 9007199254740993123456789,\n  \"decimal\": -12.3400E+008,\n  \"text\": \"line\\nquote\\\"slash\\/\",\n  \"empty\": []\n}")
expect(.formatJSON, "not JSON", nil)
expect(.formatJSON, #"{"broken":}"#, nil)
expect(.decodeURL, "Hello%20world%21", "Hello world!")
expect(.decodeURL, "a+b%2Bc", "a+b+c")
expect(.decodeURL, "%2520", "%20")
expect(.decodeURL, "caf%C3%A9%20%F0%9F%91%A9%E2%80%8D%F0%9F%92%BB", "café 👩‍💻")
for invalid in ["100%", "%2", "%GG", "%FF", "%00", "%1B", "ordinary text"] { expect(.decodeURL, invalid, nil) }
expect(.decodeURL, "first%0Asecond", "first\nsecond")
expect(.decodeBase64, "U0FQLTUzMQ==", "SAP-531")
expect(.decodeBase64, "  U0FQ\r\nLTUzMQ==\n", "SAP-531")
let unicode = "café 👩🏽‍💻\nline\ttwo"
expect(.decodeBase64, Data(unicode.utf8).base64EncodedString(), unicode)
for invalid in ["", "hello!", "U0FQLTUzMQ==!", "SGVsbG8", "/w==", "AA==", "Gw=="] {
    expect(.decodeBase64, invalid, nil)
}
let allKinds = TextTransform.choices(for: "  broken  line\n next line ")
check(allKinds.map(\.kind) == [.joinLines, .cleanSpacing], "plain OCR offers only relevant transformations in stable order")
check(allKinds[0].text == "broken  line next line" && allKinds[1].text == "broken line\nnext line",
      "each result starts from the original, never the previously transformed text")
check(TextTransform.choices(for: "Hello%20world").map(\.kind) == [.decodeURL], "URL input offers only decoding")
check(TextTransform.choices(for: "U0FQLTUzMQ==").map(\.kind) == [.decodeBase64], "Base64 input offers only decoding")
check(TextTransform.choices(for: "plain text").isEmpty, "unchanged output is not offered")
let formatted = TextTransform.apply(.formatJSON, to: preciseJSON)!
check(!TextTransform.choices(for: formatted).contains { $0.kind == .formatJSON }, "already formatted JSON does not offer a no-op")
let large = String(repeating: "x", count: TextTransform.maxBytes + 1)
check(TextTransform.choices(for: large).isEmpty, "oversized input offers no work")
for kind in TextTransform.Kind.allCases { expect(kind, large, nil) }
let boundary = String(repeating: "x", count: TextTransform.maxBytes - 2) + "\nx"
check(TextTransform.apply(.joinLines, to: boundary)?.utf8.count == TextTransform.maxBytes, "byte limit includes exact boundary")
for language in AppLanguage.allCases {
    let strings = TextTransformStrings.localized(language)
    check(strings.count == 9 && strings.allSatisfy { !$0.isEmpty }, "all text-tool UI strings exist for \(language)")
    check(Set(strings[1...6]).count == 6, "edit and transformation titles are distinct in \(language)")
}
print("PASS: \(checks) text transformation checks")
'''
fixture = fixture.replace('// FORMATTER', declaration(
    'Sources/Vorssaint/Services/Clipboard/ClipboardHistorySupport.swift', 'enum ClipboardJSONFormat'))
with tempfile.TemporaryDirectory(prefix='text-transform-') as temporary:
    folder = Path(temporary)
    source = folder / 'main.swift'
    source.write_text(fixture)
    binary = folder / 'check'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Services/QuickTools/TextTransform.swift'),
                    str(repo / 'Sources/Vorssaint/Core/TextTransformStrings.swift'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
