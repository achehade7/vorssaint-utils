// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import Combine
import UniformTypeIdentifiers

enum ClipboardFileDiff {
    enum Side: String, CaseIterable { case before, after }
    struct Input: Sendable {
        let name: String
        let text: String
    }
    enum Failure: Error { case unsupported, tooLarge, unreadable }

    /// Only metadata is inspected during a drag. Actual reads happen after drop.
    static func accepts(_ urls: [URL]) -> Bool {
        guard (1...2).contains(urls.count) else { return false }
        let extensions: Set<String> = ["", "txt", "text", "json", "xml", "yaml", "yml", "toml", "ini", "cfg", "conf", "config", "properties", "env", "log", "csv", "tsv", "md", "markdown", "swift", "js", "ts", "tsx", "jsx", "css", "scss", "html", "htm", "sh", "zsh", "bash", "py", "rb", "java", "groovy", "sql", "cds", "abap", "iflw", "xsd", "xslt", "xsl", "wsdl", "http", "gitignore"]
        return urls.allSatisfy { url in
            guard url.isFileURL, !url.hasDirectoryPath else { return false }
            let ext = url.pathExtension.lowercased()
            return extensions.contains(ext) || UTType(filenameExtension: ext)?.conforms(to: .text) == true
        }
    }

    static func read(_ url: URL) throws -> Input {
        try Task.checkCancellation()
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        guard let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
              values.isRegularFile == true else { throw Failure.unreadable }
        guard (values.fileSize ?? 0) <= ClipboardDiff.maxBytes else { throw Failure.tooLarge }
        let handle: FileHandle
        do { handle = try FileHandle(forReadingFrom: url) } catch { throw Failure.unreadable }
        defer { try? handle.close() }
        var data = Data()
        do {
            while data.count <= ClipboardDiff.maxBytes {
                try Task.checkCancellation()
                guard let chunk = try handle.read(upToCount: min(65_536, ClipboardDiff.maxBytes + 1 - data.count)),
                      !chunk.isEmpty else { break }
                data.append(chunk)
            }
        } catch is CancellationError { throw CancellationError() }
        catch { throw Failure.unreadable }
        try Task.checkCancellation()
        guard data.count <= ClipboardDiff.maxBytes else { throw Failure.tooLarge }
        guard !data.contains(0), String(data: data, encoding: .utf8) != nil else { throw Failure.unsupported }
        // Foundation's encoding initializer consumes a leading BOM. Validation
        // and decoding are separate so every valid UTF-8 byte stays represented.
        let text = String(decoding: data, as: UTF8.self)
        guard data.reduce(1, { $0 + ($1 == 10 ? 1 : 0) }) <= ClipboardDiff.maxLines else { throw Failure.tooLarge }
        return Input(name: url.lastPathComponent, text: text)
    }
}

final class ClipboardFileDiffService: ObservableObject {
    static let shared = ClipboardFileDiffService()
    @Published private(set) var inputs: [ClipboardFileDiff.Side: ClipboardFileDiff.Input] = [:]
    @Published private(set) var loading: Set<ClipboardFileDiff.Side> = []
    @Published private(set) var error: String?
    private var tasks: [ClipboardFileDiff.Side: Task<Void, Never>] = [:]
    private var revisions: [ClipboardFileDiff.Side: UUID] = [:]
    private var presentationID = UUID()
    var hasDraft: Bool { !inputs.isEmpty || !loading.isEmpty || error != nil }

    func files(from pasteboard: NSPasteboard) -> [URL]? {
        guard AppFeature.clipboardHistory.isAvailable,
              !pasteboard.canReadObject(forClasses: [NSFilePromiseReceiver.self], options: nil),
              let urls = pasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL],
              urls.count >= (pasteboard.pasteboardItems?.count ?? 0), ClipboardFileDiff.accepts(urls) else { return nil }
        return urls
    }

    @discardableResult
    func accept(_ pasteboard: NSPasteboard, side: ClipboardFileDiff.Side) -> Bool {
        guard let urls = files(from: pasteboard) else { return false }
        load(urls, side: side)
        return true
    }

    func clear() {
        presentationID = UUID()
        tasks.values.forEach { $0.cancel() }
        tasks = [:]; revisions = [:]; loading = []; inputs = [:]; error = nil
    }

    /// Two files are an atomic pair in pasteboard order. One file replaces only
    /// its explicit target; rapid successive drops on opposite sides can finish independently.
    func load(_ urls: [URL], side: ClipboardFileDiff.Side) {
        guard AppFeature.clipboardHistory.isAvailable, ClipboardFileDiff.accepts(urls) else { return }
        presentationID = UUID()
        let sides: [ClipboardFileDiff.Side] = urls.count == 2 ? [.before, .after] : [side]
        let revision = UUID()
        let replaced = Set(sides.compactMap { revisions[$0] })
        for target in ClipboardFileDiff.Side.allCases where revisions[target].map({ replaced.contains($0) }) == true {
            tasks[target]?.cancel(); tasks[target] = nil; revisions[target] = nil; loading.remove(target)
        }
        for target in sides {
            tasks[target]?.cancel(); revisions[target] = revision; loading.insert(target)
        }
        error = nil
        let work = Task.detached(priority: .userInitiated) { try urls.map(ClipboardFileDiff.read) }
        let task = Task { @MainActor [weak self] in
            let result = await withTaskCancellationHandler(operation: { await work.result }, onCancel: { work.cancel() })
            guard let self, !Task.isCancelled,
                  sides.allSatisfy({ self.revisions[$0] == revision }) else { return }
            for target in sides { self.loading.remove(target); self.tasks[target] = nil }
            guard AppFeature.clipboardHistory.isAvailable else { self.clear(); return }
            switch result {
            case .success(let values):
                for (target, value) in zip(sides, values) { self.inputs[target] = value }
                if self.error == nil, self.loading.isEmpty, let before = self.inputs[.before], let after = self.inputs[.after] {
                    self.clear()
                    let presentationID = self.presentationID
                    NotchService.shared.perform { [weak self] in
                        guard self?.presentationID == presentationID else { return }
                        ClipboardDiffService.shared.show(pair: .init(older: before.text, newer: after.text),
                                                         beforeName: before.name, afterName: after.name)
                    }
                }
            case .failure(let failure):
                let strings = ClipboardFileDiffStrings.localized(L10n.shared.language)
                switch failure {
                case ClipboardFileDiff.Failure.tooLarge: self.error = ClipboardDiffStrings.localized(L10n.shared.language).tooLarge
                case ClipboardFileDiff.Failure.unsupported: self.error = strings.unsupported
                default: self.error = strings.unreadable
                }
            }
        }
        for target in sides { tasks[target] = task }
    }
}
