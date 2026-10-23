// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import Carbon.HIToolbox
import ImageIO

/// A menu owns an immutable selected item, never the changing system clipboard.
enum SharedToolActions {
    enum Content {
        case text(String)
        case image(CGImage)
        case imageFile(String)
    }

    enum Action: CaseIterable {
        case inspect, before, after, saveSnippet, extract, annotate
        var title: String {
            switch self {
            case .inspect: return SharedToolActionStrings.inspect
            case .before: return SharedToolActionStrings.before
            case .after: return SharedToolActionStrings.after
            case .saveSnippet: return SnippetCaptureStrings.localized(L10n.shared.language).save
            case .extract: return SharedToolActionStrings.extract
            case .annotate: return SharedToolActionStrings.annotate
            }
        }

    }

    private static var current: SharedToolActionMenu?

    static func supports(entry: ClipboardHistoryEntry) -> Bool {
        switch entry.kind {
        case .text: return !actions(for: .text(entry.text)).isEmpty
        case .image: return entry.imageFile != nil && !actions(for: .imageFile(entry.imageFile!)).isEmpty
        case .files: return false
        }
    }

    static func present(entry: ClipboardHistoryEntry, from window: NSWindow, owner: UUID,
                        onClose: @escaping () -> Void = {}) {
        guard supports(entry: entry) else { return }
        let content: Content
        switch entry.kind {
        case .text: content = .text(entry.text)
        case .image:
            guard let file = entry.imageFile else { return }
            content = .imageFile(file)
        case .files: return
        }
        present(content: content, title: entry.preview, from: window, owner: owner, onClose: onClose)
    }

    static func present(content: Content, title: String, from window: NSWindow?, owner: UUID,
                        onAnnotate: (() -> Void)? = nil, onClose: @escaping () -> Void = {}) {
        if current?.owner == owner { cancel(owner: owner); return }
        current?.close(restoreFocus: false)
        guard !actions(for: content).isEmpty else { onClose(); return }
        let menu = SharedToolActionMenu(content: content, title: title, parent: window, owner: owner,
                                        onAnnotate: onAnnotate) {
            current = nil
            onClose()
        }
        current = menu
        menu.show()
    }

    static func cancel(owner: UUID) {
        guard current?.owner == owner else { return }
        current?.close(restoreFocus: false)
    }

    static func owns(window: NSWindow?, owner: UUID) -> Bool {
        guard let menu = current, menu.owner == owner else { return false }
        return window === menu.panel
    }

    static func actions(for content: Content) -> [Action] {
        switch content {
        case .text:
            return (AppFeature.textSnippets.isAvailable ? [.saveSnippet] : [])
                + (AppFeature.clipboardHistory.isAvailable ? [.inspect, .before, .after] : [])
        case .image, .imageFile:
            return (AppFeature.screenOCR.isAvailable ? [.extract] : [])
                + (AppFeature.screenshot.isAvailable ? [.annotate, .before, .after] : [])
        }
    }

    static func run(_ action: Action, content: Content, title: String) {
        guard actions(for: content).contains(action) else { return }
        switch (action, content) {
        case (.inspect, .text(let text)): PayloadInspectorService.shared.receive(text)
        case (.before, .text(let text)), (.after, .text(let text)):
            ClipboardDiffService.shared.receive(text, asBefore: action == .before, name: nil)
        case (.saveSnippet, .text(let text)): SnippetLibraryService.shared.saveCapturedText(text)
        case (.extract, .image(let image)): ExtractedTextController.show(image: image)
        case (.annotate, .image(let image)): ScreenshotService.shared.annotate(image)
        case (.before, .image(let image)), (.after, .image(let image)):
            ScreenCompareService.shared.receive(image, asBefore: action == .before, name: title)
        default: break
        }
    }
}

private final class SharedToolActionPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

