// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

final class ClipboardDiffService: NSObject, NSWindowDelegate, NSTextViewDelegate {
    static let shared = ClipboardDiffService()
    private var panel: NSPanel?
    private var calculation: Task<Void, Never>?
    private var comparisonWork: Task<ClipboardDiff.Comparison, Error>?
    private var formatting: Task<Void, Never>?
    private var formatWork: Task<ClipboardDiff.Pair, Error>?
    private var generation = 0
    private var beforeText: ClipboardDiffTextView?
    private var afterText: ClipboardDiffTextView?
    private var beforeLabel: NSTextField?
    private var afterLabel: NSTextField?
    private var beforeName: String?
    private var afterName: String?
    private var summary: NSTextField?
    private var position: NSTextField?
    private var previousButton: NSButton?
    private var nextButton: NSButton?
    private var formatButton: NSButton?
    private var formatError: String?
    private var comparison: ClipboardDiff.Comparison?
    private var currentChange: Int?
    private var synchronizing = false

    /// Direct handoff from a selected item. The other draft and clipboard stay intact.
    func receive(_ text: String, asBefore: Bool, name: String?) {
        guard AppFeature.clipboardHistory.isAvailable else { return }
        guard let panel, let editor = asBefore ? beforeText : afterText else {
            show(pair: .init(older: asBefore ? text : "", newer: asBefore ? "" : text),
                 beforeName: asBefore ? name : nil, afterName: asBefore ? nil : name)
            if !asBefore { self.panel?.makeFirstResponder(afterText) }
            return
        }
        panel.makeKeyAndOrderFront(nil)
        guard panel.attachedSheet == nil else { return }
        guard editor.string != text else { return }
        let previous = editor.string
        if previous.isEmpty {
            replace(editor, with: text, name: name)
            return
        }
        let diff = ClipboardDiffStrings.localized(L10n.shared.language)
        let alert = NSAlert()
        alert.messageText = SharedToolActionStrings.replaceTitle(side: asBefore ? diff.before : diff.after)
        alert.informativeText = SharedToolActionStrings.replaceMessage
        alert.addButton(withTitle: SharedToolActionStrings.replace)
        alert.addButton(withTitle: SharedToolActionStrings.cancel)
        alert.beginSheetModal(for: panel) { [weak self, weak panel, weak editor] response in
            guard response == .alertFirstButtonReturn, AppFeature.clipboardHistory.isAvailable,
                  let self, let panel, let editor,
                  self.panel === panel, editor.string == previous else { return }
            self.replace(editor, with: text, name: name)
        }
    }

    private func replace(_ editor: ClipboardDiffTextView, with text: String, name: String?) {
        // End typing coalescence before the separate native replacement action.
        beforeText?.breakUndoCoalescing(); afterText?.breakUndoCoalescing()
        let undo = editor.undoManager
        undo?.beginUndoGrouping()
        editor.insertText(text, replacementRange: NSRange(location: 0, length: (editor.string as NSString).length))
        editor.breakUndoCoalescing()
        setSourceName(name, isBefore: editor.isBefore, undo: undo)
        undo?.endUndoGrouping()
        undo?.setActionName(SharedToolActionStrings.replace)
        panel?.makeFirstResponder(editor)
    }

    private func setSourceName(_ name: String?, isBefore: Bool, undo: UndoManager?) {
        let previous = isBefore ? beforeName : afterName
        guard previous != name else { return }
        undo?.registerUndo(withTarget: self) { [weak undo, weak panel] service in
            guard let panel, service.panel === panel else { return }
            service.setSourceName(previous, isBefore: isBefore, undo: undo)
        }
        if isBefore { beforeName = name } else { afterName = name }
        if let label = isBefore ? beforeLabel : afterLabel { Self.setLabel(label, isBefore: isBefore, name: name) }
    }

