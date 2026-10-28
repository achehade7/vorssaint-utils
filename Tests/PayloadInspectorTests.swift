// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum PayloadInspectorTests {
    static func run(_ suite: TestSuite) {
        func parse(_ text: String) -> PayloadInspector.Document { try! PayloadInspector.parse(text) }
        func failure(_ text: String) -> PayloadInspector.Failure? {
            do { _ = try PayloadInspector.parse(text); return nil }
            catch { return error as? PayloadInspector.Failure }
        }
        let json = #"{"orders":[{"id":900719925474099312345,"amount":1.2300e+4,"status":"approved","paid":false,"reference":null}],"duplicate":1,"duplicate":2,"escaped":"line\n\u00e9 👩🏽‍💻","a.b[0]":"value"}"#
        let document = parse(json), root = document.root
        suite.expect(document.format == "JSON" && root.value == json, "container copy preserves exact JSON source")
        suite.expect(root.children.map(\.name) == ["orders", "duplicate", "duplicate", "escaped", "a.b[0]"], "JSON order and duplicate keys are preserved")
        let order = root.children[0].children[0]
        suite.expect(order.children[0].value == "900719925474099312345", "large numbers retain every digit")
        suite.expect(order.children[1].value == "1.2300e+4", "numeric spelling is not normalized")
        suite.expect(order.children[2].value == "approved" && order.children[2].kind == .string, "string value excludes JSON quotes")
        suite.expect(order.children[3].value == "false" && order.children[3].kind == .boolean, "boolean remains typed")
        suite.expect(order.children[4].value == "null" && order.children[4].kind == .null, "null remains typed")
        suite.expect(root.children[3].value == "line\né 👩🏽‍💻", "escaped text decodes without harming Unicode")
        suite.expect(root.children[4].path == #"$["a.b[0]"]"#, "JSONPath quotes keys containing punctuation")
        suite.expect(order.children[2].path == #"$["orders"][0]["status"]"#, "JSONPath addresses nested array fields")
        let filtered = root.matching("approved")!
        suite.expect(filtered.children.count == 1 && filtered.children[0].children[0].children.count == 1, "search retains only matching fields and ancestors")
        suite.expect(root.matching("unknown field") == nil, "unmatched search yields empty state")
        suite.expect(root.matching("STATUS")?.children.first?.children.first?.children.first?.name == "status", "field search is case insensitive")
        suite.expect(root.matching("")?.children.count == 5, "clearing search restores all fields")
        let escaped = parse(#"{"body":"{\"status\":\"ok\"}"}"#).root.children[0]
        suite.expect(escaped.isEmbeddedJSON && parse(escaped.value!).root.children[0].value == "ok", "escaped JSON can be inspected explicitly")
        suite.expect(!parse(#""normal text""#).root.isEmbeddedJSON, "ordinary strings do not offer embedded JSON")
        for scalar in ["true", "false", "null", "-0", "1e400", "-1.23E-999", "0.0", "[]", "{}", "\"\""] {
            suite.expect((try? PayloadInspector.parse(scalar)) != nil, "valid scalar/container parses: \(scalar)")
        }
        for invalid in ["{", "[1,]", "{\"a\":1,}", "01", "1.", "+1", "--1", "1e", "true false", "nullx", "NaN", "[1 2]", "{1:2}", "{\"x\" 2}", #""\x""#, #""\uD800""#, "\"literal\nnewline\""] {
            suite.expect(failure(invalid) != nil, "invalid JSON is rejected without partial tree: \(invalid)")
        }
        suite.expect(failure("") == .empty && failure("\r\n\t ") == .empty, "empty and whitespace-only input use the empty state")
        suite.expect(failure(String(repeating: "x", count: PayloadInspector.maxBytes + 1)) == .tooLarge, "input size is bounded before parsing")
        suite.expect(failure(String(repeating: "[", count: 66) + "0" + String(repeating: "]", count: 66)) == .tooComplex, "JSON nesting is bounded")
        suite.expect(failure("[" + Array(repeating: "0", count: 10_000).joined(separator: ",") + "]") == .tooComplex, "JSON node count is bounded")
        suite.expect(failure("{\"" + String(repeating: "k", count: 8_193) + "\":1}") == .tooComplex, "long paths do not amplify memory use")

        let xml = parse(#"<orders xmlns:p="urn:pay"><p:order id="17">approved &amp; paid</p:order><p:order id="18"><![CDATA[<raw>]]></p:order></orders>"#)
        suite.expect(xml.format == "XML" && xml.root.name == "orders", "XML root is a native tree")
        suite.expect(xml.root.children[0].name == "@xmlns:p", "namespace declarations remain visible")
        let first = xml.root.children[1], second = xml.root.children[2]
        suite.expect(first.path == "/orders[1]/p:order[1]" && second.path == "/orders[1]/p:order[2]", "XML paths retain prefixes and sibling occurrences")
        suite.expect(first.children[0].path == "/orders[1]/p:order[1]/@id" && first.children[0].value == "17", "XML attributes have copyable values and paths")
        suite.expect(first.value == "approved & paid" && first.children[1].value == "approved & paid", "XML values decode standard entities")
        suite.expect(second.children[1].value == "<raw>", "CDATA remains text")
        let mixed = parse("<p> before <b>bold</b> after </p>").root
        suite.expect(mixed.value == nil && mixed.children.map(\.kind) == [.text, .element, .text], "mixed content preserves the text/element order")
        suite.expect(mixed.children[0].value == " before " && mixed.children[2].value == " after ", "XML text whitespace is retained")
        suite.expect(mixed.children[2].path == "/p[1]/text()[2]", "multiple XML text nodes are addressable")
        let commented = parse("<p>one<!-- note -->two<?process value?>three<b/>four</p>").root
        suite.expect(commented.children.filter { $0.kind == .text }.map(\.value) == ["one", "two", "three", "four"],
                     "comments and processing instructions separate XPath text nodes")
        suite.expect(commented.children.last?.path == "/p[1]/text()[4]", "XPath text indices include comment-separated nodes")
        suite.expect(xml.root.matching("18")?.children.last?.children.first?.value == "18", "XML attribute values are searchable")
        suite.expect(failure("<a><b></a>") != nil, "malformed XML is rejected")
        suite.expect(failure("<!DOCTYPE a [<!ENTITY x SYSTEM \"file:///etc/passwd\">]><a>&x;</a>") == .unsupportedXML, "external file entities are rejected before parsing")
        suite.expect(failure("<!DOCTYPE a SYSTEM \"https://example.invalid/data\"><a/>") == .unsupportedXML, "external network DTDs are rejected before parsing")
        suite.expect(failure("<!DOCTYPE a [<!ENTITY x \"expanded\">]><a>&x;</a>") == .unsupportedXML, "internal entity expansion is rejected before parsing")
        suite.expect(failure(String(repeating: "<a>", count: 66) + String(repeating: "</a>", count: 66)) == .tooComplex, "XML nesting is bounded during parsing")
        suite.expect(failure("<a>" + String(repeating: "<b/>", count: 10_000) + "</a>") == .tooComplex, "XML node count is bounded during parsing")
        let precise = #"{"n":900719925474099312345,"n":1.2300e+4,"s":"\u00e9\/","empty":[]}"#
        let pretty = try! PayloadInspector.formatted(precise)
        suite.expect(pretty == "{\n  \"n\": 900719925474099312345,\n  \"n\": 1.2300e+4,\n  \"s\": \"\\u00e9\\/\",\n  \"empty\": []\n}",
                     "JSON formatting changes only whitespace, preserving duplicate keys, escapes and numbers")
        suite.expect(try! PayloadInspector.formatted(pretty) == pretty, "JSON formatting is idempotent")
        for scalar in ["1e400", "-0", "false", "null", #""line\nquote\"""#] {
            suite.expect(try! PayloadInspector.formatted(" \n" + scalar + "\t") == scalar, "scalar JSON formats without re-encoding")
        }
        let beyondClipboardLimit = #"{"s":""# + String(repeating: "x", count: 300_000) + #""}"#
        suite.expect((try? PayloadInspector.formatted(beyondClipboardLimit)) != nil, "inspector formatting supports its own 1 MB input limit")
        let xmlSource = #"<?xml version='1.0'?><r xmlns:p='urn:test'><!-- note > --><p:a x='a&#10;b &gt; c'> A &amp; B </p:a><b/><p>one<i/>two</p><raw><![CDATA[ <literal> ]]></raw><keep xml:space='pre&#115;erve'><a/><b/></keep></r>"#
        let xmlFormatted = try! PayloadInspector.formatted(xmlSource)
        suite.expect(xmlFormatted == "<?xml version='1.0'?>\n<r xmlns:p='urn:test'>\n  <!-- note > -->\n  <p:a x='a&#10;b &gt; c'> A &amp; B </p:a>\n  <b/>\n  <p>one<i/>two</p>\n  <raw><![CDATA[ <literal> ]]></raw>\n  <keep xml:space='pre&#115;erve'><a/><b/></keep>\n</r>",
                     "XML formatting preserves raw attributes, entities, namespaces, comments, mixed text, CDATA and xml:space")
        suite.expect(try! PayloadInspector.formatted(xmlFormatted) == xmlFormatted, "XML formatting is idempotent")
        for preserved in ["<p>  </p>", "<p>before<b/> after</p>", "<r xml:space='preserve'><a/><b/></r>",
                          "<p>\u{00a0}<b/></p>", "<p><![CDATA[]]><b/></p>"] {
            suite.expect(try! PayloadInspector.formatted(preserved) == preserved, "significant XML whitespace and mixed content remain exact")
        }
        for invalid in ["", "{", "[1,]", "<r><a></r>", "<!DOCTYPE a SYSTEM 'file:///nope'><a/>"] {
            suite.expect((try? PayloadInspector.formatted(invalid)) == nil, "invalid or unsupported source is never repaired or partially formatted")
        }
        let nearLimit = #"{"s":""# + String(repeating: "x", count: PayloadInspector.maxBytes - 8) + #""}"#
        suite.expect((try? PayloadInspector.parse(nearLimit)) != nil && (try? PayloadInspector.formatted(nearLimit)) == nil,
                     "output exceeding the inspector limit is refused without truncation")
        for language in AppLanguage.allCases {
            let strings = PayloadInspectorStrings.localized(language)
            suite.expect(!strings.title.isEmpty && !strings.search.isEmpty && !strings.copyValue.isEmpty && !strings.copyPath.isEmpty && !strings.formatSource.isEmpty,
                         "payload controls exist in every locale")
            suite.expect(!strings.message(PayloadInspector.Failure.invalidJSON(7)).contains("%d"), "error byte formats in every locale")
        }
    }
}
