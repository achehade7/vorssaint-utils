// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI
import Carbon.HIToolbox

extension TextTransform.Kind {
    var shortcut: String {
        switch self {
        case .joinLines: return "j"
        case .cleanSpacing: return "s"
        case .formatJSON: return "f"
        case .decodeURL: return "u"
        case .decodeBase64: return "b"
        }
    }
    var symbol: String {
        switch self {
        case .joinLines: return "arrow.triangle.merge"
        case .cleanSpacing: return "text.alignleft"
        case .formatJSON: return "curlybraces"
        case .decodeURL: return "link"
        case .decodeBase64: return "number"
        }
    }
}

/// A working copy of text, with the same controls in a tool window or the island.
final class TextTransformController: NSObject, NSWindowDelegate, NSTextViewDelegate {
    private static var openResults: [UUID: TextTransformController] = [:]
    private let id = UUID()
    private let panel: NSPanel
    private let embedded: Bool
    private let startsEditing: Bool
    private let previousApp = NSWorkspace.shared.frontmostApplication
    private let preview = NSTextView()
    private let status = NSTextField(labelWithString: SharedToolActionStrings.loading)
    private var copyButton: SharedToolActionButton!
    private var editButton: SharedToolActionButton!
    private var transformButtons: [SharedToolActionButton] = []
    private var choices: [TextTransform.Choice] = []
    private var revision = 0
    private var ready = false
    private var keyMonitor: Any?
    private var closed = false

    private init(editing: Bool, island: NSPanel? = nil) {
        startsEditing = editing
        embedded = island != nil
        panel = island ?? NSPanel(contentRect: NSRect(x: 0, y: 0, width: 640, height: 360),
                                 styleMask: [.titled, .closable, .resizable, .nonactivatingPanel],
                                 backing: .buffered, defer: false)
        super.init()
    }

    static func show(text: String, editing: Bool = false) {
        guard (editing ? AppFeature.screenOCR : .clipboardHistory).isAvailable else { return }
        let result = TextTransformController(editing: editing)
        openResults[result.id] = result
        result.present()
        result.receive(.success(text))
    }

    static func show(image: CGImage) {
        guard AppFeature.screenOCR.isAvailable else { return }
        let result = TextTransformController(editing: true)
        openResults[result.id] = result
        result.present()
        ScreenTextService.recognizeCaptureText(image) { [weak result] in result?.receive($0) }
    }

    static func showInIsland(text: String) {
        guard AppFeature.screenOCR.isAvailable, let panel = NotchService.shared.presentationWindow else { return }
        let result = TextTransformController(editing: true, island: panel)
        openResults[result.id] = result
        result.present()
        result.receive(.success(text))
    }

