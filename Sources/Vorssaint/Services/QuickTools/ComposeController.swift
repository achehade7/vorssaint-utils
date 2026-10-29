// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI
import UniformTypeIdentifiers

final class ComposeController: ObservableObject {
    static let shared = ComposeController()
    @Published var items: [ComposeItem] = [] { didSet { refresh() } }
    @Published var title = "" { didSet { refresh() } }
    @Published var paragraph = "" { didSet { refresh() } }
    @Published var layout = ComposeLayout.grid { didSet { refresh() } }
    @Published var columns = 2 { didSet { refresh() } }
    @Published var width = 1440 { didSet { refresh() } }
    @Published private(set) var preview: CGImage?
    @Published private(set) var pending = 0
    @Published private(set) var rendering = false
    @Published var message: String?
    private var panel: ComposePanel?
    private let queue = DispatchQueue(label: "com.vorssaint.compose", qos: .userInitiated)
    private var renderWork: DispatchWorkItem?
    private var revision = 0
    private var importGeneration = 0
    var imageCount: Int { items.filter { $0.image != nil }.count }
    var canExport: Bool { preview != nil && !rendering && pending == 0 }

    func show() {
        guard AppFeature.screenshot.isAvailable else { return }
        if panel == nil {
            let window = ComposePanel(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 700),
                styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
            window.title = "Compose"
            window.isReleasedWhenClosed = false
            window.minSize = NSSize(width: 760, height: 520)
            window.contentView = NSHostingView(rootView: ComposeView(model: self))
            window.owner = self
            window.center()
            panel = window
        }
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func clear() {
        importGeneration += 1; pending = 0
        items = []; title = ""; paragraph = ""; message = nil
    }

    func addText() {
        items.append(ComposeItem(image: nil, name: "Text"))
    }

    func move(_ id: UUID, before target: UUID) {
        guard let from = items.firstIndex(where: { $0.id == id }),
              let to = items.firstIndex(where: { $0.id == target }), from != to else { return }
        var next = items
        let item = next.remove(at: from)
        next.insert(item, at: to)
        items = next
    }

    func chooseFiles() {
        guard let panel, panel.attachedSheet == nil else { return }
        let picker = NSOpenPanel()
        picker.allowedContentTypes = [.image]
        picker.allowsMultipleSelection = true
        picker.canChooseDirectories = false
        picker.beginSheetModal(for: panel) { [weak self] result in
            if result == .OK { self?.addFiles(picker.urls) }
        }
    }

    private func beginImport() -> Int? {
        guard imageCount + pending < ComposeRenderer.imageLimit else {
            message = "Use up to \(ComposeRenderer.imageLimit) images in one composition."
            return nil
        }
        pending += 1; message = nil
        return importGeneration
    }

    private func finishImport(_ result: Result<CGImage, Error>, name: String, generation: Int) {
        guard generation == importGeneration else { return }
        pending -= 1
        switch result {
        case .success(let image):
            let pixels = items.compactMap(\.image).reduce(0) { $0 + $1.width * $1.height }
            guard pixels + image.width * image.height <= 64_000_000 else {
                message = "These images use too much memory. Remove an image or use smaller files."; return
            }
            items.append(ComposeItem(image: image, name: name))
        case .failure(let error): message = "\(name): \(error.localizedDescription)"
        }
    }

    func addFiles(_ urls: [URL]) {
        for url in urls {
            guard let generation = beginImport() else { break }
            queue.async { [weak self] in
                let result = Result { try ComposeRenderer.load(url) }
                DispatchQueue.main.async { self?.finishImport(result, name: url.lastPathComponent, generation: generation) }
            }
        }
    }

    func addRecent(_ entry: RecentCaptureEntry) {
        guard let generation = beginImport() else { return }
        RecentCaptureService.shared.screenshot(for: entry) { [weak self] capture in
            let result: Result<CGImage, Error> = capture.map { .success($0.image) } ?? .failure(ComposeRenderer.Failure.unreadable)
            self?.finishImport(result, name: "Capture " + entry.createdAt.formatted(date: .abbreviated, time: .shortened), generation: generation)
        }
    }

    func paste() {
        let board = NSPasteboard.general
        let urls = board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []
        if !urls.isEmpty { addFiles(urls); return }
        guard let image = NSImage(pasteboard: board), let pixels = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let generation = beginImport() else { message = "Copy an image or image file first."; return }
        finishImport(.success(pixels), name: "Pasted image", generation: generation)
    }

    func acceptDrop(_ providers: [NSItemProvider]) -> Bool {
        let accepted = providers.filter { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier)
            || $0.canLoadObject(ofClass: NSImage.self) }
        for provider in accepted {
            guard let generation = beginImport() else { break }
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { [weak self] item, _ in
                    let url = (item as? URL) ?? (item as? Data).flatMap { URL(dataRepresentation: $0, relativeTo: nil) }
                    guard let self else { return }
                    self.queue.async {
                        let result = Result { guard let url else { throw ComposeRenderer.Failure.unreadable }; return try ComposeRenderer.load(url) }
                        DispatchQueue.main.async { self.finishImport(result, name: url?.lastPathComponent ?? "Dropped image", generation: generation) }
                    }
                }
            } else {
                provider.loadObject(ofClass: NSImage.self) { [weak self] object, _ in
                    DispatchQueue.main.async {
                        let image = (object as? NSImage)?.cgImage(forProposedRect: nil, context: nil, hints: nil)
                        self?.finishImport(image.map { .success($0) } ?? .failure(ComposeRenderer.Failure.unreadable),
                                           name: "Dropped image", generation: generation)
                    }
                }
            }
        }
        return !accepted.isEmpty
    }

    private func refresh() {
        message = nil
        revision += 1
        let current = revision
        renderWork?.cancel(); preview = nil
        rendering = !items.isEmpty
        guard !items.isEmpty else { return }
        let snapshot = ComposeSnapshot(items: items, layout: layout, columns: columns, width: width, title: title, paragraph: paragraph)
        let work = DispatchWorkItem { [weak self] in
            let result = Result { try ComposeRenderer.render(snapshot) }
            DispatchQueue.main.async {
                guard let self, self.revision == current else { return }
                self.rendering = false
                switch result {
                case .success(let image): self.preview = image
                case .failure(let error): self.message = error.localizedDescription
                }
            }
        }
        renderWork = work
        queue.asyncAfter(deadline: .now() + 0.15, execute: work)
    }

    func copy() {
        guard canExport, let preview else { return }
        do {
            let data = try ComposeRenderer.png(preview)
            let item = NSPasteboardItem()
            item.setData(data, forType: .png)
            NSPasteboard.general.clearContents()
            guard NSPasteboard.general.writeObjects([item]) else { message = "Could not copy the image."; return }
            message = "Copied image"
        } catch { message = error.localizedDescription }
    }

    func save() {
        guard canExport, let preview, let panel, panel.attachedSheet == nil else { return }
        let picker = NSSavePanel()
        picker.allowedContentTypes = [.png]
        picker.nameFieldStringValue = "Composition.png"
        picker.beginSheetModal(for: panel) { [weak self] response in
            guard response == .OK, let url = picker.url else { return }
            do { try ComposeRenderer.png(preview).write(to: url, options: .atomic); self?.message = "Saved PNG" }
            catch { self?.message = error.localizedDescription }
        }
    }
}

