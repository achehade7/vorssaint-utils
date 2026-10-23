// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// OCR from a shared action is an editable result, with Copy as an explicit action.
final class ExtractedTextController: NSObject, NSWindowDelegate, NSTextViewDelegate {
    private static var openResults: [UUID: ExtractedTextController] = [:]
    private let id = UUID()
    private let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 640, height: 440),
                               styleMask: [.titled, .closable, .resizable, .nonactivatingPanel],
                               backing: .buffered, defer: false)
    private let editor = NSTextView()
    private let status = NSTextField(labelWithString: SharedToolActionStrings.loading)
    private var copyButton: NSButton!
    private var snippetButton: NSButton!
    private var actionsButton: NSButton!
    private let actionsOwner = UUID()
    private var keyMonitor: Any?
    private var closed = false
    private var ready = false

    static func show(image: CGImage) {
        let result = ExtractedTextController()
        openResults[result.id] = result
        result.present(image: image)
    }

    private func present(image: CGImage) {
        panel.title = SharedToolActionStrings.extract
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 400, height: 260)
        ToolAppearance.configure(panel)
        let root = ExtractedTextBackground()
        panel.contentView = root
        editor.isRichText = false
        editor.allowsUndo = true
        editor.isEditable = false
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false
        editor.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        editor.textColor = ToolAppearance.text
        editor.backgroundColor = ToolAppearance.surface
        editor.insertionPointColor = ToolAppearance.accent
        editor.textContainerInset = NSSize(width: 14, height: 14)
        editor.isVerticallyResizable = true
        editor.isHorizontallyResizable = false
        editor.autoresizingMask = [.width]
        editor.textContainer?.widthTracksTextView = true
        editor.delegate = self
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.documentView = editor
        copyButton = NSButton(title: FeatureStrings.clipboard(L10n.shared.language).copy,
                              target: self, action: #selector(copyText))
        snippetButton = NSButton(title: SnippetCaptureStrings.localized(L10n.shared.language).save,
                                 target: self, action: #selector(saveSnippet))
        actionsButton = NSButton(title: SharedToolActionStrings.actions + "  " + SharedActionShortcut.displayString,
                                 target: self, action: #selector(showActions))
        [actionsButton!, copyButton!, snippetButton!].forEach { ToolAppearance.style($0) }
        snippetButton.isHidden = !AppFeature.textSnippets.isAvailable
        let buttons = NSStackView(views: [actionsButton, snippetButton, copyButton])
        buttons.spacing = 8
        status.font = .systemFont(ofSize: 11)
        status.textColor = ToolAppearance.secondaryText
        status.lineBreakMode = .byTruncatingTail
        for view in [scroll, status, buttons] {
            root.addSubview(view); view.translatesAutoresizingMaskIntoConstraints = false
        }
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: root.topAnchor, constant: 12),
            scroll.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 12),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -12),
            scroll.bottomAnchor.constraint(equalTo: buttons.topAnchor, constant: -12),
            buttons.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -12),
            buttons.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -12),
            status.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 14),
            status.trailingAnchor.constraint(lessThanOrEqualTo: buttons.leadingAnchor, constant: -12),
            status.centerYAnchor.constraint(equalTo: buttons.centerYAnchor)
        ])
        updateButtons()
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self, !self.closed, event.window === self.panel,
                  self.panel.attachedSheet == nil else { return event }
            if let editor = self.panel.firstResponder as? NSTextView, editor.hasMarkedText() { return event }
            if !event.isARepeat, self.ready,
               SharedActionShortcut.matches(event) {
                self.showActions(); return nil
            }
            return event
        }
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        ScreenTextService.recognizeCaptureText(image) { [weak self] result in
            guard let self, !self.closed else { return }
            switch result {
            case .success(let text):
                self.editor.string = text
                self.editor.isEditable = true
                self.editor.undoManager?.removeAllActions()
                self.status.stringValue = ""
                self.ready = true
                self.panel.makeFirstResponder(self.editor)
            case .failure:
                self.status.stringValue = L10n.shared.s.ocrNoText
            }
            self.updateButtons()
        }
    }

    func textDidChange(_ notification: Notification) { updateButtons() }
    private func updateButtons() {
        let hasText = ready && !editor.string.isEmpty
        actionsButton.isEnabled = hasText
        copyButton.isEnabled = hasText
        snippetButton.isEnabled = hasText && AppFeature.textSnippets.isAvailable
    }
    @objc private func showActions() {
        guard ready, !closed, !editor.string.isEmpty, panel.attachedSheet == nil else { return }
        let source = editor.string as NSString, range = editor.selectedRange()
        let snapshot = range.length > 0 && range.location != NSNotFound && NSMaxRange(range) <= source.length
            ? source.substring(with: range) : editor.string
        SharedToolActions.present(content: .text(snapshot), title: SharedToolActionStrings.extract,
                                  from: panel, owner: actionsOwner)
    }
    @objc private func copyText() {
        guard ready, !editor.string.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(editor.string, forType: .string)
        status.stringValue = L10n.shared.s.ocrCopied
    }
    @objc private func saveSnippet() {
        guard ready, !editor.string.isEmpty, AppFeature.textSnippets.isAvailable else { return }
        SnippetLibraryService.shared.saveCapturedText(editor.string)
    }
    func windowWillClose(_ notification: Notification) {
        closed = true
        SharedToolActions.cancel(owner: actionsOwner)
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor); self.keyMonitor = nil }
        Self.openResults[id] = nil
    }
}

private final class ExtractedTextBackground: NSView {
    override func draw(_ dirtyRect: NSRect) {
        ToolAppearance.background.setFill()
        dirtyRect.intersection(bounds).fill()
    }
}
