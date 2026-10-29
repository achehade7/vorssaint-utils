#!/usr/bin/env python3
"""Native local Compose rendering/lifecycle tests with temporary images and clipboard."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
model = (root / 'Sources/Vorssaint/Services/QuickTools/ComposeModel.swift').read_text()
controller = (root / 'Sources/Vorssaint/Services/QuickTools/ComposeController.swift').read_text().replace('NSPasteboard.general', 'testBoard')
fixture = r'''
let testBoard = NSPasteboard(name: NSPasteboard.Name("compose-tests-" + UUID().uuidString))
defer { testBoard.releaseGlobally() }
struct AppFeature { static let screenshot = AppFeature(); var isAvailable: Bool { true } }
struct RecentCaptureEntry: Identifiable {
    enum Kind { case screenshot, recording }
    let id = UUID()
    var kind = Kind.screenshot
    let createdAt = Date()
}
struct Capture { let image: CGImage }
final class RecentCaptureService: ObservableObject {
    static let shared = RecentCaptureService()
    @Published var entries: [RecentCaptureEntry] = []
    var callbacks: [(Capture?) -> Void] = []
    func screenshot(for entry: RecentCaptureEntry, completion: @escaping (Capture?) -> Void) { callbacks.append(completion) }
    func thumbnail(for entry: RecentCaptureEntry) -> NSImage? { nil }
}
var checks = 0
func expect(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
func wait(_ condition: () -> Bool) {
    let end = Date().addingTimeInterval(8)
    while !condition(), Date() < end { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
    expect(condition(), "async work completes")
}
func pixels(_ color: CGColor, width: Int = 120, height: Int = 80) -> CGImage {
    let c = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.setFillColor(color); c.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return c.makeImage()!
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let red = pixels(CGColor(red: 1, green: 0, blue: 0, alpha: 1))
let blue = pixels(CGColor(red: 0, green: 0, blue: 1, alpha: 1))
let items = [ComposeItem(image: red, name: "Before"), ComposeItem(image: blue, name: "After")]
let row = try ComposeRenderer.render(ComposeSnapshot(items: items, layout: .row))
let column = try ComposeRenderer.render(ComposeSnapshot(items: items, layout: .column))
let grid = try ComposeRenderer.render(ComposeSnapshot(items: items, layout: .grid))
expect(row.width == 1440 && row.height == grid.height && column.height > row.height * 2, "layouts retain aspect ratios and arrange images")
let bitmap = NSBitmapImageRep(cgImage: row)
expect(bitmap.colorAt(x: 64, y: 64)!.redComponent > 0.9 && bitmap.colorAt(x: 800, y: 64)!.blueComponent > 0.9,
       "row order and image pixels are preserved")
let reversed = try ComposeRenderer.render(ComposeSnapshot(items: items.reversed(), layout: .row))
expect(NSBitmapImageRep(cgImage: reversed).colorAt(x: 64, y: 64)!.blueComponent > 0.9, "reorder changes exported pixels")
let label = String(repeating: "A caption with enough text to wrap. ", count: 8)
var captioned = items
captioned[0].caption = label
let rich = try ComposeRenderer.render(ComposeSnapshot(items: captioned, layout: .grid, title: "Checkout issue", paragraph: "Expected result\nActual result"))
expect(rich.height > row.height + 100, "title, multiline paragraph and wrapped caption get space")

let steps = ComposeItem(image: nil, name: "Text", text: "1. Open the checkout page.\n2. Click Continue.")
let blocks = [items[0], steps, items[1]]
func colorRange(_ image: CGImage, red: Bool) -> ClosedRange<Int>? {
    let bitmap = NSBitmapImageRep(cgImage: image)
    let rows = (0..<image.height).filter { y in
        let color = bitmap.colorAt(x: image.width / 2, y: y)!
        return red ? color.redComponent > 0.9 && color.blueComponent < 0.1
            : color.blueComponent > 0.9 && color.redComponent < 0.1
    }
    guard let first = rows.first, let last = rows.last else { return nil }
    return first...last
}
for layout in ComposeLayout.allCases {
    let composed = try ComposeRenderer.render(ComposeSnapshot(items: blocks, layout: layout))
    let first = colorRange(composed, red: true)!, second = colorRange(composed, red: false)!
    expect(second.lowerBound - first.upperBound > 60, "text separates image groups in every layout")
    let emptyText = ComposeItem(image: nil, name: "Text", text: "  \n ")
    let plain = try ComposeRenderer.render(ComposeSnapshot(items: items, layout: layout))
    let empty = try ComposeRenderer.render(ComposeSnapshot(items: [items[0], emptyText, items[1]], layout: layout))
    expect(empty.height == plain.height, "empty text blocks do not create gaps or split rows")
}
var smaller = items[0]
smaller.sizePercent = 50
let normalImage = try ComposeRenderer.render(ComposeSnapshot(items: [items[0]], layout: .column))
let smallerImage = try ComposeRenderer.render(ComposeSnapshot(items: [smaller], layout: .column))
let normalRange = colorRange(normalImage, red: true)!, smallerRange = colorRange(smallerImage, red: true)!
expect(abs(normalRange.count - smallerRange.count * 2) <= 2, "50 percent size halves height without changing proportions")
let smallPixels = NSBitmapImageRep(cgImage: smallerImage)
expect(smallPixels.colorAt(x: 100, y: smallerImage.height / 2)!.blueComponent > 0.9
       && smallPixels.colorAt(x: smallerImage.width / 2, y: smallerImage.height / 2)!.redComponent > 0.9,
       "smaller image is centered with white space instead of stretched")
let independent = try ComposeRenderer.render(ComposeSnapshot(items: [smaller, items[1]], layout: .column))
// Moving a fractional-height rectangle can change one antialiased edge pixel.
expect(abs(colorRange(independent, red: false)!.count - colorRange(column, red: false)!.count) <= 1,
       "resizing one picture leaves the next picture at its original size")
let textOnly = try ComposeRenderer.render(ComposeSnapshot(items: [steps]))
expect(textOnly.height > 64, "text-only draft renders without a phantom image")
for percent in [0.0, 101.0, Double.nan, Double.infinity] {
    var bad = items[0]; bad.sizePercent = percent
    do { _ = try ComposeRenderer.render(ComposeSnapshot(items: [bad])); fatalError("invalid scale accepted") }
    catch { checks += 1 }
}
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
let file = folder.appendingPathComponent("source.png")
let original = try ComposeRenderer.png(red)
try original.write(to: file)
let loaded = try ComposeRenderer.load(file)
expect(loaded.width == red.width && loaded.height == red.height, "file import keeps ordinary image dimensions")
expect(try Data(contentsOf: file) == original, "source file is unchanged")
let rotatedFile = folder.appendingPathComponent("rotated.jpg")
let destination = CGImageDestinationCreateWithURL(rotatedFile as CFURL, "public.jpeg" as CFString, 1, nil)!
CGImageDestinationAddImage(destination, red, [kCGImagePropertyOrientation: 6] as CFDictionary)
expect(CGImageDestinationFinalize(destination), "orientation fixture written")
let rotated = try ComposeRenderer.load(rotatedFile)
expect(rotated.width == red.height && rotated.height == red.width, "EXIF orientation is applied on import")
let c = CGContext(data: nil, width: 100, height: 100, bitsPerComponent: 8, bytesPerRow: 0,
    space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
c.setFillColor(CGColor(red: 0, green: 0, blue: 1, alpha: 1)); c.fill(CGRect(x: 0, y: 0, width: 100, height: 100))
c.setFillColor(CGColor(red: 1, green: 0, blue: 0, alpha: 1)); c.fill(CGRect(x: 0, y: 50, width: 100, height: 50))
let oriented = try ComposeRenderer.render(ComposeSnapshot(items: [ComposeItem(image: c.makeImage()!, name: "Top red")]))
let orientedPixels = NSBitmapImageRep(cgImage: oriented)
expect(orientedPixels.colorAt(x: 100, y: 100)!.redComponent > 0.9
       && orientedPixels.colorAt(x: 100, y: oriented.height - 100)!.blueComponent > 0.9,
       "composition does not vertically flip screenshots")
let export = try ComposeRenderer.png(rich)
try export.write(to: folder.appendingPathComponent("composed.png"))
expect(NSBitmapImageRep(data: export)?.pixelsWide == 1440, "PNG export has full output resolution")
for invalid in [ComposeSnapshot(items: []), ComposeSnapshot(items: Array(repeating: items[0], count: 13)),
                ComposeSnapshot(items: items, width: 100),
                ComposeSnapshot(items: [ComposeItem(image: pixels(CGColor(gray: 0, alpha: 1), width: 1, height: 100), name: "Tall")])] {
    do { _ = try ComposeRenderer.render(invalid); fatalError("unsafe output was accepted") }
    catch { checks += 1 }
}
let model = ComposeController()
model.items = items
wait { model.canExport }
model.move(items[0].id, before: items[1].id)
wait { model.canExport }
expect(model.items.map(\.id) == [items[1].id, items[0].id], "reorder preserves identities and captions")
model.title = "Latest title"
expect(!model.canExport, "edits disable export until current rendering finishes")
wait { model.canExport }
model.copy()
expect(testBoard.data(forType: .png) != nil && testBoard.string(forType: .fileURL) == nil, "Copy writes an image with no file attachment")
model.clear()
expect(model.items.isEmpty && model.preview == nil && model.title.isEmpty, "Clear resets the composition")
model.addRecent(RecentCaptureEntry())
expect(model.pending == 1 && !model.canExport, "pending recent capture blocks export")
model.clear()
RecentCaptureService.shared.callbacks.removeFirst()(Capture(image: red))
expect(model.items.isEmpty && model.pending == 0, "late recent capture cannot enter a cleared draft")
model.addFiles([file, file]); wait { model.pending == 0 && model.canExport }
expect(model.items.count == 2 && model.items[0].id != model.items[1].id, "ordered file batch uses separate stable identities")
model.addRecent(RecentCaptureEntry())
RecentCaptureService.shared.callbacks.removeFirst()(nil)
expect(model.pending == 0 && model.items.count == 2 && model.message != nil, "missing capture reports failure without losing content")
model.clear()
testBoard.clearContents(); testBoard.setData(original, forType: .png)
model.paste(); wait { model.canExport }
expect(model.items.count == 1, "image paste imports pixels")
model.addFiles([folder.appendingPathComponent("missing.png")]); wait { model.pending == 0 }
expect(model.items.count == 1, "failed file import preserves existing images")
model.clear()
let provider = NSItemProvider(item: file.absoluteString.data(using: .utf8)! as NSData, typeIdentifier: UTType.fileURL.identifier)
expect(model.acceptDrop([provider]), "file drop is accepted")
wait { model.pending == 0 && model.canExport }
expect(model.items.count == 1, "file drop imports the image")
model.items = Array(repeating: items[0], count: ComposeRenderer.imageLimit)
model.addFiles([file])
expect(model.pending == 0 && model.items.count == ComposeRenderer.imageLimit, "image count limit is enforced before loading")
model.clear()

model.items = items
model.addText()
let textID = model.items.last!.id
model.items[2].text = steps.text
model.move(textID, before: items[1].id)
expect(model.items.map(\.id) == [items[0].id, textID, items[1].id] && model.imageCount == 2,
       "text moves independently between pictures and is not counted as an image")
model.items[0].sizePercent = 50
wait { model.canExport }
model.items[1].text += "\n3. Check the result."
expect(!model.canExport, "editing steps invalidates the old preview")
wait { model.canExport }
model.items.removeAll { $0.id == textID }
expect(model.items.count == 2 && model.items[0].sizePercent == 50 && model.items[0].id == items[0].id,
       "removing text preserves image identity and custom size")
model.clear()
model.items = items; model.title = "Checkout issue"; model.paragraph = "Expected result\nActual result"
wait { model.canExport }
model.show()
let window = app.windows.first { $0.title == "Compose" }!
expect(window.contentView != nil && window.minSize.width >= 760, "Compose opens its native editor")
RunLoop.main.run(until: Date().addingTimeInterval(0.3))
if let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
    view.cacheDisplay(in: view.bounds, to: bitmap)
    try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("window.png"))
}
window.orderOut(nil)
try ComposeRenderer.png(ComposeRenderer.render(ComposeSnapshot(items: [smaller, steps, items[1]], layout: .column, title: "Steps between screenshots"))).write(to: URL(fileURLWithPath: "/tmp/vorssaint-compose-preview.png"))
try? Data(contentsOf: folder.appendingPathComponent("window.png")).write(to: URL(fileURLWithPath: "/tmp/vorssaint-compose-window.png"))
print("PASS: \(checks) Compose rendering, import, clipboard, lifecycle and native-window checks")
'''
with tempfile.TemporaryDirectory(prefix='compose-tests-') as temporary:
    folder = Path(temporary)
    path = folder / 'main.swift'
    path.write_text(model + '\n' + controller + '\n' + fixture)
    binary = folder / 'test'
    subprocess.run(['xcrun', 'swiftc', '-target', 'arm64-apple-macosx14.0', '-sdk', '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk', '-Xfrontend', '-interface-compiler-version', '-Xfrontend', '6.3.2', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(folder)], check=True, env={**os.environ, 'CFFIXED_USER_HOME': str(folder / 'preferences')})
