// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import CoreGraphics
import ImageIO

/// A bounded, deterministic comparison of visible sRGB pixels. There is no
/// resampling, alignment guess, OCR, or network operation in this comparison.
enum ScreenCompareModel {
    static let maximumPixels = 16_000_000
    static let maximumFileBytes = 64_000_000

    enum Failure: Error { case tooLarge, invalidImage, sizeMismatch }

    struct Analysis: @unchecked Sendable {
        let width: Int
        let height: Int
        /// Largest absolute channel difference, including alpha, per pixel.
        let differences: [UInt8]

        func overlay(tolerance: Int) throws -> Overlay {
            let threshold = UInt8(clamping: tolerance)
            var bytes = [UInt8](repeating: 0, count: differences.count * 4)
            var count = 0
            for pixel in differences.indices {
                if pixel % 65_536 == 0 { try Task.checkCancellation() }
                guard differences[pixel] > threshold else { continue }
                count += 1
                // Alternating light/dark magenta diagonals distinguish a
                // changed region by texture as well as color.
                let light = ((pixel % width) + (pixel / width)) % 8 < 4
                let i = pixel * 4
                bytes[i] = light ? 230 : 110
                bytes[i + 1] = light ? 45 : 8
                bytes[i + 2] = light ? 195 : 100
                bytes[i + 3] = light ? 230 : 150
            }
            guard let provider = CGDataProvider(data: Data(bytes) as CFData),
                  let image = CGImage(width: width, height: height, bitsPerComponent: 8,
                    bitsPerPixel: 32, bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                    bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                    provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
            else { throw Failure.invalidImage }
            return Overlay(image: image, changedPixels: count, totalPixels: differences.count)
        }
    }

    struct Overlay: @unchecked Sendable {
        let image: CGImage
        let changedPixels: Int
        let totalPixels: Int
        var percentage: Double { Double(changedPixels) / Double(totalPixels) * 100 }
    }

    static func validSize(width: Int, height: Int) -> Bool {
        width > 0 && height > 0 && width <= maximumPixels && height <= maximumPixels / width
    }

    static func load(_ url: URL) throws -> CGImage {
        guard url.isFileURL,
              let values = try? url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey]),
              values.isRegularFile == true, let byteCount = values.fileSize
        else { throw Failure.invalidImage }
        guard byteCount <= maximumFileBytes else { throw Failure.tooLarge }
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        guard data.count <= maximumFileBytes else { throw Failure.tooLarge }
        try Task.checkCancellation()
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int
        else { throw Failure.invalidImage }
        guard validSize(width: width, height: height) else { throw Failure.tooLarge }
        // ImageIO applies EXIF orientation without reducing pixel dimensions.
        // Animated and multipage files are rejected rather than silently
        // comparing only one frame.
        guard CGImageSourceGetCount(source) == 1,
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: max(width, height),
                kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
        else { throw Failure.invalidImage }
        try Task.checkCancellation()
        return image
    }

    static func analyze(before: CGImage, after: CGImage) throws -> Analysis {
        guard before.width == after.width, before.height == after.height else { throw Failure.sizeMismatch }
        guard validSize(width: before.width, height: before.height) else { throw Failure.tooLarge }
        let left = try pixels(before), right = try pixels(after)
        var difference = [UInt8](repeating: 0, count: before.width * before.height)
        for pixel in difference.indices {
            if pixel % 65_536 == 0 { try Task.checkCancellation() }
            let i = pixel * 4
            difference[pixel] = (0..<4).reduce(UInt8(0)) { maximum, channel in
                max(maximum, UInt8(abs(Int(left[i + channel]) - Int(right[i + channel]))))
            }
        }
        return Analysis(width: before.width, height: before.height, differences: difference)
    }

    private static func pixels(_ image: CGImage) throws -> [UInt8] {
        try Task.checkCancellation()
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let rendered = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width * 4,
                space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.setBlendMode(.copy)
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }
        guard rendered else { throw Failure.invalidImage }
        return bytes
    }
}
