#!/usr/bin/env python3
# Exercise production screenshot arrival handling against the native Spotlight
# index in an isolated Pictures folder. No screen capture or user files are read.
from pathlib import Path
import tempfile,subprocess,shutil
repo=Path(__file__).resolve().parents[1]
folder=Path(tempfile.mkdtemp(prefix='island-inbox-probe-'))
(folder/'Inbox.swift').write_text((repo/'Sources/Vorssaint/Services/Notch/NotchScreenshotInbox.swift').read_text().replace('UserDefaults(suiteName:', 'InboxDefaults(suiteName:'))
(folder/'main.swift').write_text(r'''
import AppKit
import ImageIO
let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Pictures/Island Inbox Test \(UUID().uuidString)")
try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
defer { NotchScreenshotInbox.shared.stop(); try? FileManager.default.removeItem(at: dir) }
struct InboxDefaults {
 init?(suiteName: String) {}
 func string(forKey: String) -> String? { dir.path }
}
enum Event { case capture }
enum NotchSupport { static func routes(_ event: Event) -> Bool { true } }
enum ScreenshotSupport {
 static let recentCaptureLimit = 12
 static func confirmationPreviewDismissInterval() -> TimeInterval? { 3 }
}
class NotchService { static let shared = NotchService(); var acceptsSystemFeedback = true }
enum ScreenshotSelectionController { struct Capture { let image: CGImage; let scale: CGFloat; let anchorRect: CGRect } }
class RecentCaptureService {
 static let shared = RecentCaptureService()
 var recorded: [UUID] = []
 func recordScreenshot(_ capture: ScreenshotSelectionController.Capture) -> UUID {
  let id = UUID(); recorded.append(id); return id
 }
}
class ScreenshotService {
 static let shared = ScreenshotService()
 var arrivals = 0
 func restorePreview(_ capture: ScreenshotSelectionController.Capture, historyID: UUID?, dismissInterval: TimeInterval?) {
  precondition(dismissInterval == 3)
  precondition(historyID != nil && RecentCaptureService.shared.recorded.contains(historyID!))
  arrivals += 1
 }
}
func save(_ name: String, owned: Bool = false) throws {
 let image = NSBitmapImageRep(bitmapDataPlanes:nil, pixelsWide:8, pixelsHigh:8, bitsPerSample:8, samplesPerPixel:4,
 hasAlpha:true, isPlanar:false, colorSpaceName:.deviceRGB, bytesPerRow:0, bitsPerPixel:0)!
 let url = dir.appendingPathComponent(name + ".png")
 try image.representation(using:.png,properties:[:])!.write(to:url)
 if owned { try url.setExtendedAttribute("com.vorssaint.capture", data: Data([1])) }
 let marker = try PropertyListSerialization.data(fromPropertyList:true,format:.binary,options:0)
 try url.setExtendedAttribute("com.apple.metadata:kMDItemIsScreenCapture",data:marker)
 let task = Process();task.executableURL = URL(fileURLWithPath:"/usr/bin/mdimport");task.arguments=[url.path]
 try task.run();task.waitUntilExit()
}
extension URL {
 func setExtendedAttribute(_ name: String, data: Data) throws {
  let result = data.withUnsafeBytes { setxattr(path,name,$0.baseAddress,data.count,0,0) }
  precondition(result == 0)
 }
}
func spin(_ seconds:Double) { RunLoop.main.run(until:Date().addingTimeInterval(seconds)) }
try save("old")
spin(1)
NotchScreenshotInbox.shared.start()
spin(1)
precondition(ScreenshotService.shared.arrivals == 0, "old captures must stay silent")
try save("native")
let deadline = Date().addingTimeInterval(15)
while ScreenshotService.shared.arrivals == 0 && Date() < deadline { spin(0.1) }
guard ScreenshotService.shared.arrivals == 1 else { print("FAIL: no indexed native screenshot delivery"); exit(1) }
try save("burst-a"); try save("burst-b"); try save("burst-c")
let burstDeadline = Date().addingTimeInterval(15)
while RecentCaptureService.shared.recorded.count < 4 && Date() < burstDeadline { spin(0.1) }
precondition(RecentCaptureService.shared.recorded.count == 4, "a screenshot burst must keep every image in history")
let deliveries = ScreenshotService.shared.arrivals
try save("owned", owned:true); spin(2)
precondition(ScreenshotService.shared.arrivals == deliveries && RecentCaptureService.shared.recorded.count == 4,
 "owned capture duplicated")
NotchService.shared.acceptsSystemFeedback = false
try save("quiet");spin(2)
precondition(ScreenshotService.shared.arrivals == deliveries && RecentCaptureService.shared.recorded.count == 4,
 "quiet capture must stay silent")
print("Screenshot inbox: burst retention, native metadata arrival, old-file exclusion, owned-file deduplication and quiet suppression passed")
''')
subprocess.run(['swiftc','-sdk','/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk',str(folder/'Inbox.swift'),str(folder/'main.swift'),'-o',str(folder/'probe')],check=True)
print(folder,flush=True)
subprocess.run([str(folder/'probe')],check=True)

shutil.rmtree(folder)
