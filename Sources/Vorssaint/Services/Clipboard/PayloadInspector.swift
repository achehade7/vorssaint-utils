// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// A bounded, local inspection model. JSON spelling and order are kept; XML
/// exposes decoded attributes and text without loading DTDs or external entities.
enum PayloadInspector {
    static let maxBytes = 1_048_576
    static let maxNodes = 10_000
    static let maxDepth = 64

    enum Kind: String, Sendable { case object, array, string, number, boolean, null, element, attribute, text }
    struct Node: Sendable {
        let id: Int
        let name: String
        let path: String
        let kind: Kind
        let value: String?
        let children: [Node]

        var isEmbeddedJSON: Bool {
            guard kind == .string, let first = value?.first(where: { !$0.isWhitespace }) else { return false }
            return first == "{" || first == "["
        }

        func matching(_ query: String) -> Node? {
            guard !query.isEmpty else { return self }
            if name.localizedCaseInsensitiveContains(query) || path.localizedCaseInsensitiveContains(query)
                || (kind != .object && kind != .array && value?.localizedCaseInsensitiveContains(query) == true) { return self }
            let found = children.compactMap { $0.matching(query) }
            return found.isEmpty ? nil : .init(id: id, name: name, path: path, kind: kind, value: value, children: found)
        }
    }
    struct Document: Sendable {
        let format: String
        let root: Node
        let nodeCount: Int
    }
    enum Failure: Error, Equatable {
        case empty, tooLarge, tooComplex, invalidJSON(Int), invalidXML(Int), unsupportedXML
    }

    static func parse(_ source: String) throws -> Document {
        try Task.checkCancellation()
        guard source.utf8.count <= maxBytes else { throw Failure.tooLarge }
        guard let first = source.first(where: { !$0.isWhitespace }) else { throw Failure.empty }
        if first == "<" { return try XMLReader.parse(source) }
        var reader = JSONReader(bytes: Array(source.utf8))
        let root = try reader.node(name: "$", path: "$", depth: 0)
        reader.blanks()
        guard reader.position == reader.bytes.count else { throw Failure.invalidJSON(reader.position + 1) }
        return Document(format: "JSON", root: root, nodeCount: reader.count)
    }

    static func formatted(_ source: String) throws -> String {
        let document = try parse(source)
        let result: String
        if document.format == "JSON" {
            guard let layout = ClipboardJSONFormat.layoutValidated(source, maxOutputBytes: maxBytes) else {
                throw Failure.tooLarge
            }
            result = layout
        } else {
            result = try formatXML(source)
        }
        // Formatting must still fit the inspector's size/complexity limits.
        _ = try parse(result)
        return result
    }

    private static func formatXML(_ source: String) throws -> String {
        // Tokenize only after XMLReader validates the complete input. Keep raw
        // tags, attribute quoting, entities, comments and CDATA intact.
        let pattern = #"<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<\?[\s\S]*?\?>|<(?:[^>"']|"[^"]*"|'[^']*')*>|[^<]+"#
        let regex = try NSRegularExpression(pattern: pattern)
        let input = source as NSString
        let tokens = regex.matches(in: source, range: NSRange(location: 0, length: input.length))
            .map { input.substring(with: $0.range) }
        let blanks = CharacterSet(charactersIn: " \t\r\n")
        func isBlank(_ text: String) -> Bool { text.unicodeScalars.allSatisfy(blanks.contains) }
        var stack: [Int] = [], ends: [Int: Int] = [:]
        var verbatim: Set<Int> = [], hasChildren: Set<Int> = []
        for (index, token) in tokens.enumerated() {
            try Task.checkCancellation()
            if token.hasPrefix("</") {
                if let start = stack.popLast() { ends[start] = index }
            } else if token.hasPrefix("<![CDATA[") || !token.hasPrefix("<") {
                if let parent = stack.last, !isBlank(token) { verbatim.insert(parent) }
            } else if token.hasPrefix("<!--") || token.hasPrefix("<?") {
                if let parent = stack.last { hasChildren.insert(parent) }
            } else {
                if let parent = stack.last { hasChildren.insert(parent) }
                // Conservatively preserve the entire subtree for any xml:space
                // declaration, including escaped attribute values.
                if token.range(of: #"\sxml:space\s*="#, options: .regularExpression) != nil {
                    verbatim.insert(index)
                }
                if !token.hasSuffix("/>") { stack.append(index) }
            }
        }
        var output = ""
        var size = 0
        func append(_ text: String) throws {
            size += text.utf8.count
            guard size <= maxBytes else { throw Failure.tooLarge }
            output += text
        }
        func render(_ index: Int, depth: Int) throws -> Int {
            try Task.checkCancellation()
            guard let end = ends[index] else { try append(tokens[index]); return index + 1 }
            if verbatim.contains(index) || !hasChildren.contains(index) {
                for token in tokens[index...end] { try append(token) }
            } else {
                try append(tokens[index])
                var child = index + 1
                while child < end {
                    if isBlank(tokens[child]) { child += 1; continue }
                    try append("\n" + String(repeating: "  ", count: depth + 1))
                    child = try render(child, depth: depth + 1)
                }
                try append("\n" + String(repeating: "  ", count: depth) + tokens[end])
            }
            return end + 1
        }
        var index = 0
        while index < tokens.count {
            if isBlank(tokens[index]) { index += 1; continue }
            if !output.isEmpty { try append("\n") }
            index = try render(index, depth: 0)
        }
        return output
    }