    private func button(title: String, symbol: String, shortcut: String, action: Selector) -> SharedToolActionButton {
        let button = SharedToolActionButton(title: title, target: self, action: action)
        button.isBordered = false
        button.imagePosition = .imageOnly
        button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: title)?
            .withSymbolConfiguration(.init(pointSize: 15, weight: .medium))
        button.contentTintColor = ToolAppearance.accent
        button.toolTip = title + " · " + shortcut
        button.setAccessibilityLabel(title)
        button.widthAnchor.constraint(equalToConstant: 32).isActive = true
        button.heightAnchor.constraint(equalToConstant: 32).isActive = true
        button.isEnabled = false
        return button
    }

    private func present() {
        let root = TextTransformBackground()
        preview.isRichText = false
        preview.isEditable = false
        preview.isSelectable = true
        preview.allowsUndo = true
        preview.isAutomaticQuoteSubstitutionEnabled = false
        preview.isAutomaticDashSubstitutionEnabled = false
        preview.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        preview.textColor = ToolAppearance.text
        preview.backgroundColor = ToolAppearance.surface
        preview.insertionPointColor = ToolAppearance.accent
        preview.textContainerInset = NSSize(width: 12, height: 10)
        preview.isVerticallyResizable = true
        preview.isHorizontallyResizable = false
        preview.autoresizingMask = [.width]
        preview.textContainer?.widthTracksTextView = true
        preview.delegate = self
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.documentView = preview
        transformButtons = TextTransform.Kind.allCases.enumerated().map { index, kind in
            let control = button(title: TextTransformStrings.title(for: kind), symbol: kind.symbol,
                                 shortcut: kind.shortcut.uppercased(), action: #selector(transform(_:)))
            control.tag = index
            return control
        }
        editButton = button(title: TextTransformStrings.edit, symbol: "pencil", shortcut: "⌘E", action: #selector(editText))
        copyButton = button(title: FeatureStrings.clipboard(L10n.shared.language).copy, symbol: "doc.on.doc",
                            shortcut: "⌘C", action: #selector(copyText))
        let toolbar = NSStackView(views: transformButtons + [editButton!, copyButton!])
        toolbar.orientation = .horizontal; toolbar.alignment = .centerY; toolbar.spacing = 4
        status.font = .systemFont(ofSize: 11)
        status.textColor = ToolAppearance.secondaryText
        status.lineBreakMode = .byTruncatingTail
        for view in [toolbar, scroll, status] {
            root.addSubview(view); view.translatesAutoresizingMaskIntoConstraints = false
        }
        NSLayoutConstraint.activate([
            toolbar.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 10),
            toolbar.topAnchor.constraint(equalTo: root.topAnchor, constant: 4),
            toolbar.heightAnchor.constraint(equalToConstant: 32),
            toolbar.trailingAnchor.constraint(lessThanOrEqualTo: root.trailingAnchor, constant: -10),
            scroll.topAnchor.constraint(equalTo: toolbar.bottomAnchor, constant: 8),
            scroll.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 10),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -10),
            scroll.bottomAnchor.constraint(equalTo: status.topAnchor, constant: -6),
            status.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 12),
            status.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -12),
            status.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -6)
        ])
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self, !self.closed, event.window === self.panel,
                  self.panel.attachedSheet == nil, !self.preview.hasMarkedText(),
                  !self.embedded || NotchService.shared.isCaptureVisible(id: self.id) else { return event }
            let modifiers = event.modifierFlags.intersection([.command, .option, .control, .shift])
            let key = event.charactersIgnoringModifiers?.lowercased()
            if modifiers == .command, let key, ["c", "e"].contains(key) {
                if !event.isARepeat {
                    if key == "c" { self.copyText() } else { self.editText() }
                }
                return nil
            }
            if !self.preview.isEditable || !(self.panel.firstResponder is NSTextView) {
                if modifiers.isEmpty, let key,
                   let index = TextTransform.Kind.allCases.firstIndex(where: { $0.shortcut == key }) {
                    if !event.isARepeat { self.transform(self.transformButtons[index]) }
                    return nil
                }
                if modifiers == .command, key == "z" {
                    if !event.isARepeat {
                        self.preview.undoManager?.undo()
                        self.refreshChoices()
                    }
                    return nil
                }
            }
            guard !event.isARepeat else { return event }
            if modifiers.isEmpty, event.keyCode == kVK_Return || event.keyCode == kVK_ANSI_KeypadEnter {
                if self.copyResult(useSelection: false) { self.close() }
                return nil
            }
            if (event.keyCode == kVK_Escape && modifiers.isEmpty)
                || (event.keyCode == kVK_ANSI_W && modifiers == .command) {
                self.close(); return nil
            }
            return event
        }
        if embedded {
            root.didAttach = { [weak self] in self?.focusTextIfReady() }
            root.didDetach = { [weak self] in self?.close(restoreFocus: false) }
            let shown = NotchService.shared.presentCapture(id: id,
                content: AnyView(TextTransformContent(view: root).frame(height: 260)), height: 260,
                takeFocus: true, closeOnCollapse: true,
                fallback: { [weak self] in self?.close() }, close: { [weak self] in self?.close() }, hover: { _ in })
            if !shown { close() }
        } else {
            panel.title = startsEditing ? SharedToolActionStrings.extract : TextTransformStrings.title
            panel.isReleasedWhenClosed = false
            panel.delegate = self
            panel.level = .floating
            panel.hidesOnDeactivate = false
            panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
            panel.minSize = NSSize(width: 360, height: 240)
            ToolAppearance.configure(panel)
            panel.contentView = root
            panel.center()
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    private func receive(_ result: Result<String, Error>) {
        guard !closed else { return }
        switch result {
        case .success(let text):
            guard text.utf8.count <= TextTransform.maxBytes else { status.stringValue = TextTransformStrings.tooLarge; return }
            preview.string = text
            preview.isEditable = startsEditing
            preview.undoManager?.removeAllActions()
            ready = true
            editButton.isEnabled = true
            editButton.menuSelected = startsEditing
            refreshChoices()
            focusTextIfReady()
        case .failure: status.stringValue = L10n.shared.s.ocrNoText
        }
    }

    private func focusTextIfReady() {
        guard !closed, ready, preview.window === panel else { return }
        panel.makeFirstResponder(preview.isEditable ? preview : panel)
    }

    func textDidChange(_ notification: Notification) { refreshChoices() }

    private func refreshChoices() {
        revision += 1
        let request = revision, source = preview.string
        choices = []
        transformButtons.forEach { $0.isEnabled = false }
        copyButton.isEnabled = ready && !source.isEmpty
        status.stringValue = source.utf8.count > TextTransform.maxBytes ? TextTransformStrings.tooLarge
            : preview.isEditable ? "" : TextTransformStrings.hint
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let choices = TextTransform.choices(for: source)
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.closed, self.revision == request else { return }
                self.choices = choices
                for button in self.transformButtons {
                    button.isEnabled = choices.contains { $0.kind == TextTransform.Kind.allCases[button.tag] }
                }
            }
        }
    }

    @objc private func transform(_ sender: NSButton) {
        guard !closed, sender.isEnabled, TextTransform.Kind.allCases.indices.contains(sender.tag),
              let choice = choices.first(where: { $0.kind == TextTransform.Kind.allCases[sender.tag] }) else { return }
        let editing = preview.isEditable
        preview.isEditable = true
        preview.breakUndoCoalescing()
        preview.insertText(choice.text, replacementRange: NSRange(location: 0, length: (preview.string as NSString).length))
        preview.breakUndoCoalescing()
        preview.isEditable = editing
        preview.setSelectedRange(NSRange(location: 0, length: 0))
        preview.scrollRangeToVisible(NSRange(location: 0, length: 0))
        panel.makeFirstResponder(panel)
    }

    @objc private func editText() {
        guard !closed, editButton.isEnabled else { return }
        preview.breakUndoCoalescing()
        preview.isEditable.toggle()
        editButton.menuSelected = preview.isEditable
        status.stringValue = preview.string.utf8.count > TextTransform.maxBytes ? TextTransformStrings.tooLarge
            : preview.isEditable ? "" : TextTransformStrings.hint
        panel.makeFirstResponder(preview.isEditable ? preview : panel)
    }

    @objc private func copyText() {
        if copyResult(useSelection: true) { close() }
    }

    private func copyResult(useSelection: Bool) -> Bool {
        guard !closed, copyButton.isEnabled else { return false }
        let source = preview.string as NSString, range = preview.selectedRange()
        let text = useSelection && range.length > 0 && range.location != NSNotFound && NSMaxRange(range) <= source.length
            ? source.substring(with: range) : preview.string
        NSPasteboard.general.clearContents()
        return NSPasteboard.general.setString(text, forType: .string)
    }

    private func close(restoreFocus: Bool = true) {
        guard !closed else { return }
        if embedded {
            finish(restoreFocus: restoreFocus)
            NotchService.shared.removeCapture(id: id)
        } else { panel.close() }
    }

    private func finish(restoreFocus: Bool = true) {
        guard !closed else { return }
        let restore = restoreFocus && panel.isKeyWindow
            && NSWorkspace.shared.frontmostApplication?.processIdentifier == ProcessInfo.processInfo.processIdentifier
        closed = true
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor); self.keyMonitor = nil }
        Self.openResults[id] = nil
        if restore, let previousApp, previousApp.processIdentifier != ProcessInfo.processInfo.processIdentifier {
            previousApp.activate(options: [])
        }
    }

    func windowWillClose(_ notification: Notification) { finish() }
}

private struct TextTransformContent: NSViewRepresentable {
    let view: NSView
    func makeNSView(context: Context) -> NSView { view }
    func updateNSView(_ nsView: NSView, context: Context) {}
}

private final class TextTransformBackground: NSView {
    var didAttach: (() -> Void)?
    var didDetach: (() -> Void)?
    private var attached = false
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        if window != nil {
            attached = true
            didAttach?()
        } else if attached {
            // Allow a synchronous reparent before treating removal as dismissal.
            // Keep the callback even if the detached view is released first.
            let onDetach = didDetach
            DispatchQueue.main.async { [weak self] in
                guard self?.window == nil else { return }
                onDetach?()
            }
        }
    }
    override func draw(_ dirtyRect: NSRect) {
        ToolAppearance.background.setFill()
        dirtyRect.intersection(bounds).fill()
    }
}
