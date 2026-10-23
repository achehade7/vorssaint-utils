#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise the native comparison window; capture/permission/island boundaries are deterministic fixtures."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
fixture = r'''
import AppKit
import SwiftUI
import ImageIO

enum AppLanguage: CaseIterable { case enUS, ptBR, tr, ru, es, sk, de, fr, it, ja, ko, uk, zhHans, zhTW, zhHK }
struct L10n { static let shared = Self(); let language = AppLanguage.enUS }
enum AppFeature { case screenshot; static var enabled = true; var isAvailable: Bool { Self.enabled } }
final class Permissions {
    static let shared = Permissions()
    var screenRecording = true
    var requested = false
    func refresh() {}
    func requestScreenRecording() { requested = true }
}
extension NSScreen { var displayID: CGDirectDisplayID { (deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0 } }
enum RecorderSupport {
    struct Region { let displayID: CGDirectDisplayID; let pixelRect: CGRect; let scale: CGFloat }
}
final class ScreenshotSelectionController {
    enum Mode { case geometry }
    enum Outcome { case region(RecorderSupport.Region), failed, cancelled }
    static var isSessionOnScreen = false
    static var next: Outcome = .cancelled
    static var hidesContentWindows = true
    var protectedWindowIDs: Set<CGWindowID> { [666] }
    init(freeze: Bool, includePointer: Bool, showLastRegion: Bool, hideVorssaintWindows: Bool, protectedWindowIDs: @escaping () -> Set<CGWindowID> = { [] }, purpose: String?, mode: Mode, requiresDraggedRegion: Bool) { Self.hidesContentWindows = hideVorssaintWindows }
    func begin(completion: @escaping (Outcome) -> Void) { completion(Self.next) }
    func cancel() {}
}
enum ScreenshotCaptureEngine {
    static var next: CGImage?
    static var capturedRegion: CGRect?
    static var excludesIsland = false
    static var hidesContentWindows = true
    static var protectedIDs: Set<CGWindowID> = []
    final class RegionCapture { func image() async -> CGImage? { ScreenshotCaptureEngine.next } }
    static func prepareDisplayRegion(displayID: CGDirectDisplayID, pixelRect: CGRect, includePointer: Bool,
        hideVorssaintWindows: Bool, protectedWindowIDs: Set<CGWindowID>, keepsIslandOut: Bool) async -> RegionCapture? {
        capturedRegion = pixelRect; excludesIsland = keepsIslandOut
        hidesContentWindows = hideVorssaintWindows; protectedIDs = protectedWindowIDs
        return RegionCapture()
    }
}
final class NotchService {
    static let shared = NotchService()
    var captureID: UUID?
    var protectedWindowIDs: Set<CGWindowID> { [777] }
    var takesFocus = false
    var closesOnCollapse = true
    func presentCapture(id: UUID, content: AnyView, actions: AnyView? = nil, height: CGFloat, takeFocus: Bool,
        closeOnCollapse: Bool, fallback: @escaping () -> Void, close: @escaping () -> Void, hover: @escaping (Bool) -> Void) -> Bool {
        captureID = id; takesFocus = takeFocus; closesOnCollapse = closeOnCollapse
        return true
    }
    func removeCapture(id: UUID) { if captureID == id { captureID = nil } }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) { checks += 1; precondition(condition, message) }
func until(_ predicate: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(10)
    repeat {
        if predicate() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.01))
    } while Date() < deadline
    return false
}
func drain(_ duration: TimeInterval = 0.1) { RunLoop.main.run(until: Date().addingTimeInterval(duration)) }
func views(_ root: NSView) -> [NSView] { [root] + root.subviews.flatMap(views) }
let session = CGSessionCopyCurrentDictionary() as? [String: Any]
guard session?["CGSSessionScreenIsLocked"] as? Bool != true else {
    fputs("ERROR: Native screen comparison checks require an unlocked Mac. No input was sent.\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let service = ScreenCompareService.shared
let strings = ScreenCompareStrings.localized(.enUS)
let clipboardCount = NSPasteboard.general.changeCount
func window() -> NSWindow { app.windows.first { $0.title == strings[.title] }! }
func view(_ id: String) -> NSView { views(window().contentView!).first { $0.identifier?.rawValue == "screenCompare." + id }! }
func summary() -> String { (view("summary") as! NSTextField).stringValue }
func button(_ id: String) -> NSButton { view(id) as! NSButton }
func canvas() -> ScreenCompareCanvas { view("canvas") as! ScreenCompareCanvas }
func capture(_ name: String, size: NSSize = NSSize(width: 960, height: 650)) {
    let window = window()
    window.setContentSize(size)
    for (label, appearance) in [("light", NSAppearance.Name.aqua), ("dark", .darkAqua)] {
        window.appearance = NSAppearance(named: appearance)
        drain()
        let content = window.contentView!
        content.layoutSubtreeIfNeeded(); content.displayIfNeeded()
        let bitmap = content.bitmapImageRepForCachingDisplay(in: content.bounds)!
        content.cacheDisplay(in: content.bounds, to: bitmap)
        try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/screen-compare-\(name)-\(label).png"))
        for control in views(content).filter({ $0 is NSControl && !$0.isHidden }) {
            let rect = control.convert(control.bounds, to: content)
            expect(content.bounds.insetBy(dx: -1, dy: -1).contains(rect), "control fits within \(name) \(label): \(control)")
        }
    }
}
func fixtureImage(changed: Bool) -> CGImage {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1000, pixelsHigh: 560, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    NSColor(calibratedWhite: 0.96, alpha: 1).setFill(); NSRect(x: 0, y: 0, width: 1000, height: 560).fill()
    NSColor.white.setFill(); NSBezierPath(roundedRect: NSRect(x: 32, y: 28, width: 936, height: 500), xRadius: 14, yRadius: 14).fill()
    func text(_ value: String, _ x: Double, _ y: Double, _ size: Double = 16, _ color: NSColor = .darkGray) {
        (value as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: [.font: NSFont.monospacedSystemFont(ofSize: size, weight: .regular), .foregroundColor: color])
    }
    text("Integration settings", 64, 467, 24, .black)
    text("Order confirmation · HTTP receiver", 64, 428, 15)
    NSColor(calibratedWhite: 0.91, alpha: 1).setFill(); NSRect(x: 64, y: 399, width: 872, height: 1).fill()
    text("Endpoint", 64, 347); text("/api/v1/orders", 390, 347)
    text("Connection timeout", 64, 292); text(changed ? "60 seconds" : "30 seconds", 390, 292)
    text("Retries", 64, 237); text("3", 390, 237)
    text("Authentication", 64, 182); text("Client certificate", 390, 182)
    NSColor.systemBlue.setFill(); NSBezierPath(roundedRect: NSRect(x: changed ? 772 : 792, y: 72, width: 144, height: 38), xRadius: 7, yRadius: 7).fill()
    text("Save", changed ? 820 : 840, 80, 15, .white)
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.cgImage!
}
let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
defer { try? FileManager.default.removeItem(at: directory) }
func write(_ image: CGImage, name: String) -> URL {
    let url = directory.appendingPathComponent(name + ".png")
    let destination = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, image, nil)
    expect(CGImageDestinationFinalize(destination), "fixture writes")
    return url
}
let before = fixtureImage(changed: false), after = fixtureImage(changed: true)
let beforeURL = write(before, name: "Before"), afterURL = write(after, name: "After")
let original = try! Data(contentsOf: beforeURL)
service.show()
expect(summary() == strings[.empty], "empty state explains capture or file input")
expect(!button("captureAfter").isEnabled, "After capture requires a Before region")
capture("empty", size: NSSize(width: 660, height: 430))
service.loadImage(beforeURL, isBefore: true)
service.loadImage(afterURL, isBefore: false)
expect(until { canvas().overlay != nil }, "independent imports settle into a comparison")
expect(canvas().before?.width == 1000 && canvas().after?.width == 1000, "both source images load without reduction")
expect(summary().contains("pixels changed"), "changed pixel summary is visible")
let wipe = view("wipe") as! NSSlider
wipe.doubleValue = 0.25; wipe.sendAction(wipe.action!, to: wipe.target)
expect(canvas().fraction == 0.25, "native slider moves the wipe")
let point = canvas().convert(CGPoint(x: canvas().imageRect.midX, y: canvas().imageRect.midY), to: nil)
let event = NSEvent.mouseEvent(with: .leftMouseDown, location: point, modifierFlags: [], timestamp: 0,
    windowNumber: window().windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1)!
canvas().mouseDown(with: event)
expect(abs(canvas().fraction - 0.5) < 0.01 && abs(wipe.doubleValue - 0.5) < 0.01, "dragging the image divider synchronizes native slider")
capture("wipe")
capture("wipe-small", size: NSSize(width: 660, height: 430))
let mode = view("mode") as! NSSegmentedControl
mode.selectedSegment = 1; mode.sendAction(mode.action!, to: mode.target)
expect(canvas().showsDifferences && !wipe.isEnabled, "difference mode uses overlay and disables the wipe")
capture("overlay")
let tolerance = view("tolerance") as! NSSlider
tolerance.doubleValue = 255; tolerance.sendAction(tolerance.action!, to: tolerance.target)
expect(until { summary() == strings[.noPixels] }, "sensitivity change recomputes the deterministic overlay")
tolerance.doubleValue = 0; tolerance.sendAction(tolerance.action!, to: tolerance.target)
expect(until { summary().contains("pixels changed") }, "exact sensitivity restores all changes")
service.loadImage(beforeURL, isBefore: false)
expect(until { summary() == ClipboardDiffStrings.localized(.enUS).identical }, "identical images have an explicit state")
capture("identical", size: NSSize(width: 660, height: 430))
let small = before.cropping(to: CGRect(x: 0, y: 0, width: 200, height: 200))!
service.loadImage(write(small, name: "DifferentSize"), isBefore: false)
expect(until { summary() == strings[.sizeMismatch] }, "different dimensions are rejected without scaling")
expect(canvas().overlay == nil && !mode.isEnabled, "mismatch cannot retain a stale difference overlay")
capture("mismatch-small", size: NSSize(width: 660, height: 430))
service.loadImage(beforeURL, isBefore: false)
service.clear()
drain(0.4)
expect(canvas().before == nil && canvas().after == nil && canvas().overlay == nil, "clear cancels stale imports and comparisons")
Permissions.shared.screenRecording = false
button("captureBefore").performClick(nil)
expect(Permissions.shared.requested && summary() == strings[.permission], "capture explains missing permission")
Permissions.shared.screenRecording = true
let screen = NSScreen.screens[0]
let region = RecorderSupport.Region(displayID: screen.displayID, pixelRect: CGRect(x: 40, y: 40, width: 1000, height: 560), scale: screen.backingScaleFactor)
ScreenshotSelectionController.next = .region(region)
ScreenshotCaptureEngine.next = before
button("captureBefore").performClick(nil)
expect(until { service.hasPendingCapture && NotchService.shared.captureID != nil }, "Before exposes the island capture action")
expect(!window().isVisible && !NotchService.shared.takesFocus && !NotchService.shared.closesOnCollapse, "pending island capture leaves the target app usable")
expect(ScreenshotCaptureEngine.excludesIsland, "screen comparison capture excludes its own island")
expect(!ScreenshotCaptureEngine.hidesContentWindows && !ScreenshotSelectionController.hidesContentWindows,
    "other Vorssaint windows remain capturable for UI comparison")
expect(ScreenshotCaptureEngine.protectedIDs.contains(777) && ScreenshotCaptureEngine.protectedIDs.contains(CGWindowID(window().windowNumber)),
    "capture excludes only its own comparison panel and island")
ScreenshotCaptureEngine.next = after
service.captureAfter()
expect(NotchService.shared.captureID == nil, "After removes its island before sampling")
expect(until { canvas().overlay != nil && window().isVisible }, "After reopens the completed comparison")
expect(ScreenshotCaptureEngine.capturedRegion == region.pixelRect, "After uses the exact Before region")
expect(!service.hasPendingCapture, "completed pair clears pending state")
// A failed new Before must not pair old pixels with the newly selected region.
ScreenshotCaptureEngine.next = nil
service.captureBefore()
expect(until { summary() == strings[.captureFailed] }, "failed Before capture is reported")
expect(!service.hasPendingCapture && !button("captureAfter").isEnabled, "failed Before cannot retain a new region with old pixels")
// File import is a newer explicit source selection than a capture still in flight.
ScreenshotCaptureEngine.next = before
service.captureBefore()
expect(until { service.hasPendingCapture }, "capture race baseline is ready")
ScreenshotCaptureEngine.next = after
service.captureAfter()
service.loadImage(beforeURL, isBefore: false)
expect(until { summary() == ClipboardDiffStrings.localized(.enUS).identical }, "newer After file is accepted")
drain(0.4)
expect(summary() == ClipboardDiffStrings.localized(.enUS).identical, "older capture cannot replace a newer imported After")
ScreenshotCaptureEngine.next = before
service.captureBefore()
expect(until { service.hasPendingCapture }, "new Before starts a new pair")
service.cancelPendingCapture()
expect(!service.hasPendingCapture && canvas().before != nil && NotchService.shared.captureID == nil, "cancel retains Before while dismissing pending capture")
ScreenshotSelectionController.next = .region(RecorderSupport.Region(displayID: screen.displayID, pixelRect: region.pixelRect, scale: region.scale + 1))
service.captureBefore()
expect(until { service.hasPendingCapture }, "changed-scale fixture starts with a saved Before")
service.captureAfter()
expect(summary() == strings[.displayChanged] && !service.hasPendingCapture, "display scale change requires a new Before instead of clamping the region")
service.clear(); service.show()
service.receive(before, asBefore: true, name: "handoff-before")
service.receive(after, asBefore: false, name: "handoff-after")
expect(until { canvas().overlay != nil }, "direct image handoffs produce a comparison")
expect(canvas().before === before && canvas().after === after, "direct handoffs retain exact image identities on both sides")
service.receive(after, asBefore: true)
expect(until { window().attachedSheet != nil }, "replacing a nonempty different image requires confirmation")
expect(canvas().before === before && canvas().after === after, "opening replacement confirmation changes neither image")
window().endSheet(window().attachedSheet!, returnCode: .alertSecondButtonReturn)
expect(until { window().attachedSheet == nil }, "cancel closes replacement confirmation")
expect(canvas().before === before, "cancel keeps the target image")
service.receive(after, asBefore: true)
expect(until { window().attachedSheet != nil }, "feature-disable fixture opens confirmation")
AppFeature.enabled = false
window().endSheet(window().attachedSheet!, returnCode: .alertFirstButtonReturn)
drain()
expect(canvas().before === before && canvas().after === after, "disabling screenshot capture before confirming keeps both images")
AppFeature.enabled = true
service.receive(after, asBefore: true)
expect(until { window().attachedSheet != nil }, "replacement can be retried after cancellation")
window().endSheet(window().attachedSheet!, returnCode: .alertFirstButtonReturn)
expect(until { canvas().before === after }, "confirmed handoff replaces only the chosen side")
expect(canvas().after === after, "confirmed Before handoff preserves After")
service.receive(after, asBefore: true)
expect(window().attachedSheet == nil, "handing off the same image does not prompt again")
service.receive(before, asBefore: true)
expect(until { window().attachedSheet != nil }, "stale-target fixture opens confirmation")
let staleSheet = window().attachedSheet!
service.clear()
window().endSheet(staleSheet, returnCode: .alertFirstButtonReturn)
drain()
expect(canvas().before == nil && canvas().after == nil, "late confirmation cannot repopulate a cleared comparison")
service.loadImage(beforeURL, isBefore: true)
service.receive(after, asBefore: true)
service.loadImage(afterURL, isBefore: false)
expect(until { canvas().after != nil && canvas().overlay != nil }, "opposite-side import remains independent of a direct handoff")
drain(0.3)
expect(canvas().before === after, "older target-side import cannot overwrite the newer direct image")
capture("shared-handoff", size: NSSize(width: 660, height: 430))
service.show()
service.loadImage(afterURL, isBefore: false)
window().close()
drain(0.3)
service.show()
expect(canvas().before == nil && canvas().after == nil, "closing a completed session discards images and cancels delivery")
window().close()
AppFeature.enabled = false
service.show(); service.loadImage(beforeURL, isBefore: true); service.captureBefore()
expect(!window().isVisible, "disabled screenshot feature rejects all entry routes")
expect(NSPasteboard.general.changeCount == clipboardCount, "image comparison never mutates system clipboard")
expect((try! Data(contentsOf: beforeURL)) == original, "source file is unchanged")
print("PASS: \(checks) native screen comparison checks; screenshots /tmp/screen-compare-*.png")
'''
with tempfile.TemporaryDirectory(prefix='screen-compare-ui-') as directory:
    folder = Path(directory)
    main = folder / 'main.swift'
    main.write_text(fixture)
    executable = folder / 'check'
    sources = ['Core/ClipboardDiffStrings.swift', 'Core/ScreenCompareStrings.swift', 'Core/SharedToolActionStrings.swift', 'UI/ToolAppearance.swift',
               'Services/QuickTools/ScreenCompareModel.swift', 'Services/QuickTools/ScreenCompareService.swift',
               'UI/ScreenCompare/ScreenCompareView.swift']
    subprocess.run(['swiftc', *[str(repo / 'Sources/Vorssaint' / source) for source in sources], str(main), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=90)
