// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// TextKit owns editing, selection and undo. Alignment changes only its layout
/// cache; highlighting uses temporary attributes, never the editable storage.
final class ClipboardDiffLayoutManager: NSLayoutManager, NSLayoutManagerDelegate {
    static let rowHeight: CGFloat = 24
    var starts = [0]
    var alignedRows = [0]

    override init() { super.init(); delegate = self }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func sourceLine(at offset: Int) -> Int {
        var low = 0, high = starts.count
        while low + 1 < high {
            let middle = (low + high) / 2
            if starts[middle] <= offset { low = middle } else { high = middle }
        }
        return low
    }

    private func y(at offset: Int) -> CGFloat {
        let line = sourceLine(at: offset)
        return CGFloat(alignedRows.indices.contains(line) ? alignedRows[line] : line) * Self.rowHeight
    }

    override func setLineFragmentRect(_ fragmentRect: NSRect, forGlyphRange glyphRange: NSRange, usedRect: NSRect) {
        var fragment = fragmentRect, used = usedRect
        fragment.origin.y = y(at: characterIndexForGlyph(at: glyphRange.location))
        used.origin.y = fragment.origin.y
        fragment.size.height = Self.rowHeight
        used.size.height = Self.rowHeight
        super.setLineFragmentRect(fragment, forGlyphRange: glyphRange, usedRect: used)
    }

    override func setExtraLineFragmentRect(_ fragmentRect: NSRect, usedRect: NSRect, textContainer: NSTextContainer) {
        var fragment = fragmentRect, used = usedRect
        fragment.origin.y = y(at: textStorage?.length ?? 0)
        used.origin.y = fragment.origin.y
        fragment.size.height = Self.rowHeight
        used.size.height = Self.rowHeight
        super.setExtraLineFragmentRect(fragment, usedRect: used, textContainer: textContainer)
    }

    func layoutManager(_ layoutManager: NSLayoutManager, shouldUse action: NSLayoutManager.ControlCharacterAction,
                       forControlCharacterAt charIndex: Int) -> NSLayoutManager.ControlCharacterAction {
        guard let text = textStorage?.string as NSString?, charIndex < text.length else { return action }
        let unit = text.character(at: charIndex)
        // LF defines comparison rows. Keep other separators in their source row;
        // CRLF remains a native hard break. No source characters are rewritten.
        if unit == 0x2028 || unit == 0x2029 || (unit == 13 && (charIndex + 1 == text.length || text.character(at: charIndex + 1) != 10)) {
            return .whitespace
        }
        return action
    }

    func layoutManager(_ layoutManager: NSLayoutManager, shouldUseTemporaryAttributes attrs: [NSAttributedString.Key: Any],
                       forDrawingToScreen toScreen: Bool, atCharacterIndex charIndex: Int,
                       effectiveRange: NSRangePointer?) -> [NSAttributedString.Key: Any]? { attrs }
}

final class ClipboardDiffTextView: NSTextView {
    let isBefore: Bool
    private(set) var diffRows: [ClipboardDiff.Row] = []
    private(set) var presentationCurrent = false
    var placeholder = ""
    weak var gutter: ClipboardDiffGutter?
    var selectedChange: Range<Int>? { didSet { needsDisplay = true; gutter?.needsDisplay = true } }
    var diffLayout: ClipboardDiffLayoutManager { layoutManager as! ClipboardDiffLayoutManager }
    var changeColor: NSColor { isBefore ? .systemOrange : .systemBlue }