    private struct JSONReader {
        let bytes: [UInt8]
        var position = 0
        var count = 0
        var current: UInt8? { position < bytes.count ? bytes[position] : nil }
        mutating func blanks() {
            while let byte = current, byte == 32 || byte == 9 || byte == 10 || byte == 13 { position += 1 }
        }
        mutating func consume(_ byte: UInt8) -> Bool {
            guard current == byte else { return false }
            position += 1
            return true
        }
        func invalid() -> Failure { .invalidJSON(position + 1) }
        mutating func string() throws -> (decoded: String, raw: String) {
            let start = position
            guard consume(34) else { throw invalid() }
            while let byte = current {
                if position % 4096 == 0 { try Task.checkCancellation() }
                position += 1
                if byte == 34 {
                    let raw = String(decoding: bytes[start..<position], as: UTF8.self)
                    guard let decoded = try? JSONDecoder().decode(String.self, from: Data(raw.utf8)) else { throw invalid() }
                    return (decoded, raw)
                }
                if byte == 92 {
                    guard current != nil else { throw invalid() }
                    position += 1
                } else if byte < 32 { throw invalid() }
            }
            throw invalid()
        }
        mutating func node(name: String, path: String, depth: Int) throws -> Node {
            try Task.checkCancellation()
            guard depth <= maxDepth, count < maxNodes, path.utf8.count <= 8_192 else { throw Failure.tooComplex }
            count += 1
            let id = count
            blanks()
            let start = position
            var children: [Node] = []
            let kind: Kind
            var value: String?
            switch current {
            case 123, 91:
                let object = current == 123
                kind = object ? .object : .array
                position += 1
                blanks()
                let close: UInt8 = object ? 125 : 93
                if !consume(close) {
                    repeat {
                        blanks()
                        let childName: String, childPath: String
                        if object {
                            let key = try string()
                            childName = key.decoded; childPath = path + "[" + key.raw + "]"
                            blanks()
                            guard consume(58) else { throw invalid() }
                        } else {
                            childName = "[\(children.count)]"; childPath = path + childName
                        }
                        children.append(try node(name: childName, path: childPath, depth: depth + 1))
                        blanks()
                        if consume(close) { break }
                        guard consume(44) else { throw invalid() }
                    } while true
                }
                value = String(decoding: bytes[start..<position], as: UTF8.self)
            case 34:
                kind = .string
                value = try string().decoded
            case 116, 102, 110:
                let literal = current == 116 ? "true" : current == 102 ? "false" : "null"
                for byte in literal.utf8 { guard consume(byte) else { throw invalid() } }
                kind = literal == "null" ? .null : .boolean
                value = literal
            default:
                kind = .number
                _ = consume(45)
                if !consume(48) {
                    guard let digit = current, (49...57).contains(digit) else { throw invalid() }
                    position += 1
                    while let digit = current, (48...57).contains(digit) { position += 1 }
                }
                if consume(46) {
                    let first = position
                    while let digit = current, (48...57).contains(digit) { position += 1 }
                    guard first != position else { throw invalid() }
                }
                if consume(101) || consume(69) {
                    if !consume(43) { _ = consume(45) }
                    let first = position
                    while let digit = current, (48...57).contains(digit) { position += 1 }
                    guard first != position else { throw invalid() }
                }
                value = String(decoding: bytes[start..<position], as: UTF8.self)
            }
            return Node(id: id, name: name, path: path, kind: kind, value: value, children: children)
        }
    }

