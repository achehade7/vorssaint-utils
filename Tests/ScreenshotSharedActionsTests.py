#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise production preview ownership/annotation routing without windows or clipboard access."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

repo = Path(__file__).resolve().parents[1]
source = "Sources/Vorssaint/Services/QuickTools/ScreenshotQuickPreviewController.swift"
fixture = r'''
import Foundation
import CoreGraphics
final class NSWindow {
    var isVisible = true
    var attachedSheet: NSWindow?
    func orderOut(_ sender: Any?) { isVisible = false }
}
enum NSEvent { static func removeMonitor(_ monitor: Any) {} }
enum AppFeature { case screenshot; static var enabled = true; var isAvailable: Bool { Self.enabled } }
final class NotchService {
    static let shared = NotchService()
    var visible = true
    var presentationWindow: NSWindow? = NSWindow()
    var removed: [UUID] = []
    func isCaptureVisible(id: UUID) -> Bool { visible }
    func removeCapture(id: UUID) { removed.append(id) }
}
enum SharedToolActions {
    enum Content { case image(Int) }
    struct Request {
        let image: Int; let owner: UUID; let window: NSWindow
        let onAnnotate: (() -> Void)?; let onClose: () -> Void
    }
    static var requests: [Request] = []
    static var cancelled: [UUID] = []
    static func present(content: Content, title: String, from: NSWindow, owner: UUID,
                        onAnnotate: (() -> Void)? = nil, onClose: @escaping () -> Void) {
        guard case let .image(image) = content else { return }
        requests.append(Request(image: image, owner: owner, window: from,
                                onAnnotate: onAnnotate, onClose: onClose))
    }
    static func cancel(owner: UUID) { cancelled.append(owner) }
}
final class Controller {
    enum Action: Hashable { case edit }
    struct Capture { let image: Int }
    struct Model { var sharing = false; var deletingShare = false; var disabledActions: Set<Action> = [] }
    struct Strings { let pageTitle = "Screenshot" }
    let capture = Capture(image: 42)
    let strings = Strings()
    let actionsOwner = UUID()
    let presentationID = UUID()
    var model = Model()
    var panel: NSWindow? = NSWindow()
    var keyMonitor: Any?
    var dismissWork: DispatchWorkItem? = DispatchWorkItem {}
    var showingActions = false
    var closed = false
    var systemSharing = false
    var browsingHistory = false
    var shownInNotch = false
    var scheduled = 0
    var closedCalls = 0
    var edited = 0
    lazy var action: (Action) -> String = { [weak self] _ in self?.edited += 1; return "done" }
    func onClose() { closedCalls += 1 }
    func scheduleAutoDismiss() { scheduled += 1 }
'''
fixture += "".join(declaration(source, prefix).replace("private func", "func", 1) for prefix in [
    "    func close()", "    private func showActions()", "    private func perform(_ requested:"])
fixture += "}\nenum ExternalAnnotation {\n" + r'''
final class CGImage {
    let width: Int; let height: Int
    init(_ width: Int, _ height: Int) { self.width = width; self.height = height }
}
enum ScreenshotSupport { static let scrollingCaptureMaximumPixels = 1_000_000 }
enum ScreenshotSelectionController {
    struct Capture { let image: CGImage; let scale: Int; let anchorRect: CGRect }
}
final class Service {
    var received: ScreenshotSelectionController.Capture?
    var withholds: Bool?
    func openEditor(with capture: ScreenshotSelectionController.Capture, withholdingLatestCapture: Bool = true) {
        received = capture; withholds = withholdingLatestCapture
    }
'''
fixture += declaration("Sources/Vorssaint/Services/QuickTools/ScreenshotService.swift", "    func annotate(_ image:")
fixture += r'''
}
}
var checks = 0
func expect(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
let source = Controller()
let oldDismiss = source.dismissWork!
source.showActions()
expect(source.showingActions && oldDismiss.isCancelled && source.dismissWork == nil, "menu pauses preview timeout")
expect(SharedToolActions.requests.count == 1, "menu opens once")
let request = SharedToolActions.requests.last!
expect(request.image == 42 && request.owner == source.actionsOwner && request.window === source.panel, "menu owns exact immutable image and source window")
source.showActions()
expect(SharedToolActions.requests.count == 1, "repeat invocation does not replace active menu")
request.onClose()
expect(!source.showingActions && source.scheduled == 1, "menu dismissal resumes preview lifetime")
source.showActions()
let edit = SharedToolActions.requests.last!
edit.onClose()
edit.onAnnotate?()
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
expect(source.closed && source.edited == 1 && source.closedCalls == 1, "annotation reuses source-bound Edit after menu closes")
expect(SharedToolActions.cancelled.last == source.actionsOwner, "preview close cancels only its own pending menu")
let scheduled = source.scheduled
edit.onClose(); edit.onAnnotate?(); source.close(); source.showActions()
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
expect(source.scheduled == scheduled && source.edited == 1 && source.closedCalls == 1, "late menu callbacks cannot reopen or edit a closed preview")
for gate in 0..<8 {
    let controller = Controller()
    switch gate {
    case 0: controller.model.sharing = true
    case 1: controller.systemSharing = true
    case 2: controller.model.deletingShare = true
    case 3: controller.browsingHistory = true
    case 4: controller.panel?.isVisible = false
    case 5: controller.panel?.attachedSheet = NSWindow()
    case 6: AppFeature.enabled = false
    default: controller.shownInNotch = true; NotchService.shared.visible = false
    }
    let count = SharedToolActions.requests.count
    controller.showActions()
    expect(SharedToolActions.requests.count == count && !controller.showingActions,
           "source availability and interaction guard \(gate) prevents handoff")
    AppFeature.enabled = true; NotchService.shared.visible = true
}
let island = Controller(); island.shownInNotch = true
island.showActions()
expect(SharedToolActions.requests.last?.window === NotchService.shared.presentationWindow, "visible island preview anchors menu to its presentation window")
island.close()
expect(NotchService.shared.removed.last == island.presentationID, "closing island source removes the same capture")
let external = ExternalAnnotation.Service()
let externalImage = ExternalAnnotation.CGImage(120, 80)
external.annotate(externalImage)
expect(external.received?.image === externalImage && external.withholds == false,
       "external annotation forwards exact image without withholding unrelated latest capture")
expect(external.received?.anchorRect == CGRect(x: 0, y: 0, width: 120, height: 80),
       "external image annotation uses source image dimensions")
external.received = nil
external.annotate(ExternalAnnotation.CGImage(0, 80))
external.annotate(ExternalAnnotation.CGImage(2_000, 2_000))
expect(external.received == nil, "invalid or oversized external image does not open an editor")
AppFeature.enabled = false
external.annotate(externalImage)
expect(external.received == nil, "disabled screenshot feature rejects external annotation")
print("PASS: \(checks) screenshot shared action ownership checks")
'''
with tempfile.TemporaryDirectory(prefix="screenshot-shared-actions-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(fixture)
    executable = folder / "checks"
    subprocess.run(["swiftc", str(main), "-o", str(executable)], check=True, cwd=repo)
    subprocess.run([str(executable)], check=True, timeout=20, cwd=repo)
