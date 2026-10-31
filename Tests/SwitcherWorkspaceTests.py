#!/usr/bin/env python3
"""Exercise the production AeroSpace query with isolated CLI fixtures."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='switcher-workspace-') as directory:
    root = Path(directory)
    fixtures = []
    for mode in ['normal', 'empty', 'changed', 'malformed', 'failure', 'timeout']:
        script = root / mode
        script.write_text('''#!/usr/bin/python3
import sys, time
from pathlib import Path
mode = Path(__file__).name
if mode == 'failure': sys.exit(1)
if mode == 'timeout': time.sleep(10)
if sys.argv[1] == 'list-workspaces':
    state = Path(__file__ + '.count')
    count = int(state.read_text()) if state.exists() else 0
    state.write_text(str(count + 1))
    print('P' if mode == 'changed' and count else 'G')
else:
    assert sys.argv[1:] == ['list-windows', '--workspace', 'G', '--json']
    print('bad' if mode == 'malformed' else '[]' if mode == 'empty' else '[{"window-id":12},{"window-id":34}]')
''')
        script.chmod(0o700)
        fixtures.append(str(script))
    (root / 'main.swift').write_text('''import Foundation
let paths = Array(CommandLine.arguments.dropFirst())
let normal = try NotchWorkspaceWindows.focusedSnapshot(executable: URL(fileURLWithPath: paths[0]))
precondition(normal.workspace == "G" && normal.windowIDs == [12,34])
let empty = try NotchWorkspaceWindows.focusedSnapshot(executable: URL(fileURLWithPath: paths[1]))
precondition(empty.windowIDs.isEmpty)
for path in paths.dropFirst(2) {
    let began = Date()
    do {
        _ = try NotchWorkspaceWindows.focusedSnapshot(executable: URL(fileURLWithPath:path))
        fatalError("Expected rejection")
    } catch {}
    precondition(Date().timeIntervalSince(began) < 4)
}
print("PASS: 6 workspace query cases (membership, empty, changed, malformed, failure, timeout)")
''')
    executable = root / 'checks'
    subprocess.run(['swiftc', '-sdk', '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk',
                    str(repo / 'Sources/Vorssaint/Services/Notch/NotchWorkspaceWindows.swift'),
                    str(root / 'main.swift'), '-o', str(executable)], check=True)
    subprocess.run([str(executable), *fixtures], check=True)
