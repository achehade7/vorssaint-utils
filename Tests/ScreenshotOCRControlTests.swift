// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import SwiftUI

/// Hosts the production preview view and presses its actual accessibility
/// buttons. The feature/history stores and unrelated sharing/QR dependencies
/// are substituted; visibility, observation, labels and button actions are real.
enum ScreenshotOCRControlTests {
    enum AppFeature { case screenOCR }
    final class FeatureRuntime: ObservableObject {
        static let shared = FeatureRuntime()
        @Published var available = false
        func isAvailable(_ feature: AppFeature) -> Bool { available }
    }
    enum BarcodeDetector { typealias Reading = String }
    struct L10n {
        static let shared = Self()
        struct Strings { let qrResultTitle = "QR code" }
        let s = Strings()
    }
    struct ShelfSharePickerAnchor: View {
        final class Anchor {}
        let anchor: Anchor
        var body: some View { Color.clear }
    }
    final class RecentCaptureService: ObservableObject {
        static let shared = RecentCaptureService()
        @Published var entries: [RecentCaptureEntry] = []
        var image: NSImage?
        func thumbnail(for entry: RecentCaptureEntry) -> NSImage? { image }
    }

    static func settle(_ host: NSView) {
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        host.layoutSubtreeIfNeeded()
    }

    // SwiftUI's accessibility nodes implement these Objective-C selectors
    // without declaring NSAccessibilityProtocol conformance.
    static func buttons(_ element: AnyObject, label: String) -> [AnyObject] {
        var found: [AnyObject] = []
        if element.accessibilityRole?() == .button && element.accessibilityLabel?() == label {
            found.append(element)
        }
        for child in element.accessibilityChildren?() ?? [] {
            found += buttons(child as AnyObject, label: label)
        }
        return found
    }

