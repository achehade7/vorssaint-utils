// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI

final class ScreenCompareBackground: NSView {
    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        bounds.fill()
    }
}

final class ScreenComparePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { close() }
}

final class ScreenCompareSourceView: NSView {
    let detail = NSTextField(labelWithString: "—")
    let capture: NSButton
    let open: NSButton
    var onDrop: ((URL) -> Void)?
    private let accent: NSColor
    private var isDropping = false { didSet { needsDisplay = true } }

    init(title: String, captureTitle: String, openTitle: String, accent: NSColor) {
        self.accent = accent
        capture = NSButton(title: captureTitle, target: nil, action: nil)
        open = NSButton(image: NSImage(systemSymbolName: "folder", accessibilityDescription: openTitle)!, target: nil, action: nil)
        super.init(frame: .zero)
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 12, weight: .semibold)
        label.textColor = accent
        detail.font = .monospacedDigitSystemFont(ofSize: 10, weight: .regular)
        detail.textColor = .secondaryLabelColor
        detail.lineBreakMode = .byTruncatingMiddle
        detail.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        for button in [capture, open] { button.bezelStyle = .texturedRounded; button.controlSize = .small }
        open.toolTip = openTitle
        open.setAccessibilityLabel(openTitle)
        for view in [label, detail, capture, open] {
            view.translatesAutoresizingMaskIntoConstraints = false
            addSubview(view)
        }
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            label.topAnchor.constraint(equalTo: topAnchor, constant: 11),
            detail.leadingAnchor.constraint(greaterThanOrEqualTo: label.trailingAnchor, constant: 12),
            detail.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12),
            detail.centerYAnchor.constraint(equalTo: label.centerYAnchor),
            capture.leadingAnchor.constraint(equalTo: label.leadingAnchor),
            capture.topAnchor.constraint(equalTo: label.bottomAnchor, constant: 8),
            open.leadingAnchor.constraint(equalTo: capture.trailingAnchor, constant: 6),
            open.centerYAnchor.constraint(equalTo: capture.centerYAnchor),
            open.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -12),
            heightAnchor.constraint(equalToConstant: 78),
        ])
        registerForDraggedTypes([.fileURL])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func draw(_ dirtyRect: NSRect) {
        if isDropping {
            accent.withAlphaComponent(0.12).setFill()
            NSBezierPath(roundedRect: bounds.insetBy(dx: 3, dy: 4), xRadius: 8, yRadius: 8).fill()
        }
    }
    private func droppedURL(_ sender: NSDraggingInfo) -> URL? {
        let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]
        return urls?.count == 1 ? urls?.first : nil
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        isDropping = droppedURL(sender) != nil
        return isDropping ? .copy : []
    }
    override func draggingExited(_ sender: NSDraggingInfo?) { isDropping = false }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        isDropping = false
        guard let url = droppedURL(sender) else { return false }
        onDrop?(url)
        return true
    }
}