    init(isBefore: Bool, label: String) {
        self.isBefore = isBefore
        let storage = NSTextStorage()
        let layout = ClipboardDiffLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 10_000_000, height: CGFloat.greatestFiniteMagnitude))
        storage.addLayoutManager(layout)
        layout.addTextContainer(container)
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 300), textContainer: container)
        clipsToBounds = true
        isEditable = true; isSelectable = true; isRichText = false; allowsUndo = true
        isAutomaticLinkDetectionEnabled = false
        isAutomaticQuoteSubstitutionEnabled = false
        isAutomaticDashSubstitutionEnabled = false
        isAutomaticTextReplacementEnabled = false
        isAutomaticSpellingCorrectionEnabled = false
        isContinuousSpellCheckingEnabled = false
        smartInsertDeleteEnabled = false
        usesFindPanel = true
        font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        textColor = .textColor; backgroundColor = .textBackgroundColor
        insertionPointColor = .textColor
        let paragraph = NSMutableParagraphStyle()
        paragraph.minimumLineHeight = ClipboardDiffLayoutManager.rowHeight
        paragraph.maximumLineHeight = ClipboardDiffLayoutManager.rowHeight
        paragraph.defaultTabInterval = 4 * (" " as NSString).size(withAttributes: [.font: font!]).width
        paragraph.tabStops = []
        defaultParagraphStyle = paragraph
        typingAttributes = [.font: font!, .foregroundColor: NSColor.textColor, .paragraphStyle: paragraph]
        textContainerInset = NSSize(width: 12, height: 16)
        isHorizontallyResizable = true; isVerticallyResizable = true
        maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        container.widthTracksTextView = false
        container.lineFragmentPadding = 0
        setAccessibilityLabel(label)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func cancelOperation(_ sender: Any?) { window?.close() }
    func rowY(_ row: Int) -> CGFloat { textContainerOrigin.y + CGFloat(row) * ClipboardDiffLayoutManager.rowHeight }
    func source(in row: ClipboardDiff.Row) -> ClipboardDiff.SourceLine? { isBefore ? row.before : row.after }

    // Native rulers overlay the clip view. At the left edge its document rect
    // starts at -ruleThickness, even though contentInsets reports zero.
    var viewportOrigin: NSPoint {
        guard let scroll = enclosingScrollView else { return .zero }
        let rect = scroll.documentVisibleRect
        return NSPoint(x: max(0, rect.minX + (gutter?.ruleThickness ?? 0)), y: max(0, rect.minY))
    }
    func scrollToContent(_ point: NSPoint) {
        scroll(NSPoint(x: point.x - (gutter?.ruleThickness ?? 0), y: point.y))
    }

    func invalidateComparison() {
        presentationCurrent = false
        selectedChange = nil
        layoutManager?.removeTemporaryAttribute(.backgroundColor, forCharacterRange: NSRange(location: 0, length: (string as NSString).length))
        layoutManager?.removeTemporaryAttribute(.underlineStyle, forCharacterRange: NSRange(location: 0, length: (string as NSString).length))
        let starts = [0] + string.utf16.enumerated().compactMap { $0.element == 10 ? $0.offset + 1 : nil }
        let geometryChanged = starts != diffLayout.starts || (string.isEmpty && diffLayout.alignedRows != [0])
        if starts.count != diffLayout.starts.count || string.isEmpty { diffLayout.alignedRows = Array(starts.indices); diffRows = [] }
        diffLayout.starts = starts
        if geometryChanged { invalidateGeometry() }
        else { needsDisplay = true; gutter?.needsDisplay = true }
    }

    func apply(_ comparison: ClipboardDiff.Comparison) {
        diffRows = comparison.rows
        presentationCurrent = true
        var starts: [Int] = [], aligned: [Int] = []
        for (index, row) in diffRows.enumerated() {
            guard let line = source(in: row) else { continue }
            starts.append(line.range.location); aligned.append(index)
        }
        diffLayout.starts = starts.isEmpty ? [0] : starts
        diffLayout.alignedRows = aligned.isEmpty ? [0] : aligned
        refreshHighlights()
        invalidateGeometry()
    }

    private func refreshHighlights() {
        let whole = NSRange(location: 0, length: (string as NSString).length)
        diffLayout.removeTemporaryAttribute(.backgroundColor, forCharacterRange: whole)
        diffLayout.removeTemporaryAttribute(.underlineStyle, forCharacterRange: whole)
        guard presentationCurrent else { return }
        for row in diffRows {
            guard let line = source(in: row) else { continue }
            for range in line.changedRanges where range.length > 0 {
                diffLayout.addTemporaryAttribute(.backgroundColor, value: changeColor.withAlphaComponent(0.28), forCharacterRange: range)
                // AppKit underlines every glyph, including far offscreen ones.
                // Large replacements retain the strong fill and +/- gutter;
                // reserve the additional underline for precise, smaller edits.
                if range.length <= 1024 {
                    diffLayout.addTemporaryAttribute(.underlineStyle, value: NSUnderlineStyle.single.rawValue, forCharacterRange: range)
                }
            }
        }
    }

    private func invalidateGeometry() {
        diffLayout.invalidateLayout(forCharacterRange: NSRange(location: 0, length: (string as NSString).length), actualCharacterRange: nil)
        needsDisplay = true; gutter?.needsDisplay = true
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshHighlights()
        needsDisplay = true; gutter?.needsDisplay = true
    }

    override func drawBackground(in rect: NSRect) {
        super.drawBackground(in: rect)
        guard presentationCurrent else { return }
        let height = ClipboardDiffLayoutManager.rowHeight
        let first = max(0, Int((rect.minY - textContainerOrigin.y) / height))
        let last = min(diffRows.count, Int(ceil((rect.maxY - textContainerOrigin.y) / height)))
        guard first < last else { return }
        for index in first..<last {
            let row = diffRows[index]
            let band = NSRect(x: rect.minX, y: rowY(index), width: rect.width, height: height)
            if source(in: row) == nil {
                NSColor.quaternaryLabelColor.withAlphaComponent(0.12).setFill(); band.fill()
                let path = NSBezierPath()
                path.setLineDash([2, 4], count: 2, phase: 0)
                path.move(to: NSPoint(x: band.minX, y: band.midY)); path.line(to: NSPoint(x: band.maxX, y: band.midY))
                NSColor.separatorColor.setStroke(); path.stroke()
            } else if row.kind != .same {
                changeColor.withAlphaComponent(0.09).setFill(); band.fill()
            }
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        if string.isEmpty && !presentationCurrent {
            (placeholder as NSString).draw(at: NSPoint(x: textContainerOrigin.x, y: textContainerOrigin.y + 4),
                                          withAttributes: [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: NSColor.placeholderTextColor])
        }
        guard presentationCurrent, let container = textContainer else { return }
        // Visible symbols reveal changed spaces, tabs and line endings; these
        // marks are drawing only, so copying always returns the original text.
        for (index, row) in diffRows.enumerated() where rowY(index) + 24 >= dirtyRect.minY && rowY(index) <= dirtyRect.maxY {
            guard let line = source(in: row) else { continue }
            let local = line.text as NSString
            let whitespace = CharacterSet(charactersIn: " \t\r")
            let needsSymbols = line.changedRanges.contains { range in
                range.length > 0 && local.rangeOfCharacter(from: whitespace, options: [],
                    range: NSRange(location: range.location - line.range.location, length: range.length)).location != NSNotFound
            }
            var visible = NSRange(location: 0, length: 0)
            if needsSymbols {
                let y = CGFloat(index) * ClipboardDiffLayoutManager.rowHeight + 12
                let left = diffLayout.characterIndex(for: NSPoint(x: max(0, dirtyRect.minX - textContainerOrigin.x), y: y),
                                                    in: container, fractionOfDistanceBetweenInsertionPoints: nil)
                let right = diffLayout.characterIndex(for: NSPoint(x: dirtyRect.maxX - textContainerOrigin.x, y: y),
                                                     in: container, fractionOfDistanceBetweenInsertionPoints: nil)
                visible = NSRange(location: min(left, right), length: abs(right - left) + 1)
            }
            for range in line.changedRanges {
                if range.length == 0 {
                    let x = insertionX(at: range.location)
                    changeColor.setFill()
                    NSRect(x: x, y: rowY(index) + 4, width: 2, height: 16).fill()
                } else if needsSymbols {
                    let text = string as NSString
                    let visibleChange = NSIntersectionRange(range, visible)
                    for offset in visibleChange.location..<NSMaxRange(visibleChange) {
                        let unit = text.character(at: offset)
                        let symbol: String
                        switch unit { case 9: symbol = "⇥"; case 32: symbol = "·"; case 13: symbol = "↵"; default: continue }
                        let glyph = diffLayout.glyphIndexForCharacter(at: offset)
                        let x = diffLayout.location(forGlyphAt: glyph).x
                        (symbol as NSString).draw(at: NSPoint(x: x + textContainerOrigin.x, y: rowY(index) + 4),
                                                 withAttributes: [.font: font!, .foregroundColor: NSColor.secondaryLabelColor])
                    }
                }
            }
        }
    }

    private func insertionX(at offset: Int) -> CGFloat {
        guard let container = textContainer else { return textContainerOrigin.x }
        if offset < (string as NSString).length {
            let glyph = diffLayout.glyphIndexForCharacter(at: offset)
            return diffLayout.location(forGlyphAt: glyph).x + textContainerOrigin.x
        }
        if diffLayout.extraLineFragmentTextContainer != nil { return textContainerOrigin.x }
        guard diffLayout.numberOfGlyphs > 0 else { return textContainerOrigin.x }
        return diffLayout.boundingRect(forGlyphRange: NSRange(location: diffLayout.numberOfGlyphs - 1, length: 1), in: container).maxX + textContainerOrigin.x
    }
}

