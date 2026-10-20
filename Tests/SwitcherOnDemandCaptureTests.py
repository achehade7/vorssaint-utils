#!/usr/bin/env python3
"""Exercise switcher preference sync and its real on-demand preview route."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / "Sources/Vorssaint/Services/Switcher/AppSwitcher.swift").read_text()


def declaration(marker):
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


sync = declaration("    func syncWithPreferences()")
start = source.index("        if pending.commitWhenReady {\n            commitSession()")
end = source.index("        if !pending.commitWhenReady {", start)
on_demand = source[start:end]

harness = r'''
import Foundation
enum DefaultsKey {
    static let switcherShortcut = "switcherShortcut"
    static let switcherWindowShortcut = "switcherWindowShortcut"
    static let switcherTakeOverSystemShortcuts = "switcherTakeOverSystemShortcuts"
    static let switcherPreviewExcludedApps = "switcherPreviewExcludedApps"
}
enum GlobalShortcut: Equatable {
    case switcherDefault, switcherWindowDefault
    static func saved(for: String, fallback: Self) -> Self { fallback }
}
struct UserDefaults {
    static var standard = Self()
    var takesOver = false
    func bool(forKey: String) -> Bool { takesOver }
}
final class View {
    var layouts = 0
    func layoutSubtreeIfNeeded() { layouts += 1 }
}
final class Controller { let view = View() }
final class Panel { let contentViewController: Controller? = Controller() }
final class SecureInputWatch {
    var starts = 0, stops = 0
    func start() { starts += 1 }
    func stop() { stops += 1 }
}
struct Item { var previewWindowID: Int? }
struct Pending { var commitWhenReady = false }
enum PreviewSizing { static let switcherScale = 1.0 }
final class WindowPreviewProvider {
    static var shared = WindowPreviewProvider()
    var starts = 0, stops = 0, refreshes = 0
    var requestedIDs: [Int] = []
    var excludedAppsKey: String?
    func startWarming() { starts += 1 }
    func stopWarming() { stops += 1 }
    func refreshPreviews(for items: [Item], maxPixelSize: Double, excludedAppsKey: String,
                         onUpdate: (Int, Int) -> Void) {
        refreshes += 1
        requestedIDs = items.compactMap(\.previewWindowID)
        self.excludedAppsKey = excludedAppsKey
        for id in requestedIDs { onUpdate(id, id + 100) }
    }
}
final class Switcher {
    let routeLock = NSLock()
    let secureInputWatch = SecureInputWatch()
    var routeShortcut = GlobalShortcut.switcherDefault
    var routeWindowShortcut = GlobalShortcut.switcherWindowDefault
    var routeCanStartSession = false
    var tapIsWanted = true, capturesPreviews = true
    var installed = 0, removed = 0, restored = 0, suppressed = 0
    var keyboardObservations = 0, wakeObservations = 0
    let panel = Panel()
    var sessionActive = true, sessionItems: [Item] = []
    var previews: [Int: Int] = [:]
    var commits = 0
    func startObservingKeyboardLayout() { keyboardObservations += 1 }
    func startObservingWake() { wakeObservations += 1 }
    func installTap() { installed += 1 }
    func restoreNativeHotkeys() { restored += 1 }
    func applyNativeHotkeySuppressionIfTapLive() { suppressed += 1 }
    func ensurePanel() -> Panel { panel }
    func stopObservingKeyboardLayout() { keyboardObservations -= 1 }
    func stopObservingWake() { wakeObservations -= 1 }
    func removeTap() { removed += 1 }
    func commitSession() { commits += 1 }
    func enqueuePreviewUpdate(windowID: Int, image: Int) { previews[windowID] = image }
    SYNC
    func open(_ list: [Item], pending: Pending = Pending()) {
        sessionItems = list
        ON_DEMAND
    }
}
var checks = 0
func expect(_ condition: Bool, _ message: String) {
    checks += 1
    if !condition { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
for previews in [true, false] {
    for takesOver in [true, false] {
        WindowPreviewProvider.shared = WindowPreviewProvider()
        UserDefaults.standard.takesOver = takesOver
        let switcher = Switcher()
        switcher.capturesPreviews = previews
        switcher.syncWithPreferences()
        let provider = WindowPreviewProvider.shared
        expect(provider.starts == 0, "preference sync must not begin background screen capture")
        expect(provider.stops == 1, "preference sync must stop a previously active warmer")
        expect(provider.refreshes == 0, "preference sync must not request any thumbnails")
        expect(switcher.installed == 1 && switcher.routeCanStartSession,
               "the switcher's keyboard route must remain available")
        expect(switcher.panel.contentViewController?.view.layouts == 1,
               "the panel's first layout must still be prepared")
        expect(takesOver ? switcher.suppressed == 1 : switcher.restored == 1,
               "the user's native shortcut preference must still apply")
        expect(switcher.secureInputWatch.starts == (takesOver ? 1 : 0)
               && switcher.secureInputWatch.stops == (takesOver ? 0 : 1),
               "secure-input monitoring follows native shortcut takeover without starting capture")
        switcher.syncWithPreferences()
        expect(provider.starts == 0 && provider.stops == 2 && provider.refreshes == 0,
               "repeated sync must stay capture-free")
        switcher.open([Item(previewWindowID: 7), Item(previewWindowID: 9)])
        expect(provider.refreshes == (previews ? 1 : 0),
               "opening the switcher must capture previews only in preview mode")
        expect(switcher.previews == (previews ? [7: 107, 9: 109] : [:]),
               "on-demand preview results must still reach the active switcher")
        if previews {
            expect(provider.requestedIDs == [7, 9]
                   && provider.excludedAppsKey == DefaultsKey.switcherPreviewExcludedApps,
                   "on-demand capture must retain the selected windows and exclusion policy")
        }
        switcher.tapIsWanted = false
        switcher.syncWithPreferences()
        expect(provider.starts == 0 && provider.stops == 3 && switcher.removed == 1
               && !switcher.routeCanStartSession,
               "disabling the switcher must still stop capture and keyboard routing")
        expect(switcher.secureInputWatch.stops == (takesOver ? 1 : 3),
               "disabling the switcher also stops secure-input monitoring")
    }
}
WindowPreviewProvider.shared = WindowPreviewProvider()
let immediate = Switcher()
immediate.open([Item(previewWindowID: 7)], pending: Pending(commitWhenReady: true))
expect(immediate.commits == 1 && WindowPreviewProvider.shared.refreshes == 0,
       "an already committed switch must not take an unnecessary screenshot")
let closed = Switcher()
closed.sessionActive = false
closed.open([Item(previewWindowID: 7)])
expect(closed.previews.isEmpty, "late captures must not update a closed switcher session")
print("On-demand switcher capture: \(checks) checks passed")
'''
with tempfile.TemporaryDirectory(prefix="switcher-on-demand-capture-") as temporary:
    folder = Path(temporary)
    (folder / "main.swift").write_text(harness.replace("SYNC", sync).replace("ON_DEMAND", on_demand))
    subprocess.run(["swiftc", str(folder / "main.swift"), "-o", str(folder / "test")], check=True)
    subprocess.run([str(folder / "test")], check=True)
