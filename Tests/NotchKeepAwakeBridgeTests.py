#!/usr/bin/env python3
"""Run the production SketchyBar status publisher with an isolated session and process."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / 'Sources/Vorssaint/Services/Notch/NotchService.swift').read_text()
start = source.index('    private func publishKeepAwakeState()')
end = source.index('\n    private func publishQuietMode', start)
method = source[start:end].replace('private func', 'func', 1)
swift = '''import Foundation
final class KeepAwakeManager {
 static let shared = KeepAwakeManager()
 var isActive = false
 var endDate: Date?
}
final class Process {
 var executableURL: URL?
 var arguments: [String]?
 var standardInput: Any?, standardOutput: Any?, standardError: Any?
 static var calls: [[String]] = []
 func run() throws { Self.calls.append(arguments!) }
}
final class Publisher {
''' + method + '''
}
let publisher = Publisher()
let awake = KeepAwakeManager.shared
for (active, end) in [(false, Optional<Date>.none), (true, Date(timeIntervalSince1970:1800000000)), (true,nil)] {
 awake.isActive = active; awake.endDate = end
 publisher.publishKeepAwakeState()
 let args = Process.calls.last!
 precondition(args.prefix(2) == ["--trigger", "island_keep_awake"])
 precondition(args[2] == "ACTIVE=\\(active ? 1 : 0)")
 precondition(args[3] == "END=\\(end?.timeIntervalSince1970 ?? 0)")
 let at = Double(args[4].dropFirst(3))!
 precondition(abs(at - Date().timeIntervalSince1970) < 2)
 precondition(awake.isActive == active && awake.endDate == end)
}
print("PASS: 15 Keep Awake bridge checks; no real session or process changed")
'''
with tempfile.TemporaryDirectory(prefix='awake-bridge-') as folder:
    root = Path(folder)
    (root / 'main.swift').write_text(swift)
    subprocess.run(['swiftc', str(root / 'main.swift'), '-o', str(root / 'checks')], check=True)
    subprocess.run([str(root / 'checks')], check=True)