private final class SharedToolActionButton: NSButton {
    var menuSelected = false { didSet { needsDisplay = true } }
    private var hovered = false
    private var hoverArea: NSTrackingArea?

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let hoverArea { removeTrackingArea(hoverArea) }
        let area = NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
                                  owner: self, userInfo: nil)
        addTrackingArea(area); hoverArea = area
    }
    override func mouseEntered(with event: NSEvent) { hovered = true; needsDisplay = true }
    override func mouseExited(with event: NSEvent) { hovered = false; needsDisplay = true }

    override func draw(_ dirtyRect: NSRect) {
        let shape = NSBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), xRadius: 7, yRadius: 7)
        if menuSelected || isHighlighted {
            ToolAppearance.raised.withAlphaComponent(isHighlighted ? 1 : 0.85).setFill()
            shape.fill()
            ToolAppearance.accent.setFill()
            NSBezierPath(roundedRect: NSRect(x: 3, y: (bounds.height - 10) / 2, width: 2, height: 10),
                         xRadius: 1, yRadius: 1).fill()
        } else if hovered && isEnabled {
            ToolAppearance.raised.setFill(); shape.fill()
        }
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineBreakMode = .byTruncatingTail
        let label = NSAttributedString(string: title, attributes: [
            .font: font ?? NSFont.systemFont(ofSize: 12, weight: .medium),
            .foregroundColor: isEnabled ? ToolAppearance.text : ToolAppearance.secondaryText,
            .paragraphStyle: paragraph
        ])
        let height = ceil(label.size().height)
        label.draw(in: NSRect(x: 12, y: floor((bounds.height - height) / 2),
                              width: max(0, bounds.width - 24), height: height))
    }
}

