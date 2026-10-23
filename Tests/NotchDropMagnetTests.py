#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production drag geometry and destination routing without native input."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
service = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()
magnet = (repo / "Sources/Vorssaint/UI/Notch/NotchDropMagnet.swift").read_text()
canvas = (repo / "Sources/Vorssaint/Services/Notch/NotchWindowHost.swift").read_text()


def declaration(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end]


handlers = "\n".join(declaration(service, marker) for marker in [
    "    var canAcceptFileDrop:", "    func beginFileDrop(", "    func updateFileDrop(",
    "    func fileDropEmphasis(", "    func endFileDrop()", "    func accept(_ pasteboard:",
])
swift = r'''
import AppKit
import SwiftUI
MAGNET
DROP_ACTIONS
enum NotchModule { case files }
enum Reaction { case celebrate }
enum AppFeature {
    struct Feature { var isAvailable = true }
    static var shelf = Feature()
}
enum DefaultsKey { static let shelfEnabled = "shelf" }
enum UserDefaults {
    static let standard = Store()
    final class Store {
        var enabled = true
        func bool(forKey: String) -> Bool { enabled }
    }
}
enum NotchAeroSpaceState { static let workspaces = ["1", "2", "G", "P"] }
final class NotchAeroSpaceService {
    static let shared = NotchAeroSpaceService()
    struct State { var current: String? = "1" }
    var state = State()
    var selections: [String] = []
    func select(_ workspace: String) { selections.append(workspace) }
}
enum NotchFileToolsSupport {
    static func mediaDropArea(in: Int, size: CGSize) -> CGRect {
        CGRect(x: 226, y: 50, width: 190, height: 150)
    }
}
final class NotchFileToolsService {
    static let shared = NotchFileToolsService()
    var compatible = false, canAcceptMediaDrop = true
    var optimizations = 0
    func mediaDropContent(for: NSPasteboard) -> Int? { compatible ? 1 : nil }
    func openMediaDrop(_ pasteboard: NSPasteboard) -> Bool {
        guard compatible, canAcceptMediaDrop else { return false }
        optimizations += 1; return true
    }
    func hideMedia() {}
}
final class ShelfService {
    static let shared = ShelfService()
    var deliveries = 0
    func acceptDrop(pasteboard: NSPasteboard) -> Bool { deliveries += 1; return true }
}
enum ClipboardFileDiff { enum Side: String, CaseIterable { case before, after } }
final class ClipboardFileDiffService {
    static let shared = ClipboardFileDiffService()
    var compatible = false
    var deliveries: [ClipboardFileDiff.Side] = []
    func files(from: NSPasteboard) -> [URL]? { compatible ? [URL(fileURLWithPath: "/tmp/config.json")] : nil }
    func accept(_ board: NSPasteboard, side: ClipboardFileDiff.Side) -> Bool {
        guard compatible else { return false }
        deliveries.append(side); return true
    }
}
final class Service {
    var acceptsUserInteraction = true, displayIsFullscreen = false
    var captureControls: Int?
    var modules: [NotchModule] = [.files]
    var fileDropActive = false
    var fileDropPoint: CGPoint?
    var routingFileDrag = false, choosingFileDropDestination = false, targetsMediaDrop = false
    var offeringFileDiff = false
    var fileDiffTarget: ClipboardFileDiff.Side?
    var fileDiffDropFrames: [ClipboardFileDiff.Side: CGRect] = [
        .before: CGRect(x: 20, y: 70, width: 190, height: 100),
        .after: CGRect(x: 230, y: 70, width: 190, height: 100)]
    var dragTargetWorkspace: String?
    var workspaceDropFrames = ["G": CGRect(x: 30, y: 5, width: 22, height: 26)]
    var workspaceDragWork: DispatchWorkItem?
    var expandedGeometry = 0
    var surfaceSize = CGSize(width: 440, height: 240)
    var heldDrag = false, dragPlaceholder = false
    var opens = 0, refreshes = 0
    func open(_ module: NotchModule, takeFocus: Bool = true) { opens += 1 }
    func refreshPresentation() { refreshes += 1 }
    func reactMascot(_ reaction: Reaction, patience: TimeInterval) {}
    HANDLERS
}
final class Canvas {
    var acceptingDrag = false
    var dropActions: NotchFileDropActions?
    CANVAS
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    precondition(condition, message)
}
let target = CGRect(x: 100, y: 50, width: 100, height: 100)
func strength(_ x: CGFloat, _ y: CGFloat, available: Bool = true) -> Double {
    NotchDropMagnet.strength(at: CGPoint(x: x, y: y), in: target, reach: 90, available: available)
}
expect(strength(150, 100) == 1 && strength(100, 50) == 1, "inside and boundary points receive full emphasis")
expect(strength(75, 100) > strength(50, 100) && strength(50, 100) > strength(0, 100),
       "the same target becomes brighter as a pointer approaches its edge")
expect(strength(75, 100) == strength(225, 100), "left and right approach distances are symmetrical")
expect(strength(150, 25) == strength(75, 100), "vertical approach uses the same geometry")
expect(strength(75, 25) < strength(75, 100), "diagonal proximity uses the actual corner distance")
expect(strength(-1000, 100) == 0.12, "far compatible destinations retain only a quiet base glow")
expect(strength(150, 100, available: false) == 0, "unsupported destinations never glow, even under the pointer")
expect(NotchDropMagnet.strength(at: nil, in: target, reach: 90, available: true) == 0,
       "no current drag means no persistent decorative glow")
for frame in [CGRect.null, .infinite, .zero, CGRect(x: CGFloat.infinity, y: 0, width: 100, height: 100)] {
    expect(NotchDropMagnet.strength(at: .zero, in: frame, reach: 90, available: true) == 0,
           "unmeasured and invalid targets stay dark")
}
expect(strength(.nan, 100) == 0, "invalid pointer coordinates never produce invalid rendering values")
expect(NotchDropMagnet.strength(at: .zero, in: target, reach: 0, available: true) == 0,
       "invalid reach cannot divide by zero")
let translated = target.offsetBy(dx: 500, dy: -300)
expect(NotchDropMagnet.strength(at: CGPoint(x: 575, y: -200), in: translated, reach: 90, available: true)
       == strength(75, 100), "display placement cannot change local drop emphasis")
let board = NSPasteboard.withUniqueName()
defer { board.releaseGlobally() }
board.setString("file:///tmp/example.png", forType: .fileURL)
let service = Service(), files = NotchFileToolsService.shared, shelf = ShelfService.shared
let mediaPoint = CGPoint(x: 300, y: 110), shelfPoint = CGPoint(x: 100, y: 110)
expect(!service.updateFileDrop(at: shelfPoint) && service.fileDropPoint == nil,
       "ordinary pointer movement cannot activate magnetic feedback")
let native = Canvas()
var payloadSupported = false
native.dropActions = NotchFileDropActions(canAccept: { _ in payloadSupported && service.canAcceptFileDrop },
    enter: { service.beginFileDrop($0) }, accept: { service.accept($0) }, exit: { service.endFileDrop() })
expect(native.beginDrop(board, localSource: false) == [] && service.fileDropPoint == nil && service.opens == 0,
       "unsupported native payloads never open or light a destination")
payloadSupported = true
expect(native.beginDrop(board, localSource: true) == [] && service.opens == 0,
       "internal shelf drags keep their existing reorder and merge interaction")
expect(native.beginDrop(board, localSource: false) == .copy && service.opens == 1,
       "an accepted external file enters the existing Files destination")
expect(service.updateFileDrop(at: shelfPoint) && service.fileDropPoint == shelfPoint,
       "the existing native drag update supplies the sole pointer position")
expect(service.fileDropEmphasis(in: target) > 0 && service.fileDropEmphasis(in: target, available: false) == 0,
       "availability gates every target independently")
expect(native.finishDrop(board) && shelf.deliveries == 1 && files.optimizations == 0,
       "a normal file still reaches the shelf once")
expect(service.fileDropPoint == nil && !service.fileDropActive && service.fileDropEmphasis(in: target) == 0,
       "successful completion removes all drag decoration")
for fullscreen in [false, true] {
    service.displayIsFullscreen = fullscreen
    files.compatible = true
    service.beginFileDrop(board)
    expect(service.choosingFileDropDestination && service.updateFileDrop(at: mediaPoint),
           "compatible media retains its existing destination on desktop and fullscreen")
    expect(service.targetsMediaDrop && service.fileDropEmphasis(in: target) > 0,
           "fullscreen does not disable the open drag UI's magnetic emphasis")
    let prior = files.optimizations
    expect(service.accept(board) && files.optimizations == prior + 1,
           "the selected media target retains its existing optimization action")
}
files.canAcceptMediaDrop = false
service.beginFileDrop(board)
expect(!service.updateFileDrop(at: mediaPoint) && service.targetsMediaDrop,
       "an unavailable media target remains rejected by existing routing")
expect(service.fileDropEmphasis(in: target, available: files.canAcceptMediaDrop) == 0,
       "a busy optimizer stays dark instead of promising admission")
let priorDeliveries = shelf.deliveries
expect(!service.accept(board) && shelf.deliveries == priorDeliveries,
       "rejected optimization never silently shelves the file")
service.beginFileDrop(board)
expect(service.updateFileDrop(at: shelfPoint) && service.accept(board) && shelf.deliveries == priorDeliveries + 1,
       "the same drag can still use the available shelf destination")
files.canAcceptMediaDrop = true
service.beginFileDrop(board)
expect(!service.updateFileDrop(at: CGPoint(x: 40, y: 15)) && service.dragTargetWorkspace == "G",
       "workspace numbers remain spring-loaded routes rather than file storage")
expect(service.fileDropEmphasis(in: service.workspaceDropFrames["G"]!, reach: 32) == 1,
       "the hovered workspace receives the strongest route emphasis")
let pendingWorkspace = service.workspaceDragWork
expect(!service.accept(board) && pendingWorkspace?.isCancelled == true && service.fileDropPoint == nil,
       "releasing on a workspace neither stores the file nor leaves its delayed switch active")
service.beginFileDrop(board)
_ = service.updateFileDrop(at: shelfPoint)
service.acceptsUserInteraction = false
expect(service.fileDropEmphasis(in: target) == 0,
       "locking or otherwise disabling island interaction immediately removes target emphasis")
expect(!service.updateFileDrop(at: shelfPoint) && service.fileDropPoint == nil && !service.fileDropActive,
       "a lock transition cancels the active native drag route")
service.beginFileDrop(board)
expect(!service.fileDropActive && !service.accept(board), "the noninteractive lock island cannot begin or accept a file drop")
service.acceptsUserInteraction = true
service.beginFileDrop(board)
expect(!service.updateFileDrop(at: CGPoint(x: CGFloat.nan, y: 0)) && service.fileDropPoint == nil,
       "invalid native coordinates terminate feedback without routing a file")
service.beginFileDrop(board)
_ = service.updateFileDrop(at: shelfPoint)
service.endFileDrop()
expect(service.fileDropPoint == nil && !service.routingFileDrag && !service.choosingFileDropDestination,
       "leaving the island clears both magnetic decoration and the prior routing state")
files.compatible = false
let diff = ClipboardFileDiffService.shared
diff.compatible = true
for (side, point) in [(ClipboardFileDiff.Side.before, shelfPoint), (.after, mediaPoint)] {
    let previousShelf = shelf.deliveries
    service.beginFileDrop(board)
    expect(service.offeringFileDiff && service.updateFileDrop(at: point) && service.fileDiffTarget == side,
           "text files expose the precise measured Before/After target")
    expect(service.accept(board) && diff.deliveries.last == side && shelf.deliveries == previousShelf,
           "dropping on a comparison side routes there without storing a shelf copy")
    expect(!service.offeringFileDiff && service.fileDiffTarget == nil,
           "comparison drop completion clears transient target state")
}
let previousShelf = shelf.deliveries, previousDiff = diff.deliveries.count
service.beginFileDrop(board)
expect(service.updateFileDrop(at: CGPoint(x: 100, y: 200)) && service.fileDiffTarget == nil,
       "the shelf area stays available while text comparison targets are offered")
expect(service.accept(board) && shelf.deliveries == previousShelf + 1 && diff.deliveries.count == previousDiff,
       "explicit shelf drop never starts a comparison")
service.beginFileDrop(board)
_ = service.updateFileDrop(at: mediaPoint)
expect(!service.updateFileDrop(at: CGPoint(x: 40, y: 15)) && !service.accept(board),
       "moving from comparison target to a workspace cannot accidentally compare")
print("NotchDropMagnetTests: \(checks) checks passed")
'''
swift = swift.replace("MAGNET", declaration(magnet, "enum NotchDropMagnet"))
swift = swift.replace("DROP_ACTIONS", declaration(canvas, "struct NotchFileDropActions"))
swift = swift.replace("HANDLERS", handlers)
swift = swift.replace("CANVAS", declaration(canvas, "    func beginDrop(") + "\n" + declaration(canvas, "    func finishDrop("))
with tempfile.TemporaryDirectory(prefix="notch-drop-magnet-") as temporary:
    folder = Path(temporary)
    path, binary = folder / "main.swift", folder / "tests"
    path.write_text(swift)
    subprocess.run(["xcrun", "swiftc", str(path), "-o", str(binary)], check=True, cwd=repo)
    subprocess.run([str(binary)], check=True, cwd=repo)
