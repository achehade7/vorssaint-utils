// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

final class PayloadInspectorService: NSObject, NSWindowDelegate, NSTextViewDelegate, NSSearchFieldDelegate,
                                     NSOutlineViewDataSource, NSOutlineViewDelegate {
    static let shared = PayloadInspectorService()
    private var panel: NSPanel?
    private var source: NSTextView?
    private var sourceScroll: NSScrollView?
    private var treeScroll: NSScrollView?
    private var outline: NSOutlineView?
    private var search: NSSearchField?
    private var mode: NSSegmentedControl?
    private var summary: NSTextField?
    private var empty: NSTextField?
    private var format: NSTextField?
    private var path: NSTextField?
    private var value: NSTextView?
    private var copyValue: NSButton?
    private var copyPath: NSButton?
    private var openJSON: NSButton?
    private var back: NSButton?
    private var detailViews: [NSView] = []
    private var document: PayloadInspector.Document?
    private var parents: [PayloadInspector.Document] = []
    private var root: Item?
    private var revision = 0
    private var filterRevision = 0
    private var pending: Task<Void, Never>?
    private var parsing: Task<PayloadInspector.Document, Error>?
    private var filtering: Task<Void, Never>?
    private var replacementAlert: NSAlert?
    private var strings: PayloadInspectorStrings { .localized(L10n.shared.language) }

    private final class Item: NSObject {
        let node: PayloadInspector.Node
        let children: [Item]
        init(_ node: PayloadInspector.Node) {
            self.node = node
            // XML indentation is preserved in Source and the model. The tree
            // presents leaf text as its element's value and keeps mixed text.
            children = node.children.filter { child in
                guard child.kind == .text else { return true }
                return node.value == nil && child.value?.contains(where: { !$0.isWhitespace }) == true
            }.map(Item.init)
        }
    }

    /// A tool handoff never replaces an open editor without an explicit choice.
    func receive(_ text: String) {
        guard AppFeature.clipboardHistory.isAvailable else { return }
        guard let panel, let source else { show(text: text); return }
        panel.makeKeyAndOrderFront(nil)
        guard source.string != text, panel.attachedSheet == nil else { return }
        let previous = source.string, generation = revision
        if previous.isEmpty { show(text: text); return }
        let alert = NSAlert()
        alert.messageText = SharedToolActionStrings.inspectorReplaceTitle
        alert.informativeText = SharedToolActionStrings.inspectorReplaceMessage
        alert.addButton(withTitle: SharedToolActionStrings.replace)
        alert.addButton(withTitle: SharedToolActionStrings.cancel)
        replacementAlert = alert
        alert.beginSheetModal(for: panel) { [weak self, weak panel] response in
            guard let self, let panel, self.panel === panel, self.replacementAlert === alert else { return }
            self.replacementAlert = nil
            guard response == .alertFirstButtonReturn, self.revision == generation,
                  self.source?.string == previous else { return }
            self.show(text: text)
        }
    }

    func show(text: String? = nil) {
        guard AppFeature.clipboardHistory.isAvailable else { return }
        panel?.close()
        let strings = strings
        let panel = PayloadInspectorPanel(contentRect: NSRect(x: 0, y: 0, width: 920, height: 650),
                                          styleMask: [.titled, .closable, .resizable, .nonactivatingPanel],
                                          backing: .buffered, defer: false)
        panel.title = strings.title
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 640, height: 460)
        panel.delegate = self
        ToolAppearance.configure(panel)
        let content = PayloadInspectorBackground()
        let header = PayloadInspectorBackground(color: ToolAppearance.surface)
        let detail = PayloadInspectorBackground(color: ToolAppearance.surface)
        detail.identifier = NSUserInterfaceItemIdentifier("payload.detail")
        let icon = NSImageView(image: NSImage(systemSymbolName: "curlybraces.square.fill", accessibilityDescription: nil)!)
        icon.contentTintColor = ToolAppearance.accent
        let format = NSTextField(labelWithString: "JSON / XML")
        format.font = .systemFont(ofSize: 13, weight: .semibold)
        format.textColor = ToolAppearance.text
        let back = button(strings.back, id: "payload.back", action: #selector(goBack))
        back.image = NSImage(systemSymbolName: "chevron.left", accessibilityDescription: nil)
        back.imagePosition = .imageOnly
        back.toolTip = strings.back
        back.isEnabled = false
        let mode = NSSegmentedControl(labels: [strings.tree, strings.source], trackingMode: .selectOne,
                                      target: self, action: #selector(changeMode))
        mode.identifier = NSUserInterfaceItemIdentifier("payload.mode")
        mode.controlSize = .small
        mode.selectedSegmentBezelColor = ToolAppearance.accent.withAlphaComponent(0.24)
        mode.selectedSegment = 0
        let search = NSSearchField()
        search.placeholderString = strings.search
        search.setAccessibilityLabel(strings.search)
        search.identifier = NSUserInterfaceItemIdentifier("payload.search")
        search.controlSize = .small
        search.textColor = ToolAppearance.text
        search.delegate = self
        let topRule = NSBox(), bottomRule = NSBox(), statusRule = NSBox()
        for rule in [topRule, bottomRule, statusRule] {
            rule.boxType = .custom; rule.borderWidth = 0
            rule.fillColor = ToolAppearance.border
        }

        let outline = NSOutlineView()
        outline.identifier = NSUserInterfaceItemIdentifier("payload.tree")
        outline.setAccessibilityLabel(strings.tree)
        let fieldColumn = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("field"))
        fieldColumn.width = 250; fieldColumn.minWidth = 140
        let valueColumn = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("value"))
        valueColumn.width = 270; valueColumn.minWidth = 140
        outline.addTableColumn(fieldColumn); outline.addTableColumn(valueColumn)
        outline.outlineTableColumn = fieldColumn
        outline.headerView = nil
        outline.rowHeight = 33
        outline.intercellSpacing = NSSize(width: 8, height: 2)
        outline.indentationPerLevel = 18
        outline.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        outline.usesAlternatingRowBackgroundColors = false
        outline.style = .fullWidth
        outline.backgroundColor = ToolAppearance.background
        outline.dataSource = self; outline.delegate = self
        let treeScroll = NSScrollView()
        treeScroll.hasVerticalScroller = true; treeScroll.hasHorizontalScroller = true
        treeScroll.autohidesScrollers = true
        treeScroll.backgroundColor = ToolAppearance.background
        treeScroll.contentInsets = NSEdgeInsets(top: 12, left: 0, bottom: 12, right: 0)
        treeScroll.documentView = outline
        let (sourceScroll, source) = editor(editable: true, id: "payload.source")
        source.setAccessibilityLabel(strings.source)
        sourceScroll.isHidden = true
        let empty = NSTextField(wrappingLabelWithString: strings.empty)
        empty.font = .systemFont(ofSize: 14)
        empty.textColor = ToolAppearance.secondaryText
        empty.alignment = .center
        empty.identifier = NSUserInterfaceItemIdentifier("payload.empty")

        let path = NSTextField(labelWithString: strings.selectField)
        path.font = .monospacedSystemFont(ofSize: 12, weight: .medium)
        path.textColor = ToolAppearance.accent
        path.lineBreakMode = .byTruncatingMiddle
        path.isSelectable = true
        path.identifier = NSUserInterfaceItemIdentifier("payload.path")
        let copyValue = button(strings.copyValue, id: "payload.copyValue", action: #selector(copySelectedValue))
        let copyPath = button(strings.copyPath, id: "payload.copyPath", action: #selector(copySelectedPath))
        let openJSON = button(strings.openJSON, id: "payload.openJSON", action: #selector(openEmbeddedJSON))
        for button in [copyValue, copyPath, openJSON] { button.isEnabled = false }
        let actions = NSStackView(views: [copyValue, copyPath])
        actions.orientation = .horizontal; actions.spacing = 8
        let (valueScroll, value) = editor(editable: false, id: "payload.value")
        value.font = .monospacedSystemFont(ofSize: 15, weight: .regular)
        value.textContainerInset = NSSize(width: 0, height: 8)
        valueScroll.drawsBackground = false; value.drawsBackground = false
        let summary = NSTextField(wrappingLabelWithString: strings.empty)
        summary.font = .systemFont(ofSize: 11)
        summary.textColor = ToolAppearance.secondaryText
        summary.maximumNumberOfLines = 2
        summary.identifier = NSUserInterfaceItemIdentifier("payload.summary")
        let local = NSTextField(labelWithString: strings.local)
        local.font = .systemFont(ofSize: 10)
        local.textColor = ToolAppearance.secondaryText
        local.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        local.lineBreakMode = .byTruncatingTail

        for view in [header, detail, icon, format, back, mode, search, topRule, treeScroll, sourceScroll, empty, bottomRule,
                     statusRule, summary, local] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        for view in [path, actions, openJSON, valueScroll] {
            view.translatesAutoresizingMaskIntoConstraints = false
            detail.addSubview(view)
        }
        let treeWidth = treeScroll.widthAnchor.constraint(equalTo: content.widthAnchor, multiplier: 0.42)
        // Beat content hugging, but let the window grow past the tree's cap.
        treeWidth.priority = NSLayoutConstraint.Priority(499)
        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            header.topAnchor.constraint(equalTo: content.topAnchor),
            header.bottomAnchor.constraint(equalTo: topRule.topAnchor),
            icon.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
            icon.topAnchor.constraint(equalTo: content.topAnchor, constant: 18),
            icon.widthAnchor.constraint(equalToConstant: 25), icon.heightAnchor.constraint(equalToConstant: 25),
            format.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 9),
            format.centerYAnchor.constraint(equalTo: icon.centerYAnchor),
            back.leadingAnchor.constraint(equalTo: format.trailingAnchor, constant: 10),
            back.centerYAnchor.constraint(equalTo: icon.centerYAnchor), back.widthAnchor.constraint(equalToConstant: 24),
            mode.leadingAnchor.constraint(equalTo: back.trailingAnchor, constant: 12),
            mode.centerYAnchor.constraint(equalTo: icon.centerYAnchor),
            search.leadingAnchor.constraint(greaterThanOrEqualTo: mode.trailingAnchor, constant: 16),
            search.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -18),
            search.widthAnchor.constraint(equalTo: content.widthAnchor, multiplier: 0.32),
            search.centerYAnchor.constraint(equalTo: icon.centerYAnchor),
            topRule.topAnchor.constraint(equalTo: content.topAnchor, constant: 62),
            topRule.leadingAnchor.constraint(equalTo: content.leadingAnchor), topRule.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            topRule.heightAnchor.constraint(equalToConstant: 1),
            treeScroll.topAnchor.constraint(equalTo: topRule.bottomAnchor),
            treeScroll.leadingAnchor.constraint(equalTo: content.leadingAnchor), treeScroll.trailingAnchor.constraint(equalTo: bottomRule.leadingAnchor),
            treeScroll.bottomAnchor.constraint(equalTo: statusRule.topAnchor),
            treeScroll.widthAnchor.constraint(greaterThanOrEqualToConstant: 260),
            treeScroll.widthAnchor.constraint(lessThanOrEqualToConstant: 420), treeWidth,
            sourceScroll.topAnchor.constraint(equalTo: treeScroll.topAnchor), sourceScroll.bottomAnchor.constraint(equalTo: statusRule.topAnchor),
            sourceScroll.leadingAnchor.constraint(equalTo: content.leadingAnchor), sourceScroll.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            empty.centerXAnchor.constraint(equalTo: treeScroll.centerXAnchor), empty.centerYAnchor.constraint(equalTo: treeScroll.centerYAnchor),
            empty.widthAnchor.constraint(lessThanOrEqualTo: treeScroll.widthAnchor, multiplier: 0.7),
            bottomRule.topAnchor.constraint(equalTo: topRule.bottomAnchor),
            bottomRule.bottomAnchor.constraint(equalTo: statusRule.topAnchor),
            bottomRule.trailingAnchor.constraint(equalTo: detail.leadingAnchor),
            bottomRule.widthAnchor.constraint(equalToConstant: 1),
            detail.topAnchor.constraint(equalTo: topRule.bottomAnchor),
            detail.bottomAnchor.constraint(equalTo: statusRule.topAnchor),
            detail.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            detail.widthAnchor.constraint(greaterThanOrEqualToConstant: 286),
            path.topAnchor.constraint(equalTo: detail.topAnchor, constant: 24),
            path.leadingAnchor.constraint(equalTo: detail.leadingAnchor, constant: 18),
            path.trailingAnchor.constraint(equalTo: detail.trailingAnchor, constant: -18),
            valueScroll.topAnchor.constraint(equalTo: path.bottomAnchor, constant: 18),
            valueScroll.leadingAnchor.constraint(equalTo: path.leadingAnchor),
            valueScroll.trailingAnchor.constraint(equalTo: path.trailingAnchor),
            valueScroll.bottomAnchor.constraint(equalTo: actions.topAnchor, constant: -16),
            actions.leadingAnchor.constraint(equalTo: path.leadingAnchor),
            actions.trailingAnchor.constraint(lessThanOrEqualTo: path.trailingAnchor),
            actions.bottomAnchor.constraint(equalTo: openJSON.topAnchor, constant: -10),
            openJSON.leadingAnchor.constraint(equalTo: path.leadingAnchor),
            openJSON.trailingAnchor.constraint(lessThanOrEqualTo: path.trailingAnchor),
            openJSON.bottomAnchor.constraint(equalTo: detail.bottomAnchor, constant: -22),
            statusRule.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -46),
            statusRule.leadingAnchor.constraint(equalTo: content.leadingAnchor), statusRule.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            statusRule.heightAnchor.constraint(equalToConstant: 1),
            summary.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
            summary.centerYAnchor.constraint(equalTo: statusRule.bottomAnchor, constant: 23),
            summary.trailingAnchor.constraint(lessThanOrEqualTo: local.leadingAnchor, constant: -14),
            local.centerYAnchor.constraint(equalTo: summary.centerYAnchor),
            local.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -18),
            local.widthAnchor.constraint(lessThanOrEqualTo: content.widthAnchor, multiplier: 0.27),
        ])
        panel.contentView = content
        self.panel = panel; self.source = source; self.sourceScroll = sourceScroll
        self.treeScroll = treeScroll; self.outline = outline; self.search = search; self.mode = mode
        self.summary = summary; self.empty = empty; self.path = path; self.value = value; self.format = format
        self.copyValue = copyValue; self.copyPath = copyPath; self.openJSON = openJSON; self.back = back
        self.detailViews = [bottomRule, detail]
        source.string = text ?? NSPasteboard.general.string(forType: .string)
            ?? ClipboardHistoryService.shared.entries.filter { $0.kind == .text }.max(by: { $0.copiedAt < $1.copiedAt })?.text ?? ""
        source.delegate = self
        if source.string.isEmpty { mode.selectedSegment = 1; changeMode() }
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(NSEvent.mouseLocation) }) ?? NSScreen.main {
            panel.setFrameOrigin(NSPoint(x: screen.visibleFrame.midX - panel.frame.width / 2,
                                         y: screen.visibleFrame.midY - panel.frame.height / 2))
        }
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(source.string.isEmpty ? source : search)
        refresh()
    }

    private func button(_ title: String, id: String, action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        ToolAppearance.style(button)
        button.identifier = NSUserInterfaceItemIdentifier(id)
        button.setAccessibilityLabel(title)
        return button
    }

    private func editor(editable: Bool, id: String) -> (NSScrollView, NSTextView) {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true
        let text = NSTextView()
        text.identifier = NSUserInterfaceItemIdentifier(id)
        text.isRichText = false; text.isEditable = editable; text.isSelectable = true; text.allowsUndo = editable
        text.isAutomaticQuoteSubstitutionEnabled = false; text.isAutomaticDashSubstitutionEnabled = false
        text.isAutomaticSpellingCorrectionEnabled = false; text.isAutomaticTextReplacementEnabled = false
        text.isAutomaticLinkDetectionEnabled = false
        text.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        text.textColor = ToolAppearance.text; text.backgroundColor = ToolAppearance.background
        text.insertionPointColor = ToolAppearance.accent
        text.selectedTextAttributes = [.backgroundColor: ToolAppearance.accent.withAlphaComponent(0.22),
                                       .foregroundColor: ToolAppearance.text]
        scroll.backgroundColor = ToolAppearance.background
        text.textContainerInset = NSSize(width: 18, height: 16)
        text.isVerticallyResizable = true; text.isHorizontallyResizable = false
        text.autoresizingMask = [.width]
        text.minSize = .zero; text.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        text.textContainer?.widthTracksTextView = true
        text.textContainer?.containerSize = NSSize(width: 500, height: CGFloat.greatestFiniteMagnitude)
        scroll.documentView = text
        return (scroll, text)
    }

    func textDidChange(_ notification: Notification) { refresh() }
    func controlTextDidChange(_ obj: Notification) { filter() }

    private func refresh() {
        revision += 1
        pending?.cancel(); parsing?.cancel(); filtering?.cancel()
        parents = []; document = nil; root = nil; back?.isEnabled = false
        outline?.reloadData(); selectionChanged()
        let input = source?.string ?? ""
        let generation = revision
        summary?.stringValue = strings.loading; empty?.stringValue = strings.loading
        empty?.isHidden = mode?.selectedSegment == 1 && !input.isEmpty
        format?.stringValue = "JSON / XML"
        pending = Task { @MainActor [weak self, weak panel] in
            do { try await Task.sleep(nanoseconds: 180_000_000) } catch { return }
            guard let self, let panel, self.panel === panel else { return }
            let work = Task.detached(priority: .userInitiated) { try PayloadInspector.parse(input) }
            self.parsing = work
            let result = await work.result
            guard !Task.isCancelled, self.revision == generation, self.panel === panel else { return }
            self.pending = nil; self.parsing = nil
            switch result {
            case .success(let document): self.install(document)
            case .failure(let error):
                let message = self.strings.message(error)
                self.summary?.stringValue = message; self.empty?.stringValue = message
                self.empty?.isHidden = self.mode?.selectedSegment == 1 && !input.isEmpty
            }
        }
    }

    private func install(_ document: PayloadInspector.Document) {
        self.document = document
        format?.stringValue = document.format + (parents.isEmpty ? "" : " ↳")
        back?.isEnabled = !parents.isEmpty
        summary?.stringValue = document.format + " · " + String(format: strings.fields, document.nodeCount)
        filter()
    }

    private func filter() {
        filtering?.cancel(); filterRevision += 1
        let generation = filterRevision, sourceRevision = revision
        guard let document else { return }
        let query = search?.stringValue.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        filtering = Task { @MainActor [weak self] in
            do { try await Task.sleep(nanoseconds: 70_000_000) } catch { return }
            let match = await Task.detached(priority: .userInitiated) { document.root.matching(query) }.value
            guard let self, !Task.isCancelled, generation == self.filterRevision, sourceRevision == self.revision else { return }
            self.root = match.map(Item.init)
            self.outline?.reloadData()
            if let root = self.root {
                self.outline?.expandItem(root, expandChildren: !query.isEmpty)
                self.outline?.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false)
            }
            self.empty?.stringValue = self.strings.noMatches
            self.empty?.isHidden = self.root != nil || self.mode?.selectedSegment == 1
            self.selectionChanged()
        }
    }

    @objc private func changeMode() {
        let showSource = mode?.selectedSegment == 1
        sourceScroll?.isHidden = !showSource; treeScroll?.isHidden = showSource
        detailViews.forEach { $0.isHidden = showSource }
        empty?.isHidden = (showSource && source?.string.isEmpty != true) || root != nil
        search?.isEnabled = !showSource
        if showSource, let source { panel?.makeFirstResponder(source) }
    }

    func outlineView(_ outlineView: NSOutlineView, numberOfChildrenOfItem item: Any?) -> Int {
        (item as? Item)?.children.count ?? (root == nil ? 0 : 1)
    }
    func outlineView(_ outlineView: NSOutlineView, child index: Int, ofItem item: Any?) -> Any {
        if let item = item as? Item { return item.children[index] }
        return root!
    }
    func outlineView(_ outlineView: NSOutlineView, isItemExpandable item: Any) -> Bool { !(item as! Item).children.isEmpty }
    func outlineView(_ outlineView: NSOutlineView, rowViewForItem item: Any) -> NSTableRowView? {
        PayloadInspectorRowView()
    }
    func outlineView(_ outlineView: NSOutlineView, viewFor tableColumn: NSTableColumn?, item: Any) -> NSView? {
        let item = item as! Item
        let node = item.node
        let field = tableColumn?.identifier.rawValue == "field"
        let label = NSTextField(labelWithString: "")
        label.font = .monospacedSystemFont(ofSize: 12, weight: field ? .medium : .regular)
        label.lineBreakMode = .byTruncatingTail
        label.textColor = field ? PayloadInspectorHighlighting.propertyColor
            : PayloadInspectorHighlighting.valueColor(for: node.kind)
        if field {
            let symbol: String
            switch node.kind {
            case .object: symbol = "{}"
            case .array: symbol = "[]"
            case .element: symbol = "<>"
            case .attribute: symbol = "@"
            case .string, .text: symbol = "“”"
            case .number: symbol = "#"
            case .boolean: symbol = "◐"
            case .null: symbol = "∅"
            }
            let name = node.kind == .attribute ? String(node.name.dropFirst()) : node.name
            let text = NSMutableAttributedString(string: symbol + "  " + name,
                                                 attributes: [.foregroundColor: PayloadInspectorHighlighting.propertyColor])
            text.addAttribute(.foregroundColor, value: ToolAppearance.accent, range: NSRange(location: 0, length: symbol.utf16.count))
            label.attributedStringValue = text
        } else if !item.children.isEmpty && !(node.kind == .element && node.value != nil) {
            label.stringValue = String(format: strings.fields, item.children.count)
            label.textColor = ToolAppearance.secondaryText
        } else {
            // Only the single-row preview is shortened. The full value remains
            // selectable below and is used by the explicit copy action.
            let preview = String((node.value ?? "").prefix(300))
            label.stringValue = preview.replacingOccurrences(of: "\r", with: "␍").replacingOccurrences(of: "\n", with: "↵").replacingOccurrences(of: "\t", with: "⇥")
            if (node.value?.count ?? 0) > 300 { label.stringValue += "…" }
            if node.kind == .string { label.stringValue = "\"" + label.stringValue + "\"" }
        }
        label.toolTip = field ? node.path : nil
        return label
    }
    func outlineViewSelectionDidChange(_ notification: Notification) { selectionChanged() }
    private var selected: PayloadInspector.Node? {
        guard let outline, outline.selectedRow >= 0 else { return nil }
        return (outline.item(atRow: outline.selectedRow) as? Item)?.node
    }
    private func selectionChanged() {
        let node = selected
        path?.stringValue = node?.path ?? strings.selectField
        path?.toolTip = node?.path
        if let value {
            if let node {
                value.textStorage?.setAttributedString(PayloadInspectorHighlighting.attributed(
                    node.value ?? "", kind: node.kind,
                    font: .monospacedSystemFont(ofSize: 15, weight: .regular)))
            } else { value.string = "" }
        }
        value?.scrollToBeginningOfDocument(nil)
        copyValue?.isEnabled = node?.value != nil
        copyPath?.isEnabled = node != nil
        openJSON?.isEnabled = node?.isEmbeddedJSON == true
    }
    @objc private func copySelectedValue() { if let value = selected?.value { copy(value) } }
    @objc private func copySelectedPath() { if let path = selected?.path { copy(path) } }
    private func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        summary?.stringValue = strings.copied
    }
    @objc private func openEmbeddedJSON() {
        guard let node = selected, node.isEmbeddedJSON, let text = node.value, let parent = document else { return }
        pending?.cancel(); parsing?.cancel()
        let generation = revision
        summary?.stringValue = strings.loading
        pending = Task { @MainActor [weak self, weak panel] in
            let work = Task.detached(priority: .userInitiated) { try PayloadInspector.parse(text) }
            self?.parsing = work
            let result = await work.result
            guard let self, let panel, self.panel === panel, !Task.isCancelled, self.revision == generation else { return }
            self.parsing = nil; self.pending = nil
            switch result {
            case .success(let document):
                self.parents.append(parent); self.search?.stringValue = ""; self.install(document)
            case .failure(let error): self.summary?.stringValue = self.strings.message(error)
            }
        }
    }
    @objc private func goBack() {
        guard let parent = parents.popLast() else { return }
        pending?.cancel(); parsing?.cancel()
        search?.stringValue = ""
        install(parent)
    }
    func windowWillClose(_ notification: Notification) {
        let alert = replacementAlert
        replacementAlert = nil
        if let alert, panel?.attachedSheet === alert.window { panel?.endSheet(alert.window, returnCode: .abort) }
        revision += 1; filterRevision += 1
        pending?.cancel(); parsing?.cancel(); filtering?.cancel()
        pending = nil; parsing = nil; filtering = nil
        document = nil; parents = []; root = nil
        source = nil; sourceScroll = nil; treeScroll = nil; outline = nil; search = nil; mode = nil
        summary = nil; empty = nil; path = nil; value = nil; format = nil
        copyValue = nil; copyPath = nil; openJSON = nil; back = nil
        detailViews = []
        panel?.contentView = nil; panel = nil
    }
}

private final class PayloadInspectorPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { close() }
}

private final class PayloadInspectorBackground: NSView {
    private let color: NSColor
    init(color: NSColor = ToolAppearance.background) { self.color = color; super.init(frame: .zero) }
    required init?(coder: NSCoder) { return nil }
    override var isOpaque: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        color.setFill()
        dirtyRect.fill()
    }
    override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsDisplay = true }
}

private final class PayloadInspectorRowView: NSTableRowView {
    override var interiorBackgroundStyle: NSView.BackgroundStyle { .normal }
    override func drawSelection(in dirtyRect: NSRect) {
        guard selectionHighlightStyle != .none else { return }
        let rect = bounds.insetBy(dx: 6, dy: 2)
        ToolAppearance.accent.withAlphaComponent(0.14).setFill()
        NSBezierPath(roundedRect: rect, xRadius: 6, yRadius: 6).fill()
        ToolAppearance.accent.setFill()
        NSBezierPath(roundedRect: NSRect(x: rect.minX, y: rect.minY, width: 2, height: rect.height),
                     xRadius: 1, yRadius: 1).fill()
    }
}