    private static func setLabel(_ label: NSTextField, isBefore: Bool, name: String?) {
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        let text = (isBefore ? "−  " + strings.before : "+  " + strings.after) + (name.map { " · " + $0 } ?? "")
        let title = NSMutableAttributedString(string: text, attributes: [.foregroundColor: ToolAppearance.secondaryText])
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineBreakMode = .byTruncatingMiddle
        title.addAttribute(.paragraphStyle, value: paragraph, range: NSRange(location: 0, length: title.length))
        title.addAttribute(.foregroundColor, value: isBefore ? ToolAppearance.before : ToolAppearance.after,
                           range: NSRange(location: 0, length: 1))
        label.attributedStringValue = title
        label.toolTip = text
    }

    func show(pair suppliedPair: ClipboardDiff.Pair? = nil, beforeName: String? = nil, afterName: String? = nil) {
        guard AppFeature.clipboardHistory.isAvailable else { return }
        panel?.close()
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        let pair = suppliedPair ?? ClipboardDiff.latestPair(in: ClipboardHistoryService.shared.entries)
        let panel = ClipboardDiffPanel(contentRect: NSRect(x: 0, y: 0, width: 1040, height: 640),
                                      styleMask: [.titled, .closable, .resizable, .nonactivatingPanel],
                                      backing: .buffered, defer: false)
        panel.title = strings.title
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 620, height: 360)
        panel.delegate = self
        ToolAppearance.configure(panel)
        let content = ClipboardDiffBackground()
        let beforeLabel = NSTextField(labelWithString: ""), afterLabel = NSTextField(labelWithString: "")
        for label in [beforeLabel, afterLabel] {
            label.font = .systemFont(ofSize: 11, weight: .medium)
            label.textColor = ToolAppearance.secondaryText
            label.lineBreakMode = .byTruncatingMiddle
            label.maximumNumberOfLines = 1
            label.cell?.usesSingleLineMode = true
            label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        }
        Self.setLabel(beforeLabel, isBefore: true, name: beforeName)
        Self.setLabel(afterLabel, isBefore: false, name: afterName)
        let (beforeScroll, beforeText) = Self.editor(label: strings.before, isBefore: true)
        let (afterScroll, afterText) = Self.editor(label: strings.after, isBefore: false)
        let format = NSButton(title: "JSON", target: self, action: #selector(formatJSON(_:)))
        ToolAppearance.style(format)
        format.toolTip = strings.before + " + " + strings.after + ": " + strings.formatJSON
        format.identifier = NSUserInterfaceItemIdentifier("diff.formatJSON")
        format.setAccessibilityLabel(format.toolTip)
        beforeText.placeholder = strings.pasteHint; afterText.placeholder = strings.pasteHint
        let toolbarRule = ClipboardDiffRule(), topRule = ClipboardDiffRule()
        let middleRule = ClipboardDiffRule(), bottomRule = ClipboardDiffRule()
        let summary = NSTextField(wrappingLabelWithString: strings.missing)
        summary.identifier = NSUserInterfaceItemIdentifier("diff.summary")
        summary.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        summary.textColor = ToolAppearance.text
        summary.maximumNumberOfLines = 2
        let hint = NSTextField(labelWithString: SharedToolActionStrings.editableHint)
        hint.font = .systemFont(ofSize: 10)
        hint.textColor = ToolAppearance.secondaryText
        hint.lineBreakMode = .byTruncatingTail
        hint.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let position = NSTextField(labelWithString: "")
        position.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular)
        position.textColor = ToolAppearance.secondaryText
        position.alignment = .center
        let previous = NSButton(image: NSImage(systemSymbolName: "chevron.up", accessibilityDescription: strings.previousChange)!, target: self, action: #selector(previousChange))
        let next = NSButton(image: NSImage(systemSymbolName: "chevron.down", accessibilityDescription: strings.nextChange)!, target: self, action: #selector(nextChange))
        for (button, label, identifier) in [(previous, strings.previousChange, "diff.previous"), (next, strings.nextChange, "diff.next")] {
            ToolAppearance.style(button)
            button.imagePosition = .imageOnly
            button.toolTip = label
            button.setAccessibilityLabel(label)
            button.identifier = NSUserInterfaceItemIdentifier(identifier)
            button.isEnabled = false
        }
        previous.keyEquivalent = "\u{f700}"; previous.keyEquivalentModifierMask = [.option, .command]
        next.keyEquivalent = "\u{f701}"; next.keyEquivalentModifierMask = [.option, .command]
        for view in [beforeLabel, afterLabel, beforeScroll, afterScroll, toolbarRule, topRule, middleRule, bottomRule, summary, hint, position, previous, next, format] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            summary.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
            summary.centerYAnchor.constraint(equalTo: content.topAnchor, constant: 26),
            summary.trailingAnchor.constraint(lessThanOrEqualTo: format.leadingAnchor, constant: -16),
            next.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),
            next.centerYAnchor.constraint(equalTo: summary.centerYAnchor),
            next.widthAnchor.constraint(equalToConstant: 28),
            previous.trailingAnchor.constraint(equalTo: next.leadingAnchor, constant: -6),
            previous.centerYAnchor.constraint(equalTo: next.centerYAnchor),
            previous.widthAnchor.constraint(equalToConstant: 28),
            format.trailingAnchor.constraint(equalTo: previous.leadingAnchor, constant: -8),
            format.centerYAnchor.constraint(equalTo: summary.centerYAnchor),
            toolbarRule.topAnchor.constraint(equalTo: content.topAnchor, constant: 51),
            toolbarRule.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            toolbarRule.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            toolbarRule.heightAnchor.constraint(equalToConstant: 1),
            beforeLabel.centerYAnchor.constraint(equalTo: toolbarRule.bottomAnchor, constant: 20),
            beforeLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
            beforeLabel.trailingAnchor.constraint(lessThanOrEqualTo: beforeScroll.trailingAnchor, constant: -16),
            afterLabel.topAnchor.constraint(equalTo: beforeLabel.topAnchor),
            afterLabel.leadingAnchor.constraint(equalTo: afterScroll.leadingAnchor, constant: 18),
            afterLabel.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -18),
            topRule.topAnchor.constraint(equalTo: toolbarRule.bottomAnchor, constant: 40),
            topRule.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            topRule.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            topRule.heightAnchor.constraint(equalToConstant: 1),
            beforeScroll.topAnchor.constraint(equalTo: topRule.bottomAnchor),
            beforeScroll.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            beforeScroll.widthAnchor.constraint(equalTo: afterScroll.widthAnchor),
            beforeScroll.bottomAnchor.constraint(equalTo: bottomRule.topAnchor),
            middleRule.leadingAnchor.constraint(equalTo: beforeScroll.trailingAnchor),
            middleRule.widthAnchor.constraint(equalToConstant: 1),
            middleRule.topAnchor.constraint(equalTo: toolbarRule.bottomAnchor),
            middleRule.bottomAnchor.constraint(equalTo: bottomRule.topAnchor),
            afterScroll.leadingAnchor.constraint(equalTo: middleRule.trailingAnchor),
            afterScroll.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            afterScroll.topAnchor.constraint(equalTo: beforeScroll.topAnchor),
            afterScroll.bottomAnchor.constraint(equalTo: beforeScroll.bottomAnchor),
            bottomRule.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bottomRule.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            bottomRule.heightAnchor.constraint(equalToConstant: 1),
            bottomRule.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -40),
            hint.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            hint.centerYAnchor.constraint(equalTo: bottomRule.bottomAnchor, constant: 20),
            hint.trailingAnchor.constraint(lessThanOrEqualTo: position.leadingAnchor, constant: -12),
            position.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),
            position.centerYAnchor.constraint(equalTo: hint.centerYAnchor),
            position.widthAnchor.constraint(equalToConstant: 56),
        ])
        panel.contentView = content
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(NSEvent.mouseLocation) }) ?? NSScreen.main {
            let frame = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: frame.midX - panel.frame.width / 2, y: frame.midY - panel.frame.height / 2))
        }
        self.panel = panel
        self.beforeText = beforeText; self.afterText = afterText
        self.beforeLabel = beforeLabel; self.afterLabel = afterLabel
        self.beforeName = beforeName; self.afterName = afterName
        self.summary = summary; self.position = position
        previousButton = previous; nextButton = next
        formatButton = format
        beforeText.string = pair?.older ?? ""; afterText.string = pair?.newer ?? ""
        beforeText.delegate = self; afterText.delegate = self
        for scroll in [beforeScroll, afterScroll] {
            scroll.contentView.postsBoundsChangedNotifications = true
            NotificationCenter.default.addObserver(self, selector: #selector(scrolled(_:)), name: NSView.boundsDidChangeNotification, object: scroll.contentView)
        }
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(beforeText)
        content.layoutSubtreeIfNeeded()
        refreshComparison()
    }

    private static func editor(label: String, isBefore: Bool) -> (NSScrollView, ClipboardDiffTextView) {
        let scroll = NSScrollView()
        scroll.borderType = .noBorder
        scroll.backgroundColor = ToolAppearance.surface
        scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = true
        let text = ClipboardDiffTextView(isBefore: isBefore, label: label)
        scroll.documentView = text
        let gutter = ClipboardDiffGutter(scroll: scroll, editor: text)
        text.gutter = gutter
        scroll.verticalRulerView = gutter
        scroll.hasVerticalRuler = true; scroll.rulersVisible = true
        return (scroll, text)
    }

    func textDidChange(_ notification: Notification) { refreshComparison() }

    private func refreshComparison() {
        guard let panel, let beforeText, let afterText, let summary else { return }
        calculation?.cancel(); comparisonWork?.cancel()
        formatting?.cancel(); formatWork?.cancel()
        formatting = nil; formatWork = nil; formatError = nil
        formatButton?.isEnabled = (!beforeText.string.isEmpty || !afterText.string.isEmpty)
            && !beforeText.hasMarkedText() && !afterText.hasMarkedText()
        generation += 1
        let revision = generation
        comparison = nil; currentChange = nil
        updateNavigation()
        beforeText.invalidateComparison(); afterText.invalidateComparison()
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        let pair = ClipboardDiff.Pair(older: beforeText.string, newer: afterText.string)
        if pair.older.isEmpty && pair.newer.isEmpty {
            summary.stringValue = strings.missing
            fitDocuments()
            return
        }
        summary.stringValue = strings.loading
        // Debounce and cancel work as well as delivery. Nothing writes history,
        // pasteboard or disk, and no comparison replaces the text storage.
        calculation = Task { @MainActor [weak self, weak panel] in
            do { try await Task.sleep(nanoseconds: 180_000_000) } catch { return }
            guard let self, let panel, self.panel === panel else { return }
            let work = Task.detached(priority: .userInitiated) { try ClipboardDiff.compare(pair) }
            self.comparisonWork = work
            let result = await work.result
            guard !Task.isCancelled, self.generation == revision, self.panel === panel else { return }
            switch result {
            case .success(let comparison):
                self.install(comparison)
                summary.stringValue = self.formatError ?? (comparison.isIdentical ? strings.identical : strings.summary(changed: comparison.changedLines, added: comparison.addedLines, removed: comparison.removedLines))
            case .failure:
                summary.stringValue = self.formatError ?? strings.tooLarge
                self.fitDocuments()
            }
            self.calculation = nil; self.comparisonWork = nil
        }
    }

    @objc private func formatJSON(_ sender: NSButton) {
        guard let panel, let beforeText, let afterText,
              !beforeText.hasMarkedText(), !afterText.hasMarkedText() else { return }
        formatting?.cancel(); formatWork?.cancel()
        let input = ClipboardDiff.Pair(older: beforeText.string, newer: afterText.string)
        let revision = generation
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        sender.isEnabled = false
        formatting = Task { @MainActor [weak self, weak panel] in
            guard let self, let panel else { return }
            let work = Task.detached(priority: .userInitiated) {
                func formatted(_ text: String, isBefore: Bool) throws -> String {
                    guard !text.isEmpty else { return text }
                    do { return try ClipboardDiff.formatJSON(text) }
                    catch { throw FormattingFailure(isBefore: isBefore, reason: error) }
                }
                return try ClipboardDiff.Pair(older: formatted(input.older, isBefore: true),
                                              newer: formatted(input.newer, isBefore: false))
            }
            self.formatWork = work
            let result = await work.result
            guard !Task.isCancelled, self.generation == revision, self.panel === panel else { return }
            self.formatting = nil; self.formatWork = nil
            sender.isEnabled = !input.older.isEmpty || !input.newer.isEmpty
            switch result {
            case .success(let formatted):
                guard formatted.older != input.older || formatted.newer != input.newer else {
                    self.refreshComparison(); return
                }
                // Validate both drafts before editing either. AppKit's shared
                // window undo manager makes this one reversible user action.
                beforeText.breakUndoCoalescing(); afterText.breakUndoCoalescing()
                let undo = beforeText.undoManager
                undo?.beginUndoGrouping()
                for (editor, text) in [(beforeText, formatted.older), (afterText, formatted.newer)] where editor.string != text {
                    editor.insertText(text, replacementRange: NSRange(location: 0, length: (editor.string as NSString).length))
                    editor.breakUndoCoalescing()
                }
                undo?.endUndoGrouping()
                undo?.setActionName(strings.formatJSON)
            case .failure(let error):
                guard let failure = error as? FormattingFailure else { return }
                let message: String
                switch failure.reason {
                case ClipboardDiff.Failure.tooLarge: message = strings.tooLarge
                case ClipboardDiff.Failure.formattedTooLarge: message = strings.formattedTooLarge
                default: message = strings.invalidJSON
                }
                let side = failure.isBefore ? strings.before : strings.after
                self.formatError = side + ": " + message
                self.summary?.stringValue = self.formatError!
            }
        }
    }

    private struct FormattingFailure: Error {
        let isBefore: Bool
        let reason: Error
    }

    private func install(_ result: ClipboardDiff.Comparison) {
        guard let beforeText, let afterText else { return }
        let active = (panel?.firstResponder as? ClipboardDiffTextView) ?? beforeText
        let origin = active.viewportOrigin
        let oldRow = max(0, Int((origin.y - active.textContainerOrigin.y) / ClipboardDiffLayoutManager.rowHeight))
        let sourceLine = active.diffLayout.alignedRows.lastIndex(where: { $0 <= oldRow }) ?? 0
        let oldAligned = active.diffLayout.alignedRows[sourceLine]
        let distance = origin.y - active.rowY(oldAligned)
        synchronizing = true
        beforeText.apply(result); afterText.apply(result)
        comparison = result
        fitDocuments()
        let newAligned = active.diffLayout.alignedRows[min(sourceLine, active.diffLayout.alignedRows.count - 1)]
        let y = max(0, active.rowY(newAligned) + distance)
        for editor in [beforeText, afterText] { editor.scrollToContent(NSPoint(x: origin.x, y: y)) }
        synchronizing = false
        updateNavigation()
    }

    private func fitDocuments() {
        guard let beforeText, let afterText else { return }
        let wasSynchronizing = synchronizing
        synchronizing = true
        defer { synchronizing = wasSynchronizing }
        let editors = [beforeText, afterText]
        var width: CGFloat = 0, height: CGFloat = 0
        for editor in editors {
            guard let container = editor.textContainer, let scroll = editor.enclosingScrollView else { continue }
            editor.diffLayout.ensureLayout(for: container)
            width = max(width, scroll.contentSize.width - (editor.gutter?.ruleThickness ?? 0), editor.diffLayout.usedRect(for: container).maxX + 2 * editor.textContainerInset.width)
            let count = max(editor.diffRows.count, editor.diffLayout.starts.count)
            height = max(height, scroll.contentSize.height, CGFloat(count) * ClipboardDiffLayoutManager.rowHeight + 2 * editor.textContainerInset.height)
        }
        for editor in editors {
            editor.minSize = NSSize(width: width, height: height)
            editor.setFrameSize(NSSize(width: width, height: height))
            editor.gutter?.needsDisplay = true
        }
    }

    func windowDidResize(_ notification: Notification) { fitDocuments() }

    @objc private func scrolled(_ notification: Notification) {
        guard !synchronizing, let source = notification.object as? NSClipView,
              let beforeText, let afterText else { return }
        synchronizing = true
        let editor = source === beforeText.enclosingScrollView?.contentView ? beforeText : afterText
        let other = editor === beforeText ? afterText : beforeText
        if let scroll = other.enclosingScrollView {
            // Clip bounds include AppKit's ruler/content offsets. Synchronize
            // document coordinates so resizing cannot displace the source text.
            other.scrollToContent(editor.viewportOrigin)
            scroll.reflectScrolledClipView(scroll.contentView)
        }
        beforeText.gutter?.needsDisplay = true; afterText.gutter?.needsDisplay = true
        synchronizing = false
    }

    private func updateNavigation() {
        let count = comparison?.groups.count ?? 0
        previousButton?.isEnabled = count > 0; nextButton?.isEnabled = count > 0
        position?.stringValue = currentChange.map { "\($0 + 1) / \(count)" } ?? ""
    }

    @objc private func previousChange() { navigate(-1) }
    @objc private func nextChange() { navigate(1) }
    private func navigate(_ direction: Int) {
        guard let comparison, !comparison.groups.isEmpty, let beforeText, let afterText else { return }
        let count = comparison.groups.count
        let next = currentChange.map { ($0 + direction + count) % count } ?? (direction > 0 ? 0 : count - 1)
        currentChange = next
        let group = comparison.groups[next]
        for editor in [beforeText, afterText] {
            editor.selectedChange = group
            if let scroll = editor.enclosingScrollView {
                editor.scrollToContent(NSPoint(x: editor.viewportOrigin.x, y: max(0, editor.rowY(group.lowerBound) - 48)))
                scroll.reflectScrolledClipView(scroll.contentView)
            }
        }
        updateNavigation()
    }

    func windowWillClose(_ notification: Notification) {
        generation += 1
        calculation?.cancel(); calculation = nil
        comparisonWork?.cancel(); comparisonWork = nil
        formatting?.cancel(); formatting = nil
        formatWork?.cancel(); formatWork = nil
        NotificationCenter.default.removeObserver(self, name: NSView.boundsDidChangeNotification, object: nil)
        beforeText = nil; afterText = nil; summary = nil; position = nil
        beforeLabel = nil; afterLabel = nil
        beforeName = nil; afterName = nil
        previousButton = nil; nextButton = nil; comparison = nil; currentChange = nil
        formatButton = nil; formatError = nil
        panel?.contentView = nil
        panel = nil
    }
}

private final class ClipboardDiffPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { close() }
}

private final class ClipboardDiffBackground: NSView {
    override var isOpaque: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        ToolAppearance.background.setFill()
        dirtyRect.fill()
    }
}

private final class ClipboardDiffRule: NSView {
    override func draw(_ dirtyRect: NSRect) {
        ToolAppearance.border.setFill()
        dirtyRect.intersection(bounds).fill()
    }
}
