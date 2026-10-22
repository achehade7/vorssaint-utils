// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

final class ClipboardDiffService: NSObject, NSWindowDelegate, NSTextViewDelegate {
    static let shared = ClipboardDiffService()
    private var panel: NSPanel?
    private var calculation: Task<Void, Never>?
    private var beforeText: NSTextView?
    private var afterText: NSTextView?
    private var resultText: NSTextView?
    private var legend: NSTextField?

    func show() {
        guard AppFeature.clipboardHistory.isAvailable else { return }
        panel?.close()
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        let pair = ClipboardDiff.latestPair(in: ClipboardHistoryService.shared.entries)
        let panel = ClipboardDiffPanel(contentRect: NSRect(x: 0, y: 0, width: 900, height: 660),
                                      styleMask: [.titled, .closable, .resizable, .nonactivatingPanel],
                                      backing: .buffered, defer: false)
        panel.title = strings.title
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 540, height: 420)
        panel.delegate = self

        let content = NSView()
        let beforeLabel = NSTextField(labelWithString: strings.before)
        let afterLabel = NSTextField(labelWithString: strings.after)
        let (beforeScroll, beforeText) = Self.textArea(label: strings.before, editable: true)
        let (afterScroll, afterText) = Self.textArea(label: strings.after, editable: true)
        let (resultScroll, resultText) = Self.textArea(label: strings.title, editable: false)
        let legend = NSTextField(labelWithString: strings.legend)
        for view in [beforeLabel, afterLabel, beforeScroll, afterScroll, legend, resultScroll] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            beforeLabel.topAnchor.constraint(equalTo: content.topAnchor, constant: 12),
            beforeLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            afterLabel.topAnchor.constraint(equalTo: beforeLabel.topAnchor),
            afterLabel.leadingAnchor.constraint(equalTo: afterScroll.leadingAnchor),
            beforeScroll.topAnchor.constraint(equalTo: beforeLabel.bottomAnchor, constant: 8),
            beforeScroll.leadingAnchor.constraint(equalTo: beforeLabel.leadingAnchor),
            beforeScroll.heightAnchor.constraint(equalTo: content.heightAnchor, multiplier: 0.35),
            beforeScroll.widthAnchor.constraint(equalTo: afterScroll.widthAnchor),
            afterScroll.leadingAnchor.constraint(equalTo: beforeScroll.trailingAnchor, constant: 12),
            afterScroll.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            afterScroll.topAnchor.constraint(equalTo: beforeScroll.topAnchor),
            afterScroll.bottomAnchor.constraint(equalTo: beforeScroll.bottomAnchor),
            legend.topAnchor.constraint(equalTo: beforeScroll.bottomAnchor, constant: 12),
            legend.leadingAnchor.constraint(equalTo: beforeLabel.leadingAnchor),
            legend.trailingAnchor.constraint(equalTo: afterScroll.trailingAnchor),
            resultScroll.topAnchor.constraint(equalTo: legend.bottomAnchor, constant: 12),
            resultScroll.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            resultScroll.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            resultScroll.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])
        panel.contentView = content
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(NSEvent.mouseLocation) }) ?? NSScreen.main {
            let frame = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: frame.midX - panel.frame.width / 2, y: frame.midY - panel.frame.height / 2))
        }
        self.panel = panel
        self.beforeText = beforeText; self.afterText = afterText
        self.resultText = resultText; self.legend = legend
        beforeText.string = pair?.older ?? ""
        afterText.string = pair?.newer ?? ""
        beforeText.delegate = self; afterText.delegate = self
        resultText.string = pair == nil ? strings.missing : strings.loading
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(beforeText)
        for text in [beforeText, afterText, resultText] { text.sizeToFit() }
        if pair != nil { refreshComparison() }
    }

    private static func textArea(label: String, editable: Bool) -> (NSScrollView, NSTextView) {
        let scroll = NSScrollView()
        scroll.borderType = .bezelBorder
        scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = true
        let text = ClipboardDiffTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 200))
        text.isEditable = editable; text.isSelectable = true; text.isRichText = false
        text.isAutomaticLinkDetectionEnabled = false
        text.isAutomaticQuoteSubstitutionEnabled = false
        text.isAutomaticDashSubstitutionEnabled = false
        text.isAutomaticTextReplacementEnabled = false
        text.isAutomaticSpellingCorrectionEnabled = false
        text.isContinuousSpellCheckingEnabled = false
        text.smartInsertDeleteEnabled = false
        text.allowsUndo = editable
        text.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        text.textContainerInset = NSSize(width: 12, height: 10)
        text.isHorizontallyResizable = true; text.isVerticallyResizable = true
        text.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        text.textContainer?.containerSize = text.maxSize
        text.textContainer?.widthTracksTextView = false
        text.setAccessibilityLabel(label)
        scroll.documentView = text
        return (scroll, text)
    }

    func textDidChange(_ notification: Notification) { refreshComparison() }

    private func refreshComparison() {
        guard let panel, let beforeText, let afterText, let resultText, let legend else { return }
        calculation?.cancel()
        let strings = ClipboardDiffStrings.localized(L10n.shared.language)
        let pair = ClipboardDiff.Pair(older: beforeText.string, newer: afterText.string)
        // Debounce edits and compare off the UI thread. Edits stay in these
        // fields; nothing is written to clipboard history or the disk.
        calculation = Task { @MainActor [weak self, weak panel] in
            do { try await Task.sleep(nanoseconds: 150_000_000) } catch { return }
            let result = await Task.detached(priority: .userInitiated) { Result { try ClipboardDiff.lines(for: pair) } }.value
            guard !Task.isCancelled, let self, let panel, self.panel === panel else { return }
            legend.stringValue = strings.legend
            switch result {
            case .success(let lines):
                let rendered = NSMutableAttributedString(string: "")
                if lines.allSatisfy({ $0.kind == .same }) { legend.stringValue = strings.identical }
                for line in lines {
                    let color: NSColor = line.kind == .removed ? .systemRed : line.kind == .added ? .systemGreen : .textColor
                    var attributes: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: 13, weight: .regular), .foregroundColor: color]
                    if line.kind != .same { attributes[.backgroundColor] = color.withAlphaComponent(0.12) }
                    rendered.append(NSAttributedString(string: line.prefix + line.text.replacingOccurrences(of: "\r", with: "␍") + "\n", attributes: attributes))
                }
                resultText.textStorage?.setAttributedString(rendered)
            case .failure: resultText.string = strings.tooLarge
            }
            resultText.sizeToFit()
            self.calculation = nil
        }
    }

    func windowWillClose(_ notification: Notification) {
        calculation?.cancel(); calculation = nil
        beforeText = nil; afterText = nil; resultText = nil; legend = nil
        panel?.contentView = nil
        panel = nil
    }
}

private final class ClipboardDiffPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { close() }
}

private final class ClipboardDiffTextView: NSTextView {
    override func cancelOperation(_ sender: Any?) { window?.close() }
}
