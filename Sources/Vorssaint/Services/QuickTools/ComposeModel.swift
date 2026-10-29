// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import ImageIO

enum ComposeLayout: String, CaseIterable, Identifiable {
    case row = "Row", column = "Column", grid = "Grid"
    var id: String { rawValue }
}

struct ComposeItem: Identifiable {
    let id = UUID()
    let image: CGImage?
    let name: String
    var caption = ""
    var text = ""
    var sizePercent = 100.0
}

struct ComposeSnapshot {
    var items: [ComposeItem]
    var layout: ComposeLayout = .grid
    var columns = 2
    var width = 1440
    var title = ""
    var paragraph = ""
}

enum ComposeRenderer {
    static let imageLimit = 12
    enum Failure: LocalizedError {
        case unreadable, tooLarge, empty
        var errorDescription: String? {
            switch self {
            case .unreadable: return "This image could not be opened."
            case .tooLarge: return "The composition is too large. Try a grid, a smaller width, or fewer items."
            case .empty: return "Add an image or write some text to start composing."
            }
        }
    }

    /// Decode bounded, orientation-correct pixels without changing the source file.
    static func load(_ url: URL) throws -> CGImage {
        guard url.isFileURL,
              let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 4096,
                kCGImageSourceShouldCacheImmediately: true
              ] as CFDictionary) else { throw Failure.unreadable }
        return image
    }

    static func render(_ snapshot: ComposeSnapshot) throws -> CGImage {
        let imageCount = snapshot.items.filter { $0.image != nil }.count
        guard imageCount > 0 || snapshot.items.contains(where: { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else { throw Failure.empty }
        guard imageCount <= imageLimit, (640...2400).contains(snapshot.width),
              snapshot.items.filter({ $0.image != nil }).allSatisfy({ $0.sizePercent.isFinite && (10...100).contains($0.sizePercent) }) else { throw Failure.tooLarge }
        let width = CGFloat(snapshot.width), scale = width / 1440
        let padding = 32 * scale, gap = 24 * scale
        func text(_ value: String, size: CGFloat, bold: Bool = false) -> NSAttributedString {
            let paragraph = NSMutableParagraphStyle()
            paragraph.lineBreakMode = .byWordWrapping
            return NSAttributedString(string: value, attributes: [
                .font: bold ? NSFont.systemFont(ofSize: size * scale, weight: .semibold) : NSFont.systemFont(ofSize: size * scale),
                .foregroundColor: NSColor(calibratedWhite: 0.12, alpha: 1), .paragraphStyle: paragraph
            ])
        }
        func height(_ text: NSAttributedString, width: CGFloat) -> CGFloat {
            guard text.length > 0 else { return 0 }
            return ceil(text.boundingRect(with: CGSize(width: width, height: 100_000),
                options: [.usesLineFragmentOrigin, .usesFontLeading]).height)
        }
        let title = text(snapshot.title, size: 44, bold: true)
        let paragraph = text(snapshot.paragraph, size: 24)
        var labels: [(NSAttributedString, CGRect)] = []
        var pictures: [(CGImage, CGRect)] = []
        var y = padding
        for label in [title, paragraph] where label.length > 0 {
            let h = height(label, width: width - padding * 2)
            labels.append((label, CGRect(x: padding, y: y, width: width - padding * 2, height: h)))
            y += h + gap
        }
        func appendImages(_ items: [ComposeItem]) {
            guard !items.isEmpty else { return }
            let columns = snapshot.layout == .column ? 1 : snapshot.layout == .row ? items.count
                : min(items.count, max(2, min(4, snapshot.columns)))
            let cellWidth = (width - padding * 2 - gap * CGFloat(columns - 1)) / CGFloat(columns)
            for start in stride(from: 0, to: items.count, by: columns) {
                var rowHeight: CGFloat = 0
                for index in start..<min(start + columns, items.count) {
                    let item = items[index]
                    guard let image = item.image else { continue }
                    let imageWidth = cellWidth * item.sizePercent / 100
                    let h = imageWidth * CGFloat(image.height) / CGFloat(image.width)
                    let x = padding + CGFloat(index - start) * (cellWidth + gap) + (cellWidth - imageWidth) / 2
                    pictures.append((image, CGRect(x: x, y: y, width: imageWidth, height: h)))
                    let caption = text(item.caption, size: 22)
                    let captionHeight = height(caption, width: imageWidth)
                    if captionHeight > 0 {
                        labels.append((caption, CGRect(x: x, y: y + h + gap / 2, width: imageWidth, height: captionHeight)))
                    }
                    rowHeight = max(rowHeight, h + (captionHeight > 0 ? gap / 2 + captionHeight : 0))
                }
                y += rowHeight + gap
            }
        }
        // Text spans the composition and separates image groups in every layout.
        var group: [ComposeItem] = []
        for item in snapshot.items {
            if item.image != nil { group.append(item) }
            else if !item.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                appendImages(group); group.removeAll()
                let label = text(item.text, size: 24)
                let h = height(label, width: width - padding * 2)
                labels.append((label, CGRect(x: padding, y: y, width: width - padding * 2, height: h)))
                y += h + gap
            }
        }
        appendImages(group)
        let outputHeight = ceil(y - gap + padding)
        guard outputHeight.isFinite, outputHeight <= 16_384, width * outputHeight <= 32_000_000,
              let context = CGContext(data: nil, width: snapshot.width, height: Int(outputHeight), bitsPerComponent: 8,
                bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { throw Failure.tooLarge }
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: outputHeight))
        context.translateBy(x: 0, y: outputHeight)
        context.scaleBy(x: 1, y: -1)
        context.interpolationQuality = .high
        for (image, rect) in pictures {
            context.saveGState()
            context.translateBy(x: rect.minX, y: rect.maxY)
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(origin: .zero, size: rect.size))
            context.restoreGState()
        }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
        for (label, rect) in labels { label.draw(with: rect, options: [.usesLineFragmentOrigin, .usesFontLeading]) }
        NSGraphicsContext.restoreGraphicsState()
        guard let image = context.makeImage() else { throw Failure.tooLarge }
        return image
    }

    static func png(_ image: CGImage) throws -> Data {
        guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            throw Failure.unreadable
        }
        return data
    }
}
