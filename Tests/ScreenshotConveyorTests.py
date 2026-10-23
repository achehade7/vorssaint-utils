#!/usr/bin/env python3
"""Run the production async browse handler against controlled cache completions."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/QuickTools/ScreenshotQuickPreviewController.swift").read_text()
start = source.index("    private func browse(_ entry:")
opening = source.index("{", start)
depth = 1
end = opening + 1
while depth:
    if source[end] == "{":
        depth += 1
    elif source[end] == "}":
        depth -= 1
    end += 1
handler = source[start:end].replace("private func", "func", 1)
harness = r'''
import Foundation
struct RecentCaptureEntry { let id = UUID() }
struct Capture { let number: Int }
class RecentCaptureService {
 static let shared = RecentCaptureService()
 var pending: [(Capture?) -> Void] = []
 func screenshot(for entry: RecentCaptureEntry, completion: @escaping (Capture?) -> Void) {
  pending.append(completion)
 }
}
class NotchService {
 static let shared = NotchService()
 var visible = true
 func isCaptureVisible(id: UUID) -> Bool { visible }
}
class ScreenshotService {
 static let shared = ScreenshotService()
 var opened: [UUID] = []
 func restorePreview(_ capture: Capture, historyID: UUID?) { opened.append(historyID!) }
}
class Model { var sharing = false }
class Controller {
 var closed = false, shownInNotch = true, browsingHistory = false, systemSharing = false, showingActions = false
 let historyID = UUID(), presentationID = UUID(), model = Model()
HANDLER
}
func reset() {
 RecentCaptureService.shared.pending.removeAll()
 ScreenshotService.shared.opened.removeAll()
 NotchService.shared.visible = true
}
let target = RecentCaptureEntry()
reset()
let active = Controller()
active.browse(target); active.browse(RecentCaptureEntry())
precondition(RecentCaptureService.shared.pending.count == 1, "only one image load may be pending")
RecentCaptureService.shared.pending.removeFirst()(Capture(number: 1))
precondition(ScreenshotService.shared.opened == [target.id] && !active.browsingHistory,
 "loaded image must reopen the selected capture identity")
reset()
let dismissed = Controller()
dismissed.browse(target); dismissed.closed = true
RecentCaptureService.shared.pending.removeFirst()(Capture(number: 2))
precondition(ScreenshotService.shared.opened.isEmpty, "outside-click must not be undone by delayed image loading")
reset()
let replaced = Controller()
replaced.browse(target); NotchService.shared.visible = false
RecentCaptureService.shared.pending.removeFirst()(Capture(number: 3))
precondition(ScreenshotService.shared.opened.isEmpty, "older load must not replace a newer capture")
reset()
let failed = Controller()
failed.browse(target)
RecentCaptureService.shared.pending.removeFirst()(nil)
precondition(ScreenshotService.shared.opened.isEmpty && !failed.browsingHistory,
 "a missing cache image must leave current preview intact and permit retry")
failed.browse(target)
precondition(RecentCaptureService.shared.pending.count == 1)
reset()
let sharing = Controller()
sharing.model.sharing = true; sharing.browse(target)
sharing.model.sharing = false; sharing.systemSharing = true; sharing.browse(target)
precondition(RecentCaptureService.shared.pending.isEmpty, "sharing must hold its current capture")
sharing.systemSharing = false; sharing.showingActions = true; sharing.browse(target)
precondition(RecentCaptureService.shared.pending.isEmpty, "shared actions must retain their immutable source capture")
print("Screenshot conveyor: selection, single pending load, click-away race, replacement race, missing image and share protection passed")
'''
with tempfile.TemporaryDirectory(prefix="island-conveyor-test-") as temporary:
    folder = Path(temporary)
    (folder / "main.swift").write_text(harness.replace("HANDLER", handler))
    subprocess.run(["swiftc", str(folder / "main.swift"), "-o", str(folder / "probe")], check=True)
    subprocess.run([str(folder / "probe")], check=True)