final class ClipboardDiffGutter: NSRulerView {
    weak var editor: ClipboardDiffTextView?
    init(scroll: NSScrollView, editor: ClipboardDiffTextView) {
        self.editor = editor
        super.init(scrollView: scroll, orientation: .verticalRuler)
        clipsToBounds = true
        clientView = editor
        ruleThickness = 58
    }
    required init(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func drawHashMarksAndLabels(in rect: NSRect) {
        NSColor.textBackgroundColor.setFill(); bounds.fill()
        guard let editor else { return }
        let count = editor.presentationCurrent ? editor.diffRows.count : editor.diffLayout.starts.count
        for index in 0..<count {
            let displayRow = editor.presentationCurrent ? index : editor.diffLayout.alignedRows[index]
            let y = convert(NSPoint(x: 0, y: editor.rowY(displayRow)), from: editor).y
            guard y + 24 >= rect.minY, y <= rect.maxY else { continue }
            let row = editor.presentationCurrent ? editor.diffRows[index] : nil
            let source = row.flatMap { editor.source(in: $0) }
            let number = row == nil ? String(index + 1) : source.map { String($0.number) } ?? "–"
            let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .regular), .foregroundColor: NSColor.secondaryLabelColor]
            let width = (number as NSString).size(withAttributes: attributes).width
            (number as NSString).draw(at: NSPoint(x: 39 - width, y: y + 5), withAttributes: attributes)
            if let row, row.kind != .same, source != nil {
                // Simple geometric signs avoid CoreText's marker-font path,
                // which can fail during a nested native button redraw.
                let marker = NSBezierPath()
                marker.lineWidth = 1.4
                marker.move(to: NSPoint(x: 44, y: y + 12)); marker.line(to: NSPoint(x: 51, y: y + 12))
                if !editor.isBefore {
                    marker.move(to: NSPoint(x: 47.5, y: y + 8.5)); marker.line(to: NSPoint(x: 47.5, y: y + 15.5))
                }
                editor.changeColor.setStroke(); marker.stroke()
            }
            if editor.selectedChange?.contains(index) == true {
                editor.changeColor.setFill(); NSRect(x: 2, y: y + 2, width: 3, height: 20).fill()
            }
        }
    }
}
