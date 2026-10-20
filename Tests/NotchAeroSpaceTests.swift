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
        suite.expect(state.previous == nil, "the initial snapshot cannot invent a previous workspace")
        suite.expect(state.showsStrip(hovered: true, blocked: false, now: 10), "hover reveals connected workspaces")
        suite.expect(state.receive(event("G"), now: 20) && state.showsStrip(hovered: false, blocked: false, now: 21.31)
                     && !state.showsStrip(hovered: false, blocked: false, now: 21.32),
                     "the workspace shell stays through the app and label departures")
        suite.expect(state.previous == "1" && state.trailUntil == 20.8 && state.trailUntil < state.flashUntil,
                     "confirmed switches keep app trails shorter than the workspace label")
        let appsGone = state.trailUntil + NotchAeroSpaceState.trailFadeDuration
        suite.expect(state.labelFadeAt > appsGone && state.labelFadeAt - appsGone < 0.03
                     && abs(state.labelFadeAt + NotchAeroSpaceState.labelFadeDuration - state.flashUntil) < 0.001,
                     "the label follows the app fade closely and hands directly into shell withdrawal")
        suite.expect(!state.receive(event("G"), now: 20.9) && state.flashUntil == 21.32,
                     "duplicate events do not extend the flash")
        suite.expect(state.previous == "1", "duplicate events preserve the previous destination")
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
        windowContracts(suite)
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
                if (root / 'fail-switch').exists():
                    (root / 'failed').write_text(sys.argv[2])
                    sys.exit(1)
                with (root / 'commands').open('a') as commands:
                    commands.write(sys.argv[2] + '\\n')
                (root / 'switch-pid').write_text(str(os.getpid()))
                (root / 'selected').write_text(sys.argv[2])
                while (root / 'hold-switch').exists():
                    time.sleep(.01)
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
            service.togglePrevious()
            suite.expect(!FileManager.default.fileExists(atPath: folder.appendingPathComponent("selected").path),
                         "a previous-workspace gesture before the first switch sends no command")
            let holdSwitch = folder.appendingPathComponent("hold-switch")
            try Data().write(to: holdSwitch)
            service.select("2")
            suite.expect(wait { service.state.current == "2" }, "clicking a workspace sends the command and waits for the confirmed event")
            let switchingPID = Int32(try String(contentsOf: folder.appendingPathComponent("switch-pid"), encoding: .utf8))!
            suite.expect(kill(switchingPID, 0) == 0,
                         "the fixture confirms the switch while its command is still alive")
            suite.expect(updates >= 2 && service.state.flashUntil > ProcessInfo.processInfo.systemUptime,
                         "confirmed switching publishes the new selection and starts its flash")
            service.select("unlisted")
            suite.expect((try? String(contentsOf: folder.appendingPathComponent("selected"), encoding: .utf8)) == "2",
                         "only the four configured workspace buttons can send commands")
            service.select("G")
            service.togglePrevious()
            suite.expect((try? String(contentsOf: folder.appendingPathComponent("commands"), encoding: .utf8)) == "2\n",
                         "requests wait for the active workspace command instead of running in parallel")
            suite.expect(service.state.current == "2" && service.state.previous == "1",
                         "queued requests leave the event-confirmed workspace history unchanged")
            try FileManager.default.removeItem(at: holdSwitch)
            suite.expect(wait { service.state.current == "1" && service.state.previous == "2" },
                         "previous-workspace switching returns to the confirmed prior workspace")
            suite.expect((try? String(contentsOf: folder.appendingPathComponent("commands"), encoding: .utf8)) == "2\n1\n",
                         "only the latest workspace request runs after the prior command exits")
            service.togglePrevious()
            suite.expect(wait { service.state.current == "2" && service.state.previous == "1" },
                         "repeating previous-workspace switching toggles back")
            let failSwitch = folder.appendingPathComponent("fail-switch")
            try Data().write(to: failSwitch)
            service.togglePrevious()
            suite.expect(wait { FileManager.default.fileExists(atPath: folder.appendingPathComponent("failed").path) },
                         "the previous-workspace request reaches the command process")
            suite.expect(service.state.current == "2" && service.state.previous == "1",
                         "a failed command cannot change the confirmed workspace history")
            try FileManager.default.removeItem(at: failSwitch)
            try "Q".write(to: folder.appendingPathComponent("selected"), atomically: true, encoding: .utf8)
            suite.expect(wait { service.state.current == "Q" }, "external workspace changes update history")
            service.togglePrevious()
            suite.expect(wait { service.state.current == "2" && service.state.previous == "Q" },
                         "the previous-workspace gesture returns from an external workspace")
            service.togglePrevious()
            suite.expect(wait { service.state.current == "Q" && service.state.previous == "2" },
                         "the gesture can return to a confirmed workspace outside the visible four buttons")
            try Data().write(to: holdSwitch)
            service.select("1")
            suite.expect(wait { service.state.current == "1" }, "the disconnect fixture holds a confirmed workspace command")
            let disconnectedSwitchPID = Int32(try String(contentsOf: folder.appendingPathComponent("switch-pid"), encoding: .utf8))!
            service.select("P")
            let pidFile = folder.appendingPathComponent("pid")
            let pid = Int32(try String(contentsOf: pidFile, encoding: .utf8))!
            kill(pid, SIGTERM)
            suite.expect(wait { service.state.current == nil && service.state.previous == nil },
                         "a disconnected event stream clears stale selection and history")
            try FileManager.default.removeItem(at: holdSwitch)
            suite.expect(wait { kill(disconnectedSwitchPID, 0) != 0 },
                         "disconnecting terminates an unfinished workspace command")
            suite.expect(wait(timeout: 5) {
                service.state.current != nil && (try? String(contentsOf: pidFile, encoding: .utf8)) != String(pid)
            }, "the event stream reconnects after AeroSpace restarts")
            suite.expect(!(try String(contentsOf: folder.appendingPathComponent("commands"), encoding: .utf8)).split(separator: "\n").contains("P"),
                         "disconnecting discards the pending target instead of replaying it on reconnect")
            let reconnectedPID = Int32(try String(contentsOf: pidFile, encoding: .utf8))!
            try Data().write(to: holdSwitch)
            service.select("G")
            suite.expect(wait { service.state.current == "G" }, "the stop fixture holds a confirmed workspace command")
            let stoppedSwitchPID = Int32(try String(contentsOf: folder.appendingPathComponent("switch-pid"), encoding: .utf8))!
            service.select("P")
            service.stop()
            try FileManager.default.removeItem(at: holdSwitch)
            suite.expect(wait { kill(reconnectedPID, 0) != 0 }, "stopping the island terminates its subscription process")
            let stoppedSwitch = wait { kill(stoppedSwitchPID, 0) != 0 }
            let stoppedCommands = try String(contentsOf: folder.appendingPathComponent("commands"), encoding: .utf8)
            suite.expect(stoppedSwitch && !stoppedCommands.split(separator: "\n").contains("P"),
                         "stopping terminates the active command and discards its pending target")
            suite.expect(service.state.current == nil && service.state.previous == nil
                         && !service.state.showsStrip(hovered: true, blocked: false, now: 0),
                         "stopping removes stale workspace controls")
        } catch { suite.expect(false, "AeroSpace process fixture failed: \(error)") }
    }

    private static func windowContracts(_ suite: TestSuite) {
        let valid = Data(#"[{"window-id":42,"app-name":"Ghostty","window-title":"build · project"}]"#.utf8)
        let windows = try? JSONDecoder().decode([NotchWorkspaceWindow].self, from: valid)
        suite.expect(windows?.first?.id == 42 && windows?.first?.app == "Ghostty" && windows?.first?.title == "build · project",
                     "window cards decode the actual AeroSpace CLI field names and Unicode titles")
        suite.expect((try? JSONDecoder().decode([NotchWorkspaceWindow].self, from: Data("invalid".utf8))) == nil,
                     "malformed window output fails instead of showing stale cards")
        var result: Result<Data, Error>?
        Task { do { result = .success(try await NotchWorkspaceWindows.run(["-c", "printf hello"], executable: URL(fileURLWithPath: "/bin/sh"))) } catch { result = .failure(error) } }
        suite.expect(wait { result != nil }, "one-shot window commands complete asynchronously")
        suite.expect((try? result?.get()) == Data("hello".utf8), "one-shot commands drain their output")
        result = nil
        Task { do { result = .success(try await NotchWorkspaceWindows.run(["-c", "exec sleep 10"], executable: URL(fileURLWithPath: "/bin/sh"))) } catch { result = .failure(error) } }
        suite.expect(wait(timeout: 4) { result != nil }, "an unresponsive command is terminated within the time limit")
        if case .failure = result {} else { suite.expect(false, "a timed-out command must fail") }
    }

    private static func wait(timeout: TimeInterval = 3, until condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition(), Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
        }
        return condition()
    }
}