private final class SharedToolActionMenu: NSObject, NSWindowDelegate {
    let owner: UUID
    let panel = SharedToolActionPanel(contentRect: NSRect(x: 0, y: 0, width: 288, height: 156),
                                     styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    private weak var parent: NSWindow?
    private weak var previousResponder: NSResponder?
    private let title: String
    private var content: SharedToolActions.Content
    private var onClose: (() -> Void)?
    private let onAnnotate: (() -> Void)?
    private let rows = NSStackView()
    private let status = NSTextField(labelWithString: "")
    private var buttons: [SharedToolActionButton] = []
    private var shown: [SharedToolActions.Action] = []
    private var selected = 0
    private var loading = false
    private var failed = false
    private var monitors: [Any] = []
    private var parentObserver: NSObjectProtocol?
    private var closed = false

    init(content: SharedToolActions.Content, title: String, parent: NSWindow?, owner: UUID,
         onAnnotate: (() -> Void)?, onClose: @escaping () -> Void) {
        self.content = content; self.title = title; self.parent = parent; self.owner = owner
        self.onClose = onClose; self.onAnnotate = onAnnotate
        previousResponder = parent?.firstResponder
        super.init()
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        panel.level = parent?.level ?? .floating
        panel.appearance = parent?.effectiveAppearance
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        ToolAppearance.configure(panel)
        let root = NSView()
        root.wantsLayer = true
        root.layer?.cornerRadius = 12
        root.layer?.masksToBounds = true
        root.layer?.borderWidth = 0.5
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.title = SharedToolActionStrings.actions
        panel.contentView = root
        let backdrop = NSVisualEffectView(frame: root.bounds)
        backdrop.material = .menu
        backdrop.blendingMode = .behindWindow
        backdrop.state = .active
        backdrop.autoresizingMask = [.width, .height]
        root.addSubview(backdrop)
        // Keep the charcoal tint and controls above the material, outside vibrancy.
        let tint = NSView(frame: root.bounds)
        tint.wantsLayer = true
        tint.autoresizingMask = [.width, .height]
        root.addSubview(tint)
        panel.effectiveAppearance.performAsCurrentDrawingAppearance {
            tint.layer?.backgroundColor = ToolAppearance.background.withAlphaComponent(0.88).cgColor
            root.layer?.borderColor = ToolAppearance.secondaryText.withAlphaComponent(0.24).cgColor
        }
        let heading = NSTextField(labelWithString: SharedToolActionStrings.actions)
        heading.font = .systemFont(ofSize: 11, weight: .semibold)
        heading.textColor = ToolAppearance.secondaryText
        heading.setContentHuggingPriority(.required, for: .horizontal)
        heading.setContentCompressionResistancePriority(.required, for: .horizontal)
        let caption = NSTextField(labelWithString: title.replacingOccurrences(of: "\n", with: " "))
        caption.font = .systemFont(ofSize: 10, weight: .regular)
        caption.textColor = ToolAppearance.secondaryText.withAlphaComponent(0.70)
        caption.alignment = .right
        caption.lineBreakMode = .byTruncatingTail
        caption.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        rows.orientation = .vertical; rows.alignment = .leading; rows.spacing = 4
        status.font = .systemFont(ofSize: 10)
        status.textColor = ToolAppearance.secondaryText
        let header = NSStackView(views: [heading, caption])
        header.orientation = .horizontal; header.alignment = .centerY; header.spacing = 12
        header.distribution = .fill
        header.edgeInsets = NSEdgeInsets(top: 0, left: 12, bottom: 0, right: 12)
        let stack = NSStackView(views: [header, rows, status])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 8
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: root.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: root.bottomAnchor, constant: -12),
            header.widthAnchor.constraint(equalTo: stack.widthAnchor),
            header.heightAnchor.constraint(equalToConstant: 20),
            rows.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])
    }

    func show() {
        if case .imageFile(let file) = content {
            loading = true
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let image = ClipboardImageStore.imageData(named: file).flatMap { data -> CGImage? in
                    guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
                    return CGImageSourceCreateImageAtIndex(source, 0, nil)
                }
                DispatchQueue.main.async { [weak self] in
                    guard let self, !self.closed else { return }
                    self.loading = false
                    if let image { self.content = .image(image) } else { self.failed = true }
                    self.refresh()
                }
            }
        }
        refresh()
        let visible = parent?.screen?.visibleFrame ?? NSScreen.pointerVisibleFrame
        let origin = parent.map { NSPoint(x: $0.frame.maxX - panel.frame.width - 12, y: $0.frame.minY + 18) }
            ?? NSPoint(x: NSEvent.mouseLocation.x + 12, y: NSEvent.mouseLocation.y - panel.frame.height - 12)
        let x = min(max(origin.x, visible.minX + 8), visible.maxX - panel.frame.width - 8)
        let y = min(max(origin.y, visible.minY + 8), visible.maxY - panel.frame.height - 8)
        panel.setFrameOrigin(NSPoint(x: x, y: y))
        parent?.addChildWindow(panel, ordered: .above)
        if let parent {
            parentObserver = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification,
                object: parent, queue: .main) { [weak self] _ in self?.close(restoreFocus: false) }
        }
        if let monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown, handler: { [weak self] event in
            guard let self, event.window === self.panel else { return event }
            let modifiers = event.modifierFlags.intersection([.command, .shift, .option, .control])
            if event.keyCode == UInt16(kVK_Escape)
                || (!event.isARepeat && SharedActionShortcut.matches(event))
                || (modifiers == [.command] && event.charactersIgnoringModifiers?.lowercased() == "w") {
                self.close(restoreFocus: true); return nil
            }
            guard modifiers.isEmpty else { return event }
            switch Int(event.keyCode) {
            case kVK_DownArrow: self.move(1); return nil
            case kVK_UpArrow: self.move(-1); return nil
            case kVK_LeftArrow, kVK_RightArrow:
                guard self.shown.indices.contains(self.selected),
                      [.before, .after].contains(self.shown[self.selected]),
                      let side = self.shown.firstIndex(of: Int(event.keyCode) == kVK_LeftArrow ? .before : .after)
                else { return event }
                self.selected = side; self.updateSelection(); return nil
            case kVK_Return, kVK_ANSI_KeypadEnter: self.performSelection(); return nil
            default: return event
            }
        }) { monitors.append(monitor) }
        if let monitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown], handler: { [weak self] event in
            if let self, event.window !== self.panel { self.close(restoreFocus: false) }
            return event
        }) { monitors.append(monitor) }
        if let monitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown], handler: { [weak self] _ in
            self?.close(restoreFocus: false)
        }) { monitors.append(monitor) }
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(panel)
    }

    private func refresh() {
        rows.arrangedSubviews.forEach { rows.removeArrangedSubview($0); $0.removeFromSuperview() }
        buttons = []
        shown = SharedToolActions.actions(for: content)
        selected = min(selected, max(0, shown.count - 1))
        for (index, action) in shown.enumerated() {
            let button = SharedToolActionButton(title: action.title, target: self, action: #selector(clicked(_:)))
            button.tag = index
            button.alignment = .left; button.isBordered = false
            button.font = .systemFont(ofSize: 12, weight: .medium)
            button.isEnabled = !loading && !failed
            button.heightAnchor.constraint(equalToConstant: 32).isActive = true
            buttons.append(button)
        }
        var index = 0
        while index < buttons.count {
            let row: NSView
            if shown[index] == .before, index + 1 < shown.count, shown[index + 1] == .after {
                let separator = NSBox(); separator.boxType = .separator
                separator.widthAnchor.constraint(equalToConstant: 1).isActive = true
                separator.heightAnchor.constraint(equalToConstant: 12).isActive = true
                let pair = NSStackView(views: [buttons[index], separator, buttons[index + 1]])
                pair.orientation = .horizontal; pair.alignment = .centerY; pair.spacing = 4
                pair.distribution = .fill
                buttons[index].widthAnchor.constraint(equalTo: buttons[index + 1].widthAnchor).isActive = true
                row = pair; index += 2
            } else {
                row = buttons[index]; index += 1
            }
            rows.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: rows.widthAnchor).isActive = true
        }
        status.stringValue = loading ? SharedToolActionStrings.loading : failed ? SharedToolActionStrings.unavailable : ""
        status.isHidden = !loading && !failed
        // Loading feedback expands below the actions without moving the header.
        let rowCount = rows.arrangedSubviews.count
        let height = 52 + CGFloat(rowCount) * 32 + CGFloat(max(0, rowCount - 1)) * rows.spacing
            + (status.isHidden ? 0 : 22)
        var frame = panel.frame
        frame.origin.y += frame.height - height
        frame.size.height = height
        panel.setFrame(frame, display: true)

        updateSelection()
    }

    private func move(_ delta: Int) {
        guard !shown.isEmpty else { return }
        selected = (selected + delta + shown.count) % shown.count
        updateSelection()
    }
    private func updateSelection() {
        for (index, button) in buttons.enumerated() {
            button.menuSelected = index == selected
            button.setAccessibilitySelected(index == selected)
        }
    }
    @objc private func clicked(_ sender: NSButton) { selected = sender.tag; performSelection() }
    private func performSelection() {
        guard !closed, !loading, !failed, shown.indices.contains(selected) else { return }
        let action = shown[selected], snapshot = content
        close(restoreFocus: false)
        if action == .annotate, let onAnnotate {
            // A screenshot preview retains its existing source-bound edit behavior.
            if AppFeature.screenshot.isAvailable { onAnnotate() }
        } else { SharedToolActions.run(action, content: snapshot, title: title) }
    }
    func windowWillClose(_ notification: Notification) { close(restoreFocus: true) }

    func close(restoreFocus: Bool) {
        guard !closed else { return }
        closed = true
        monitors.forEach(NSEvent.removeMonitor); monitors = []
        if let parentObserver { NotificationCenter.default.removeObserver(parentObserver) }
        parentObserver = nil
        parent?.removeChildWindow(panel)
        panel.orderOut(nil)
        if restoreFocus, let parent, parent.isVisible {
            parent.makeKeyAndOrderFront(nil)
            parent.makeFirstResponder(previousResponder)
        }
        let callback = onClose; onClose = nil
        callback?()
    }
}
