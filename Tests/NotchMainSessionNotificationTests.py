#!/usr/bin/env python3
"""Run native notification acceptance against child and main-session fixtures."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
support = (repo / "Sources/Vorssaint/Services/Notch/NotchNotificationSupport.swift").read_text()
service = (repo / "Sources/Vorssaint/Services/Notch/NotchNotificationService.swift").read_text()


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


production = "\n".join(
    declaration(support, marker)
    for marker in [
        "struct NotchNotificationContent:",
        "struct NotchSystemNotification:",
        "struct NotchNotificationInbox",
    ]
)
policy = declaration(support, "    static func shouldMirror(")
accept = declaration(service, "    private func accept(").replace("private ", "", 1)

harness = r'''
import Foundation
PRODUCTION
enum NotchNotificationSupport {
    static let maximumItems = 50
    POLICY
}
// Native app lookup and icons are fixtures; acceptance and the inbox are real.
struct NSImage {}
struct NSRunningApplication {
    var icon: NSImage? { nil }
    static func runningApplications(withBundleIdentifier: String) -> [Self] { [] }
}
enum InstalledApps {
    static func url(for: String) -> URL? { nil }
}
struct NSWorkspace {
    static let shared = NSWorkspace()
    func icon(forFile: String) -> NSImage { NSImage() }
}
enum NotchNotificationSources {
    static func source(for names: [String]) -> (bundleIdentifier: String, name: String)? {
        let apps = ["Ghostty": "com.mitchellh.ghostty", "Codex": "com.openai.codex",
                    "Claude": "com.anthropic.claudefordesktop", "Slack": "com.tinyspeck.slackmacgap"]
        guard let name = names.first, let identifier = apps[name] else { return nil }
        return (identifier, name)
    }
}
final class Received {
    var items: [NotchSystemNotification] = []
    func send(_ item: NotchSystemNotification) { items.append(item) }
}
final class Service {
    var inbox = NotchNotificationInbox()
    var appIcons: [String: NSImage] = [:]
    var sourceApplications: [UUID: String] = [:]
    var shownIDs = Set<UUID>(), closingIDs = Set<UUID>()
    let received = Received()
    func trimIcons() {}
    ACCEPT
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    if !condition { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
func item(_ message: String, app: String = "Ghostty", field: String = "body") -> NotchSystemNotification {
    NotchSystemNotification(id: UUID(), content: NotchNotificationContent(
        app: app, title: field == "title" ? message : "Codex",
        subtitle: field == "subtitle" ? message : "", body: field == "body" ? message : ""),
        received: Date(), canOpen: true)
}
let service = Service()
service.accept([])
let children = [
    item("Completed `/root/desktop_cpu_measurement`"),
    item("Completed /root/bar_input", field: "title"),
    item("Completed `/root/task_1/nested_child`", field: "subtitle"),
    item("Completed /root/child", app: "Codex"),
    item(" Completed `/root/child` \n"),
]
service.accept(children)
expect(service.received.items.isEmpty, "child-task completions must not interrupt the island")
expect(service.inbox.items.isEmpty, "child-task completions must not appear in notification rewind")
expect(service.inbox.unreadCount == 0, "filtered child-task completions must not create unread marks")
let kept = [
    item("Completed `/root`"), item("Completed /root"), item("Codex finished"),
    item("Claude finished", app: "Claude"),
    item("Completed `/root/desktop_cpu_measurement`", app: "Slack"),
    item("Completed `/root/desktop_cpu_measurement`", app: "Unknown"),
    item("Approval requested for `/root/child`"),
    item("Completed `/root/child` and updated the main session"),
    item("Report: Completed `/root/child`"),
    item("Completed `/root/child`", app: "Claude"),
    item("Completed /rootish"), item("Completed /root/"), item("Completed `/root/child"),
]
service.accept(children + kept)
expect(Set(service.received.items.map(\.id)) == Set(kept.map(\.id)),
       "main completion, Claude, unrelated senders and non-completion notices must arrive unchanged")
expect(Set(service.inbox.items.map(\.id)) == Set(kept.map(\.id)),
       "only eligible notices enter history")
expect(service.inbox.unreadIDs == Set(kept.map(\.id)),
       "eligible arrivals remain unread after their automatic banners are delivered")
service.inbox.markRead(kept[0].id)
service.accept(children + kept)
expect(service.received.items.count == kept.count, "layout rescans must not redeliver eligible notices")
expect(service.inbox.items.count == kept.count, "layout rescans must not resurrect hidden child completions")
expect(service.inbox.unreadCount == kept.count - 1 && !service.inbox.unreadIDs.contains(kept[0].id),
       "native rescans must preserve which notification was explicitly read")
service.accept([])
expect(service.inbox.items.allSatisfy { !$0.canOpen }, "native expiry must still clear stale actions")
let startup = Service()
startup.accept(children + kept)
expect(startup.received.items.isEmpty && startup.inbox.items.isEmpty,
       "starting the mirror must not replay existing native banners")
expect(startup.inbox.unreadCount == 0, "existing banners must not appear as unread on startup")
let root = item("Completed `/root`")
startup.accept([root])
expect(startup.received.items.map(\.id) == [root.id], "a new main session finish must still notify")
for child in children {
    expect(!NotchNotificationSupport.shouldMirror(child.content,
        sourceBundleIdentifier: NotchNotificationSources.source(for: [child.content.app])?.bundleIdentifier),
        "each observed child completion format must be filtered")
}
for notice in kept {
    expect(NotchNotificationSupport.shouldMirror(notice.content,
        sourceBundleIdentifier: NotchNotificationSources.source(for: [notice.content.app])?.bundleIdentifier),
        "each non-child notification must remain eligible")
}
print("Main-session notification filtering: \(checks) checks passed")
'''
with tempfile.TemporaryDirectory(prefix="island-main-session-notifications-") as temporary:
    folder = Path(temporary)
    (folder / "main.swift").write_text(
        harness.replace("PRODUCTION", production).replace("POLICY", policy).replace("ACCEPT", accept)
    )
    subprocess.run(["swiftc", str(folder / "main.swift"), "-o", str(folder / "test")], check=True)
    subprocess.run([str(folder / "test")], check=True)
