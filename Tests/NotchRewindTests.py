#!/usr/bin/env python3
"""Exercise the production rewind route without posting native input events."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
service = (repo / "Sources/Vorssaint/Services/Notch/NotchService.swift").read_text()
support = (repo / "Sources/Vorssaint/Services/Notch/NotchSupport.swift").read_text()
notifications = (repo / "Sources/Vorssaint/Services/Notch/NotchNotificationSupport.swift").read_text()
scroll = (repo / "Sources/Vorssaint/Services/Notch/NotchSectionPaging.swift").read_text()


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


production = "\n".join([
    declaration(notifications, "struct NotchNotificationContent:"),
    declaration(notifications, "struct NotchSystemNotification:"),
    declaration(notifications, "enum NotchNotificationRewind {"),
    declaration(support, "struct NotchHoverState {"),
    declaration(scroll, "struct NotchSectionScroll {"),
])
handlers = "\n".join(
    declaration(service, marker).replace("private func", "func", 1)
    for marker in [
        "    private func handleRewindScroll(",
        "    private func settleNotificationHover(",
    ]
)
layout = "\n".join(
    line for line in support.splitlines()
    if "static let sectionTileHeight:" in line or "static let sectionSpacing:" in line
)
harness = r'''
import Foundation
import CoreGraphics
enum NotchLayout {
LAYOUT
}
PRODUCTION
struct NSEvent {
 struct ModifierFlags: OptionSet {
  let rawValue: Int
  static let command = Self(rawValue: 1), control = Self(rawValue: 2)
  static let option = Self(rawValue: 4), shift = Self(rawValue: 8)
 }
 struct Phase: OptionSet {
  let rawValue: Int
  static let began = Self(rawValue: 1), ended = Self(rawValue: 2), cancelled = Self(rawValue: 4)
 }
 static let mouseLocation = CGPoint(x: 50, y: 10)
 var modifierFlags: ModifierFlags = []
 var scrollingDeltaY = -1.0, scrollingDeltaX = 0.0, timestamp = 1.0
 var hasPreciseScrollingDeltas = false
 var phase: Phase = [], momentumPhase: Phase = []
 var locationInWindow = CGPoint(x: 50, y: 10)
}
class Panel {
 var frame = CGRect(x: 10, y: 100, width: 400, height: 300)
 func convertPoint(toScreen point: CGPoint) -> CGPoint {
  CGPoint(x: frame.minX + point.x, y: frame.minY + point.y)
 }
}
struct Geometry { var headerTopInset = 8.0, headerRowHeight = 32.0 }
class Host {
 var containsPointer = true
 func contains(_ point: CGPoint) -> Bool { containsPointer }
 func containsHover(_ point: CGPoint) -> Bool { containsPointer }
}
enum NotchNotificationSupport {
 static var enabled = true
 static func isEnabled() -> Bool { enabled }
}
class NotchNotificationService {
 static let shared = NotchNotificationService()
 var items: [NotchSystemNotification] = []
}
struct NotchNotice {
 enum Event { case systemNotification }
 var event: Event, title: String, detail: String, symbol: String
 var notification: NotchNotificationContent?
 var notificationID: UUID?
 var replayed = false
}
class Service {
 var acceptsUserInteraction = true, expanded = false, peeking = false, noticeExpanded = false
 var trackingMenu = false, heldDrag = false
 var openedByHover = false, showingSections = false, pinned = false, keepsWorkingSurface = false
 var expandedGeometry = Geometry()
 var captureControls: Int?
 var panel: Panel? = Panel()
 var windowHost: Host? = Host()
 var rewindScroll = NotchSectionScroll(), hoverState = NotchHoverState()
 var hoverWork: DispatchWorkItem?
 var notice: NotchNotice?
 var shown = 0, dismissed = 0, collapsed = 0
 var shownWhileExpanded = false
 func show(_ incoming: NotchNotice) -> Bool {
  notice = incoming; shown += 1; shownWhileExpanded = expanded; return true
 }
 func dismissNotice() { notice = nil; dismissed += 1 }
 func collapse() { expanded = false; openedByHover = false; collapsed += 1 }
HANDLERS
}
var checks = 0
func expect(_ value: @autoclosure () -> Bool, _ message: String) {
 checks += 1
 precondition(value(), message)
}
func item(_ title: String) -> NotchSystemNotification {
 NotchSystemNotification(id: UUID(),
  content: NotchNotificationContent(app: "Fixture", title: title, subtitle: "", body: title + " body"),
  received: Date(), canOpen: true)
}
let newest = item("Newest"), middle = item("Middle"), oldest = item("Oldest")
let history = [newest, middle, oldest]
func fresh() -> Service {
 NotchNotificationSupport.enabled = true
 NotchNotificationService.shared.items = history
 return Service()
}
let down = NSEvent()
var up = NSEvent(); up.scrollingDeltaY = 1

let blocked: [(String, (Service) -> Void)] = [
 ("disabled interaction", { $0.acceptsUserInteraction = false }),
 ("expanded", { $0.expanded = true }),
 ("pinned", { $0.pinned = true }),
 ("protected working surface", { $0.keepsWorkingSurface = true }),
 ("peeking", { $0.peeking = true }),
 ("expanded notice", { $0.noticeExpanded = true }),
 ("tracking menu", { $0.trackingMenu = true }),
 ("capture selection", { $0.captureControls = 1 }),
 ("held drag", { $0.heldDrag = true }),
 ("missing panel", { $0.panel = nil }),
 ("missing host", { $0.windowHost = nil }),
 ("outside island", { $0.windowHost?.containsPointer = false }),
 ("notification feature disabled", { _ in NotchNotificationSupport.enabled = false }),
 ("empty history", { _ in NotchNotificationService.shared.items = [] }),
]
for (name, configure) in blocked {
 let service = fresh(), work = DispatchWorkItem {}
 service.hoverWork = work; configure(service)
 expect(!service.handleRewindScroll(down), name + " must not consume scrolling")
 expect(service.shown == 0 && service.dismissed == 0 && !work.isCancelled,
        name + " must preserve content and unrelated hover work")
}
for modifier: NSEvent.ModifierFlags in [.command, .control, .option, .shift] {
 let service = fresh()
 var event = down; event.modifierFlags = modifier
 expect(!service.handleRewindScroll(event) && service.shown == 0, "modified scroll must be left alone")
}
let horizontal = fresh()
var sideways = down; sideways.scrollingDeltaX = 10
expect(!horizontal.handleRewindScroll(sideways), "horizontal gestures must not browse notifications")

func hoveredHome() -> Service {
 let service = fresh()
 service.expanded = true; service.openedByHover = true; service.showingSections = true
 return service
}
var header = down; header.locationInWindow.y = 280
let hovered = hoveredHome()
expect(hovered.handleRewindScroll(header) && hovered.notice?.notificationID == newest.id,
       "the hovered home header must permit notification rewind")
expect(!hovered.expanded && hovered.collapsed == 1 && !hovered.shownWhileExpanded
       && hovered.hoverState.suppressed, "the first header step must collapse before showing a replay and suppress reopening")
let headerBlocked: [(String, (Service) -> Void)] = [
 ("explicit home opening", { $0.openedByHover = false }),
 ("a tool page", { $0.showingSections = false }),
 ("pinned home", { $0.pinned = true }),
 ("modal or protected home", { $0.keepsWorkingSurface = true }),
]
for (name, configure) in headerBlocked {
 let service = hoveredHome(), work = DispatchWorkItem {}
 service.hoverWork = work; configure(service)
 expect(!service.handleRewindScroll(header), name + " must retain its scrolling")
 expect(service.expanded && service.collapsed == 0 && service.shown == 0 && !work.isCancelled,
        name + " must not collapse or cancel its existing work")
}
let gallery = hoveredHome(), galleryHover = DispatchWorkItem {}
gallery.hoverWork = galleryHover
var body = header; body.locationInWindow.y = 259
expect(!gallery.handleRewindScroll(body) && gallery.expanded && gallery.collapsed == 0
       && !galleryHover.isCancelled, "the gallery body must keep its own scrolling below the header boundary")
let boundary = hoveredHome()
var headerEdge = header; headerEdge.locationInWindow.y = 260
expect(boundary.handleRewindScroll(headerEdge) && boundary.collapsed == 1,
       "the last point in the header must use the same measured boundary as gallery scrolling")
let headerTrackpad = hoveredHome()
var headerPrecise = header
headerPrecise.hasPreciseScrollingDeltas = true; headerPrecise.phase = .began
headerPrecise.scrollingDeltaY = -12
expect(headerTrackpad.handleRewindScroll(headerPrecise) && headerTrackpad.expanded
       && headerTrackpad.collapsed == 0 && headerTrackpad.shown == 0,
       "small header trackpad movement must wait for the first browse step before collapsing")
headerPrecise.phase = []; headerPrecise.timestamp = 1.05
expect(headerTrackpad.handleRewindScroll(headerPrecise) && !headerTrackpad.expanded
       && headerTrackpad.collapsed == 1 && headerTrackpad.notice?.notificationID == newest.id,
       "crossing the first trackpad threshold must collapse the hovered home once")
let headerMomentum = hoveredHome()
var momentumOnly = header; momentumOnly.momentumPhase = .began; momentumOnly.scrollingDeltaY = -1000
expect(headerMomentum.handleRewindScroll(momentumOnly) && headerMomentum.expanded
       && headerMomentum.collapsed == 0 && headerMomentum.shown == 0,
       "momentum over the header must not collapse the home or browse notifications")

let browse = fresh(), pendingHover = DispatchWorkItem {}
browse.hoverWork = pendingHover
expect(browse.handleRewindScroll(down) && browse.notice?.notificationID == newest.id,
       "the first wheel step must show the latest message")
expect(browse.notice?.replayed == true && browse.notice?.title == newest.content.title
       && browse.notice?.detail == newest.content.body, "rewind must preserve actual message content")
expect(pendingHover.isCancelled && browse.hoverWork == nil && browse.hoverState.suppressed,
       "rewinding must cancel delayed opening and suppress automatic hover")
expect(browse.handleRewindScroll(down) && browse.notice?.notificationID == middle.id,
       "the next step must show the next older message")
expect(browse.handleRewindScroll(down) && browse.notice?.notificationID == oldest.id,
       "older traversal must reach the last message")
expect(browse.handleRewindScroll(down) && browse.notice?.notificationID == oldest.id,
       "older traversal must stop at the oldest message")
expect(browse.handleRewindScroll(up) && browse.notice?.notificationID == middle.id,
       "reverse scroll must return to a newer message")
expect(browse.handleRewindScroll(up) && browse.notice?.notificationID == newest.id,
       "reverse scroll must reach the newest message")
expect(browse.handleRewindScroll(up) && browse.notice == nil && browse.dismissed == 1
       && browse.hoverState.suppressed, "scrolling past the newest message must return to live content")
browse.hoverState.update(pointerInside: false)
expect(!browse.hoverState.suppressed, "leaving the island must release hover suppression")

let trackpad = fresh(), pendingTrackpadHover = DispatchWorkItem {}
trackpad.hoverWork = pendingTrackpadHover
var precise = down
precise.hasPreciseScrollingDeltas = true; precise.phase = .began; precise.scrollingDeltaY = -12
expect(trackpad.handleRewindScroll(precise) && trackpad.shown == 0 && pendingTrackpadHover.isCancelled,
       "the start of a trackpad scroll cancels pending opening before the browse threshold")
precise.phase = []; precise.timestamp = 1.05
expect(trackpad.handleRewindScroll(precise) && trackpad.notice?.notificationID == newest.id,
       "trackpad deltas accumulate into one browse step")
var momentum = precise; momentum.momentumPhase = .began; momentum.scrollingDeltaY = -1000
let shownBeforeMomentum = trackpad.shown
expect(trackpad.handleRewindScroll(momentum) && trackpad.shown == shownBeforeMomentum
       && trackpad.notice?.notificationID == newest.id, "momentum must not run through notification history")

let replacement = fresh()
_ = replacement.handleRewindScroll(down); _ = replacement.handleRewindScroll(down)
let arriving = item("Arriving")
NotchNotificationService.shared.items.insert(arriving, at: 0)
_ = replacement.show(NotchNotice(event: .systemNotification, title: arriving.content.title,
 detail: arriving.content.body, symbol: "bell.fill", notification: arriving.content,
 notificationID: arriving.id, replayed: false))
expect(replacement.handleRewindScroll(down) && replacement.notice?.notificationID == arriving.id,
       "a real notification must reset the cursor instead of continuing the previous replay position")
expect(replacement.handleRewindScroll(down) && replacement.notice?.notificationID == newest.id,
       "older traversal must continue from the refreshed history")

expect(NotchNotificationRewind.selection(items: [], current: nil, steps: 1) == nil,
       "an empty inbox has no selection")
expect(NotchNotificationRewind.selection(items: history, current: newest.id, steps: 0) == nil,
       "zero steps must not invent a selection")
expect(NotchNotificationRewind.selection(items: history, current: UUID(), steps: 1)?.id == newest.id,
       "a removed history cursor must restart at the newest message")
expect(NotchNotificationRewind.selection(items: history, current: newest.id, steps: Int.max)?.id == oldest.id,
       "large scroll counts must clamp safely to the oldest message")
expect(NotchNotificationRewind.selection(items: history, current: oldest.id, steps: Int.min) == nil,
       "large reverse scroll counts must safely return to live content")
print("Notification rewind: \(checks) checks passed")
'''
with tempfile.TemporaryDirectory(prefix="island-rewind-test-") as temporary:
    folder = Path(temporary)
    (folder / "main.swift").write_text(
        harness.replace("LAYOUT", layout).replace("PRODUCTION", production).replace("HANDLERS", handlers)
    )
    subprocess.run(["swiftc", str(folder / "main.swift"), "-o", str(folder / "probe")], check=True)
    subprocess.run([str(folder / "probe")], check=True)