    private final class XMLReader: NSObject, XMLParserDelegate {
        final class Element {
            let id: Int, name: String, path: String
            var children: [Node] = []
            var occurrences: [String: Int] = [:]
            var textBoundary = false
            init(id: Int, name: String, path: String) { self.id = id; self.name = name; self.path = path }
            var node: Node { Node(id: id, name: name, path: path, kind: .element,
                                 value: children.allSatisfy { $0.kind == .text || $0.kind == .attribute }
                                    ? children.filter { $0.kind == .text }.compactMap(\.value).joined() : nil,
                                 children: children) }
        }
        var stack: [Element] = []
        var root: Node?
        var count = 0
        var failure: Error?

        static func parse(_ source: String) throws -> Document {
            // DTDs are unnecessary for payload inspection. Reject declarations
            // before parsing, including internal entity expansion and file URLs.
            guard source.range(of: "<!DOCTYPE", options: .caseInsensitive) == nil,
                  source.range(of: "<!ENTITY", options: .caseInsensitive) == nil else { throw Failure.unsupportedXML }
            let reader = XMLReader()
            let parser = XMLParser(data: Data(source.utf8))
            parser.shouldResolveExternalEntities = false
            parser.delegate = reader
            let valid = parser.parse()
            if let failure = reader.failure { throw failure }
            guard valid, let root = reader.root else { throw Failure.invalidXML(parser.lineNumber) }
            return Document(format: "XML", root: root, nodeCount: reader.count)
        }
        func nextID(_ parser: XMLParser) -> Int? {
            if Task.isCancelled { failure = CancellationError(); parser.abortParsing(); return nil }
            guard count < maxNodes, stack.count <= maxDepth else {
                failure = Failure.tooComplex; parser.abortParsing(); return nil
            }
            count += 1
            return count
        }
        func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?,
                    qualifiedName: String?, attributes: [String: String]) {
            guard let id = nextID(parser) else { return }
            let parent = stack.last
            let occurrence = (parent?.occurrences[name] ?? 0) + 1
            parent?.occurrences[name] = occurrence
            let element = Element(id: id, name: name, path: (parent?.path ?? "") + "/\(name)[\(occurrence)]")
            guard element.path.utf8.count <= 8_192 else { failure = Failure.tooComplex; parser.abortParsing(); return }
            stack.append(element)
            for (name, value) in attributes.sorted(by: { $0.key < $1.key }) {
                guard let id = nextID(parser) else { return }
                element.children.append(Node(id: id, name: "@" + name, path: element.path + "/@" + name,
                                             kind: .attribute, value: value, children: []))
            }
        }
        func parser(_ parser: XMLParser, foundCharacters string: String) { text(string, parser: parser) }
        func parser(_ parser: XMLParser, foundComment comment: String) { stack.last?.textBoundary = true }
        func parser(_ parser: XMLParser, foundProcessingInstructionWithTarget: String, data: String?) { stack.last?.textBoundary = true }
        func parser(_ parser: XMLParser, foundCDATA data: Data) {
            guard let value = String(data: data, encoding: .utf8) else { failure = Failure.invalidXML(parser.lineNumber); parser.abortParsing(); return }
            text(value, parser: parser)
        }
        func text(_ value: String, parser: XMLParser) {
            guard let element = stack.last, !value.isEmpty else { return }
            if let previous = element.children.last, previous.kind == .text, !element.textBoundary {
                element.children[element.children.count - 1] = Node(id: previous.id, name: previous.name, path: previous.path,
                                                                    kind: .text, value: (previous.value ?? "") + value, children: [])
            } else {
                guard let id = nextID(parser) else { return }
                let number = element.children.filter { $0.kind == .text }.count + 1
                element.children.append(Node(id: id, name: "text()[\(number)]", path: element.path + "/text()[\(number)]",
                                             kind: .text, value: value, children: []))
            }
            element.textBoundary = false
        }
        func parser(_ parser: XMLParser, didEndElement: String, namespaceURI: String?, qualifiedName: String?) {
            guard let element = stack.popLast() else { return }
            if let parent = stack.last { parent.children.append(element.node) } else { root = element.node }
        }
        func parser(_ parser: XMLParser, resolveExternalEntityName: String, systemID: String?) -> Data? { nil }
    }
}