struct ScreenComparePendingView: View {
    let image: NSImage
    let title: String
    let hint: String
    let captureTitle: String
    let cancelTitle: String
    let capture: () -> Void
    let cancel: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Image(nsImage: image).resizable().scaledToFit()
                .frame(width: 92, height: 66)
                .background(Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            VStack(alignment: .leading, spacing: 7) {
                Text(title).font(.system(size: 12, weight: .semibold))
                Text(hint).font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 10) {
                    Button(captureTitle, action: capture).buttonStyle(.borderedProminent).controlSize(.small)
                    Button(cancelTitle, action: cancel).buttonStyle(.plain).font(.system(size: 11))
                }
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

final class ScreenCompareCanvas: NSView {
    var before: CGImage? { didSet { needsDisplay = true } }
    var after: CGImage? { didSet { needsDisplay = true } }
    var overlay: CGImage? { didSet { needsDisplay = true } }
    var showsDifferences = false { didSet { needsDisplay = true } }
    var fraction: Double = 0.5 { didSet { needsDisplay = true } }
    var onFractionChanged: ((Double) -> Void)?
    var placeholder = "" { didSet { needsDisplay = true } }
    var beforeTitle = "", afterTitle = ""

    override var isFlipped: Bool { true }

    var imageRect: CGRect {
        guard let image = before ?? after else { return .zero }
        let area = bounds.insetBy(dx: 28, dy: 32)
        let factor = min(area.width / CGFloat(image.width), area.height / CGFloat(image.height))
        let size = CGSize(width: CGFloat(image.width) * factor, height: CGFloat(image.height) * factor)
        return CGRect(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2, width: size.width, height: size.height)
    }

    override func draw(_ dirtyRect: NSRect) {
        (NSColor.textBackgroundColor.blended(withFraction: 0.04, of: .labelColor) ?? .controlBackgroundColor).setFill()
        bounds.fill()
        guard before != nil || after != nil else {
            let symbol = NSImage(systemSymbolName: "rectangle.on.rectangle", accessibilityDescription: nil)!
            let symbolRect = NSRect(x: bounds.midX - 23, y: bounds.midY - 60, width: 46, height: 46)
            symbol.draw(in: symbolRect, from: .zero, operation: .sourceOver, fraction: 0.4, respectFlipped: true, hints: nil)
            let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
            (placeholder as NSString).draw(in: NSRect(x: 36, y: bounds.midY + 2, width: bounds.width - 72, height: 64),
                withAttributes: [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: NSColor.secondaryLabelColor, .paragraphStyle: paragraph])
            return
        }
        let rect = imageRect
        // A light checker gives transparent images a stable visible backing.
        NSColor.controlBackgroundColor.setFill(); rect.fill()
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect: rect).addClip()
        NSColor.separatorColor.withAlphaComponent(0.2).setFill()
        for y in stride(from: rect.minY, to: rect.maxY, by: 12) {
            for x in stride(from: rect.minX, to: rect.maxX, by: 12) where Int((x - rect.minX) / 12 + (y - rect.minY) / 12) % 2 == 0 {
                NSRect(x: x, y: y, width: 12, height: 12).fill()
            }
        }
        NSGraphicsContext.restoreGraphicsState()
        if showsDifferences, let after, let overlay {
            drawImage(after, in: rect)
            drawImage(overlay, in: rect)
        } else if let before, let after, before.width == after.width, before.height == after.height {
            drawImage(after, in: rect)
            let split = rect.minX + rect.width * fraction
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath(rect: CGRect(x: rect.minX, y: rect.minY, width: rect.width * fraction, height: rect.height)).addClip()
            drawImage(before, in: rect)
            NSGraphicsContext.restoreGraphicsState()
            NSColor.black.withAlphaComponent(0.6).setFill()
            NSRect(x: split - 2, y: rect.minY, width: 4, height: rect.height).fill()
            NSColor.white.setFill()
            NSRect(x: split - 0.75, y: rect.minY, width: 1.5, height: rect.height).fill()
            let handle = CGRect(x: split - 15, y: rect.midY - 15, width: 30, height: 30)
            NSBezierPath(ovalIn: handle).fill()
            let arrows = NSImage(systemSymbolName: "arrow.left.and.right", accessibilityDescription: nil)!
            arrows.withSymbolConfiguration(.init(paletteColors: [.black]))?.draw(in: handle.insetBy(dx: 6, dy: 6),
                from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
        } else if let image = before ?? after { drawImage(image, in: rect) }
        let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .left
        let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 10, weight: .semibold),
            .foregroundColor: NSColor.secondaryLabelColor, .paragraphStyle: paragraph]
        if before != nil { (beforeTitle as NSString).draw(at: CGPoint(x: rect.minX, y: rect.minY - 19), withAttributes: attributes) }
        if let after, before == nil || (before?.width == after.width && before?.height == after.height) {
            let width = (afterTitle as NSString).size(withAttributes: attributes).width
            (afterTitle as NSString).draw(at: CGPoint(x: rect.maxX - width, y: rect.minY - 19), withAttributes: attributes)
        }
    }

    private func drawImage(_ image: CGImage, in rect: CGRect) {
        let value = NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
        value.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.none])
    }
    override func resetCursorRects() {
        if before != nil && after != nil && !showsDifferences { addCursorRect(imageRect, cursor: .resizeLeftRight) }
    }
    override func mouseDown(with event: NSEvent) { moveDivider(event) }
    override func mouseDragged(with event: NSEvent) { moveDivider(event) }
    private func moveDivider(_ event: NSEvent) {
        guard before != nil, after != nil, !showsDifferences, imageRect.width > 0 else { return }
        let point = convert(event.locationInWindow, from: nil)
        fraction = min(1, max(0, Double((point.x - imageRect.minX) / imageRect.width)))
        onFractionChanged?(fraction)
    }
}