private final class ComposePanel: NSPanel {
    weak var owner: ComposeController?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if flags == .command {
            switch event.charactersIgnoringModifiers?.lowercased() {
            case "o": owner?.chooseFiles(); return true
            case "s": owner?.save(); return true
            case "w": performClose(nil); return true
            case "v" where !(firstResponder is NSTextView): owner?.paste(); return true
            case "c" where !(firstResponder is NSTextView): owner?.copy(); return true
            default: break
            }
        }
        return super.performKeyEquivalent(with: event)
    }
}

private struct ComposeView: View {
    @ObservedObject var model: ComposeController
    @ObservedObject private var history = RecentCaptureService.shared
    @State private var recent = false
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Button("Add images…") { model.chooseFiles() }
                Button("Paste") { model.paste() }
                Button("Add text") { model.addText() }
                Button("Recent captures") { recent.toggle() }
                    .popover(isPresented: $recent) {
                        ScrollView {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                                ForEach(history.entries.filter { $0.kind == .screenshot }) { entry in
                                    Button { model.addRecent(entry) } label: {
                                        VStack {
                                            if let image = history.thumbnail(for: entry) {
                                                Image(nsImage: image).resizable().scaledToFit().frame(width: 100, height: 70)
                                            } else { Image(systemName: "photo").frame(width: 100, height: 70) }
                                            Text(entry.createdAt, style: .time).font(.caption)
                                        }
                                    }.buttonStyle(.plain).help("Add capture")
                                }
                            }.padding()
                            if history.entries.filter({ $0.kind == .screenshot }).isEmpty { Text("No recent screenshots").padding() }
                        }.frame(width: 380, height: 300)
                    }
                Spacer()
                Text("\(model.imageCount) images").foregroundStyle(.secondary)
                Button("Clear") { model.clear() }.disabled(model.items.isEmpty && model.pending == 0)
            }.padding(16)
            Divider()
            HStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        TextField("Title (optional)", text: $model.title).font(.headline)
                        Text("Intro text (optional)").font(.caption).foregroundStyle(.secondary)
                        TextEditor(text: $model.paragraph).frame(height: 64)
                            .overlay(RoundedRectangle(cornerRadius: 5).stroke(.secondary.opacity(0.2)))
                        Picker("Layout", selection: $model.layout) {
                            ForEach(ComposeLayout.allCases) { Text($0.rawValue).tag($0) }
                        }.pickerStyle(.segmented)
                        if model.layout == .grid { Stepper("\(model.columns) columns", value: $model.columns, in: 2...4) }
                        Picker("Image width", selection: $model.width) {
                            ForEach([720, 1080, 1440, 1920, 2400], id: \.self) { Text("\($0) px").tag($0) }
                        }
                        Text("Drag blocks to reorder").font(.caption).foregroundStyle(.secondary)
                        ForEach($model.items) { $item in
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    if let image = item.image {
                                        Image(decorative: image, scale: 1).resizable().scaledToFit().frame(width: 70, height: 55)
                                    } else { Image(systemName: "text.alignleft").foregroundStyle(.secondary) }
                                    Text(item.name).font(.caption).lineLimit(2)
                                    Spacer()
                                    Button { model.items.removeAll { $0.id == item.id } } label: { Image(systemName: "xmark") }
                                        .buttonStyle(.plain).help("Remove block")
                                }
                                if item.image != nil {
                                    HStack {
                                        Text("Size").font(.caption)
                                        Slider(value: $item.sizePercent, in: 10...100, step: 5)
                                            .accessibilityLabel("Image size")
                                        Text("\(Int(item.sizePercent))%")
                                            .font(.caption.monospacedDigit()).frame(width: 36, alignment: .trailing)
                                    }.help("Size within the layout. Image proportions stay the same.")
                                    TextField("Text below image (optional)", text: $item.caption, axis: .vertical).lineLimit(1...4)
                                } else {
                                    TextField("Steps or explanation…", text: $item.text, axis: .vertical).lineLimit(3...12)
                                }
                            }.padding(10).background(.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                                .onDrag { NSItemProvider(object: item.id.uuidString as NSString) }
                                .onDrop(of: [.plainText], delegate: ComposeReorder(model: model, target: item.id))
                        }
                    }.textFieldStyle(.roundedBorder).padding(16)
                }.frame(width: 290)
                Divider()
                ZStack {
                    Color.primary.opacity(0.025)
                    if let preview = model.preview {
                        Image(decorative: preview, scale: 1).resizable().scaledToFit().padding(24)
                    } else if model.rendering || model.pending > 0 { ProgressView() }
                    else {
                        VStack(spacing: 12) {
                            Image(systemName: "square.grid.2x2").font(.system(size: 36, weight: .light))
                            Text("Drop images here").font(.title3)
                            Text("Add files, paste an image, or pick recent captures.").font(.callout)
                        }.foregroundStyle(.secondary)
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            Divider()
            HStack {
                Text(model.message ?? (model.preview.map { "\($0.width) × \($0.height) px · Local only" } ?? "Local only"))
                    .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Spacer()
                Button("Save PNG…") { model.save() }.disabled(!model.canExport)
                Button("Copy image") { model.copy() }.buttonStyle(.borderedProminent).disabled(!model.canExport)
            }.padding(16)
        }.onDrop(of: [.fileURL, .image], isTargeted: nil) { model.acceptDrop($0) }
    }
}

private struct ComposeReorder: DropDelegate {
    let model: ComposeController
    let target: UUID
    func validateDrop(info: DropInfo) -> Bool {
        !info.hasItemsConforming(to: [.fileURL, .image]) && info.hasItemsConforming(to: [.plainText])
    }
    func dropUpdated(info: DropInfo) -> DropProposal? { DropProposal(operation: .move) }
    func performDrop(info: DropInfo) -> Bool {
        guard let provider = info.itemProviders(for: [.plainText]).first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { item, _ in
            let text = (item as? String) ?? (item as? Data).flatMap { String(data: $0, encoding: .utf8) }
            guard let text, let id = UUID(uuidString: text) else { return }
            DispatchQueue.main.async { model.move(id, before: target) }
        }
        return true
    }
}
