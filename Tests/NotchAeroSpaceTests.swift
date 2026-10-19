// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import Darwin

enum NotchAeroSpaceTests {
    static func run(_ suite: TestSuite) {
        func event(_ name: String) -> Data {
            try! JSONSerialization.data(withJSONObject: ["_event": "focused-workspace-changed", "workspace": name])
        }
        var state = NotchAeroSpaceState()
        suite.expect(!state.showsStrip(hovered: true, blocked: false, now: 0), "no workspace controls without AeroSpace")
        suite.expect(state.receive(event("1"), now: 10) && state.current == "1"
                     && !state.showsStrip(hovered: false, blocked: false, now: 10),
                     "the first workspace snapshot sets selection without a startup flash")
        suite.expect(state.showsStrip(hovered: true, blocked: false, now: 10), "hover reveals connected workspaces")
        suite.expect(state.receive(event("G"), now: 20) && state.showsStrip(hovered: false, blocked: false, now: 21.9)
                     && !state.showsStrip(hovered: false, blocked: false, now: 22),
                     "a workspace change flashes for two seconds and then restores the resting island")
        suite.expect(!state.receive(event("G"), now: 21) && state.flashUntil == 22,
                     "duplicate events do not extend the flash")
        suite.expect(!state.showsStrip(hovered: true, blocked: true, now: 21),
                     "notifications, full screen and open pages suppress both hover and flash")
        suite.expect(state.showsStrip(hovered: true, blocked: false, now: 30),
                     "hover keeps the buttons available after a flash expires")
        suite.expect(!state.receive(Data("not JSON".utf8), now: 30)
                     && !state.receive(Data("{\"_event\":\"focused-window-changed\",\"workspace\":\"2\"}".utf8), now: 30),
                     "malformed and unrelated events do not change the workspace")
        suite.expect(state.receive(event("Q"), now: 30) && !state.showsStrip(hovered: false, blocked: false, now: 30),
                     "workspaces outside the selected four do not produce a flash")
        suite.expect(SettingsBackupSupport.exportKeys().contains(DefaultsKey.notchAeroSpaceEnabled),
                     "the integration toggle is included in settings backups")
        processContracts(suite)
    }

    private static func processContracts(_ suite: TestSuite) {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("notch-aerospace-\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: folder) }
            let executable = folder.appendingPathComponent("aerospace")
            let script = """
            #!/usr/bin/python3
            import pathlib, sys, time, json, os
            root = pathlib.Path(__file__).parent
            if sys.argv[1:] == ['subscribe', 'focused-workspace-changed']:
                (root / 'pid').write_text(str(os.getpid()))
                previous = '1'
                line = json.dumps({'_event': 'focused-workspace-changed', 'workspace': previous}) + '\\n'
                sys.stdout.write(line[:15]); sys.stdout.flush(); time.sleep(.03)
                sys.stdout.write(line[15:]); sys.stdout.flush()
                while True:
                    target = root / 'selected'
                    selected = target.read_text() if target.exists() else previous
                    if selected != previous:
                        print(json.dumps({'_event': 'focused-workspace-changed', 'workspace': selected}), flush=True)
                        previous = selected
                    time.sleep(.02)
            elif len(sys.argv) == 3 and sys.argv[1] == 'workspace':
                (root / 'selected').write_text(sys.argv[2])
            else:
                sys.exit(1)
            """
            try script.write(to: executable, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: executable.path)
            let service = NotchAeroSpaceService(executable: executable)
            defer { service.stop() }
            var updates = 0
            service.onChange = { updates += 1 }
            service.start()
            suite.expect(wait { service.state.current == "1" }, "the subscription reconstructs events split across pipe reads")
            service.select("2")
            suite.expect(wait { service.state.current == "2" }, "clicking a workspace sends the command and waits for the confirmed event")
            suite.expect(updates >= 2 && service.state.flashUntil > ProcessInfo.processInfo.systemUptime,
                         "confirmed switching publishes the new selection and starts its flash")
            service.select("unlisted")
            suite.expect((try? String(contentsOf: folder.appendingPathComponent("selected"), encoding: .utf8)) == "2",
                         "only the four configured workspace buttons can send commands")
            let pidFile = folder.appendingPathComponent("pid")
            let pid = Int32(try String(contentsOf: pidFile, encoding: .utf8))!
            kill(pid, SIGTERM)
            suite.expect(wait { service.state.current == nil }, "a disconnected event stream clears stale selection")
            suite.expect(wait(timeout: 5) {
                service.state.current != nil && (try? String(contentsOf: pidFile, encoding: .utf8)) != String(pid)
            }, "the event stream reconnects after AeroSpace restarts")
            let reconnectedPID = Int32(try String(contentsOf: pidFile, encoding: .utf8))!
            service.stop()
            suite.expect(wait { kill(reconnectedPID, 0) != 0 }, "stopping the island terminates its subscription process")
            suite.expect(service.state.current == nil && !service.state.showsStrip(hovered: true, blocked: false, now: 0),
                         "stopping removes stale workspace controls")
        } catch { suite.expect(false, "AeroSpace process fixture failed: \(error)") }
    }

    private static func wait(timeout: TimeInterval = 3, until condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition(), Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
        }
        return condition()
    }
}