    static func run(_ suite: TestSuite) {
        _ = NSApplication.shared
        // SwiftUI builds its accessibility tree lazily. Enable it only for
        // this process through AppKit's legacy attribute API, preserving the
        // prior value. No Accessibility permission or desktop input is used.
        let attribute = "AXEnhancedUserInterface"
        let getter = NSSelectorFromString("accessibilityAttributeValue:")
        let setter = NSSelectorFromString("accessibilitySetValue:forAttribute:")
        let previous = NSApp.perform(getter, with: attribute)?.takeUnretainedValue() as? NSNumber ?? false
        NSApp.perform(setter, with: true, with: attribute)
        defer { NSApp.perform(setter, with: previous, with: attribute) }
        let domain = "vorss.tests.ocr-control.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: domain)!
        defaults.set(true, forKey: DefaultsKey.screenshotSharingEnabled)
        defer {
            defaults.removePersistentDomain(forName: domain)
            FeatureRuntime.shared.available = false
            RecentCaptureService.shared.entries = []
            RecentCaptureService.shared.image = nil
        }
        let context = CGContext(data: nil, width: 32, height: 32, bitsPerComponent: 8,
                                bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        let image = context.makeImage()!
        func historyEntry(_ kind: RecentCaptureEntry.Kind) -> RecentCaptureEntry {
            RecentCaptureEntry(
                id: UUID(), kind: kind, createdAt: Date(),
                screenshotName: nil, recordingPath: nil, thumbnailName: "fixture.png",
                scale: 1, anchorX: 0, anchorY: 0, anchorWidth: 32, anchorHeight: 32)
        }
        for embedded in [false, true] {
            for language in [AppLanguage.enUS, .de] {
                FeatureRuntime.shared.available = false
                let newest = historyEntry(.screenshot)
                let older = historyEntry(.screenshot)
                RecentCaptureService.shared.entries = embedded
                    ? [newest, historyEntry(.recording), older] : []
                RecentCaptureService.shared.image = NSImage(cgImage: image, size: NSSize(width: 32, height: 32))
                let strings = FeatureStrings.screenshot(language)
                let model = ScreenshotQuickPreviewModel()
                model.qr = "test QR"
                var presses = 0
                var actionPresses = 0
                var browsed: [UUID] = []
                let view = ScreenshotQuickPreviewView(
                    image: image, strings: strings, model: model, perform: { _ in },
                    dragItem: { NSItemProvider() }, share: { _ in }, systemShare: {},
                    shareAnchor: ShelfSharePickerAnchor.Anchor(), copySharedLink: {},
                    deleteSharedLink: {}, showQR: {}, copyText: { presses += 1 },
                    showActions: { actionPresses += 1 },
                    dismiss: {}, hoverChanged: { _ in }, showsDismissButton: true,
                    embedded: embedded, historyID: embedded ? newest.id : nil,
                    browseHistory: { browsed.append($0.id) })
                let host = NSHostingView(rootView: VStack(spacing: 0) {
                    if embedded { view.toolbar.fixedSize() }
                    view
                }.background(embedded ? Color.black : Color.clear).defaultAppStorage(defaults))
                let window = NSWindow(contentRect: NSRect(x: -10000, y: -10000, width: 350, height: 210),
                                      styleMask: [.borderless], backing: .buffered, defer: false)
                window.isReleasedWhenClosed = false
                window.contentView = host
                host.frame = NSRect(x: 0, y: 0, width: 350, height: 210)
                defer { window.contentView = nil; window.close() }
                settle(host)
                let actions = buttons(host, label: SharedToolActionStrings.actions)
                suite.expect(actions.count == 1 && (actions[0].accessibilityPerformPress?() ?? false)
                             && actionPresses == 1,
                             "\(language.rawValue) embedded=\(embedded): visible Actions opens the source's shared menu")
                suite.expect(buttons(host, label: strings.copyTextButton).isEmpty,
                             "\(language.rawValue) embedded=\(embedded): OCR button is absent when disabled")
                if embedded {
                    let olderButtons = buttons(host, label: "Older screenshot")
                    suite.expect(olderButtons.count == 1,
                                 "\(language.rawValue): the island preview retains its screenshot conveyor")
                    let performed = olderButtons.first?.accessibilityPerformPress?() ?? false
                    settle(host)
                    suite.expect(performed && browsed == [older.id] && presses == 0,
                                 "\(language.rawValue): the conveyor skips recordings without invoking OCR")
                }
                for _ in 0..<2 {
                    FeatureRuntime.shared.available = true
                    settle(host)
                    let controls = buttons(host, label: strings.copyTextButton)
                    suite.expect(controls.count == 1,
                                 "\(language.rawValue) embedded=\(embedded): enabling OCR reveals exactly one localized button")
                    let before = presses
                    let performed = controls.first?.accessibilityPerformPress?() ?? false
                    settle(host)
                    suite.expect(performed && presses == before + 1,
                                 "\(language.rawValue) embedded=\(embedded): pressing the rendered OCR button calls its action once")
                    suite.expect(browsed == (embedded ? [older.id] : []),
                                 "\(language.rawValue) embedded=\(embedded): OCR does not browse capture history")
                    FeatureRuntime.shared.available = false
                    settle(host)
                    suite.expect(buttons(host, label: strings.copyTextButton).isEmpty,
                                 "\(language.rawValue) embedded=\(embedded): disabling OCR removes the button from the same view")
                }
                // The island toolbar makes room for the button. The floating
                // action row was already full in longer languages, so there
                // the button rides on the thumbnail and the row keeps its width.
                func rowWidth(ocr: Bool) -> CGFloat {
                    FeatureRuntime.shared.available = ocr
                    let row = NSHostingView(rootView: view.toolbar.defaultAppStorage(defaults))
                    settle(row)
                    return row.fittingSize.width
                }
                let withoutOCR = rowWidth(ocr: false)
                let withOCR = rowWidth(ocr: true)
                FeatureRuntime.shared.available = false
                suite.expect(embedded ? withOCR > withoutOCR : withOCR == withoutOCR,
                             "\(language.rawValue) embedded=\(embedded): only the island toolbar makes room for the OCR button")
                if embedded {
                    suite.expect(withOCR <= 350,
                                 "\(language.rawValue): Actions fits with every existing island toolbar control (\(withOCR)pt)")
                }
                if language == .enUS {
                    FeatureRuntime.shared.available = true
                    for (label, name) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
                        window.appearance = NSAppearance(named: name)
                        settle(host)
                        if let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
                            host.cacheDisplay(in: host.bounds, to: bitmap)
                            let destination = URL(fileURLWithPath: "/tmp/screenshot-actions-\(embedded ? "island" : "floating")-\(label).png")
                            try? bitmap.representation(using: .png, properties: [:])?.write(to: destination)
                        }
                    }
                    FeatureRuntime.shared.available = false
                }
            }
        }
    }
}
