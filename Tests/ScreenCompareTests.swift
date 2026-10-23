// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import CoreGraphics
import ImageIO

enum ScreenCompareTests {
    static func image(_ pixels: [UInt8], width: Int, height: Int) -> CGImage {
        CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: width * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: CGDataProvider(data: Data(pixels) as CFData)!, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
    }

    static func run(_ suite: TestSuite) {
        suite.expect(ScreenCompareModel.validSize(width: 4000, height: 4000), "16 million pixels is accepted exactly")
        for pair in [(0, 10), (10, 0), (-1, 1), (Int.max, 2), (4000, 4001)] {
            suite.expect(!ScreenCompareModel.validSize(width: pair.0, height: pair.1), "invalid and oversized dimensions fail before allocation")
        }
        let beforePixels: [UInt8] = [100, 100, 100, 255, 10, 20, 30, 255, 0, 0, 0, 0, 220, 220, 220, 255]
        var afterPixels = beforePixels
        afterPixels[0] = 101
        afterPixels[5] = 90
        afterPixels[11] = 100
        let before = image(beforePixels, width: 2, height: 2)
        let after = image(afterPixels, width: 2, height: 2)
        do {
            let analysis = try ScreenCompareModel.analyze(before: before, after: after)
            suite.expect(analysis.differences.sorted() == [0, 1, 70, 100], "one-channel, large and alpha-only changes remain measurable")
            let exact = try analysis.overlay(tolerance: 0)
            suite.expect(exact.changedPixels == 3 && exact.totalPixels == 4 && exact.percentage == 75,
                "exact comparison counts changed pixels without guessing alignment")
            suite.expect(try analysis.overlay(tolerance: 1).changedPixels == 2, "tolerance is inclusive and suppresses a one-unit rendering difference")
            suite.expect(try analysis.overlay(tolerance: 70).changedPixels == 1, "alpha changes remain visible above RGB tolerance")
            suite.expect(try analysis.overlay(tolerance: 255).changedPixels == 0, "maximum tolerance suppresses every channel difference")
            let identical = try ScreenCompareModel.analyze(before: before, after: before).overlay(tolerance: 0)
            suite.expect(identical.changedPixels == 0, "identical inputs are exactly identical")
            let bytes = exact.image.dataProvider!.data! as Data
            suite.expect(stride(from: 3, to: bytes.count, by: 4).filter { bytes[$0] == 0 }.count == 1,
                "overlay is transparent at unchanged pixels")
            suite.expect((before.dataProvider!.data! as Data) == Data(beforePixels), "comparison leaves original image bytes unchanged")
        } catch { suite.expect(false, "valid pixel comparison succeeds: \(error)") }
        do {
            _ = try ScreenCompareModel.analyze(before: before, after: image([0, 0, 0, 255], width: 1, height: 1))
            suite.expect(false, "mismatched dimensions must throw")
        } catch ScreenCompareModel.Failure.sizeMismatch { suite.expect(true, "no silent resize for incompatible images") }
        catch { suite.expect(false, "dimension mismatch gives its precise error") }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
            defer { try? FileManager.default.removeItem(at: directory) }
            let url = directory.appendingPathComponent("source.png")
            let destination = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil)!
            CGImageDestinationAddImage(destination, before, nil)
            suite.expect(CGImageDestinationFinalize(destination), "PNG fixture writes")
            let original = try Data(contentsOf: url)
            let loaded = try ScreenCompareModel.load(url)
            suite.expect(loaded.width == 2 && loaded.height == 2, "import preserves original dimensions")
            suite.expect(try ScreenCompareModel.analyze(before: before, after: loaded).overlay(tolerance: 0).changedPixels == 0,
                "lossless PNG round trip compares identically")
            suite.expect(try Data(contentsOf: url) == original, "import never rewrites the source file")
            let invalid = directory.appendingPathComponent("invalid.png")
            try Data("not an image".utf8).write(to: invalid)
            do { _ = try ScreenCompareModel.load(invalid); suite.expect(false, "invalid image must throw") }
            catch { suite.expect(true, "invalid file is rejected") }
            do { _ = try ScreenCompareModel.load(directory); suite.expect(false, "directory must throw") }
            catch { suite.expect(true, "directory is rejected before reading") }
            let animated = directory.appendingPathComponent("animated.gif")
            let animation = CGImageDestinationCreateWithURL(animated as CFURL, "com.compuserve.gif" as CFString, 2, nil)!
            CGImageDestinationAddImage(animation, before, nil); CGImageDestinationAddImage(animation, after, nil)
            suite.expect(CGImageDestinationFinalize(animation), "animated fixture writes")
            do { _ = try ScreenCompareModel.load(animated); suite.expect(false, "animation must not silently compare its first frame") }
            catch { suite.expect(true, "animated images are rejected explicitly") }
        } catch { suite.expect(false, "file fixture succeeds: \(error)") }
        for language in AppLanguage.allCases {
            let strings = ScreenCompareStrings.localized(language)
            suite.expect(ScreenCompareStrings.Key.allCases.allSatisfy { !strings[$0].isEmpty }, "every locale supplies all screen comparison strings")
        }
    }
}
