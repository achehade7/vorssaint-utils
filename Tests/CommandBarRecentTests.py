#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Test recent-note ordering with the actual Spotlight query and temporary files."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import time

repo = Path(__file__).resolve().parents[1]
folder = Path(tempfile.mkdtemp(prefix="island-recent-", dir=Path.home() / "Pictures"))
try:
    (folder / "ignored").mkdir()
    for name, age in [("older.md", 900), ("newer.md", 100), ("recent report.md", 500),
                      ("not-a-note.txt", 1), ("ignored/hidden-note.md", 1)]:
        path = folder / name
        path.write_text("Test fixture\n")
        os.utime(path, (time.time() - age, time.time() - age))
    subprocess.run(["mdimport", str(folder)], check=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        indexed = subprocess.check_output(["mdfind", "-onlyin", str(folder),
                                           "kMDItemFSName == '*.md'cd"], text=True)
        if len(indexed.splitlines()) >= 4:
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Spotlight did not index the isolated fixtures")
    with tempfile.TemporaryDirectory(prefix="recent-command-tests-") as temporary:
        build = Path(temporary)
        swift = build / "main.swift"
        swift.write_text(r'''
import Foundation
let folder = CommandLine.arguments[1]
let search = CommandBarFileSearch()
var deliveries = 0
search.onResult = { deliveries += 1 }
func waitFor(_ query: String) {
    let deadline = Date().addingTimeInterval(10)
    while search.cachedPaths(for: query) == nil && Date() < deadline {
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
    }
    precondition(search.cachedPaths(for: query) != nil, "query did not complete")
}
search.schedule(query: "recent", scopes: [folder], patterns: ["ignored"])
waitFor("recent")
let names = search.cachedPaths(for: "recent")!.map { URL(fileURLWithPath: $0).lastPathComponent }
precondition(names == ["newer.md", "recent report.md", "older.md"], "unexpected recent order or filtering: \(names)")
search.schedule(query: "recent report", scopes: [folder], patterns: [])
waitFor("recent report")
precondition(search.cachedPaths(for: "recent report")!.count == 1, "filename searches must still work")
search.reset()
let before = deliveries
search.schedule(query: "recent", scopes: [folder], patterns: [])
search.reset()
RunLoop.main.run(until: Date().addingTimeInterval(0.3))
precondition(deliveries == before && search.cachedPaths(for: "recent") == nil, "closed search must not publish")
print("Recent command: native Spotlight ordering, Markdown filter, ignored folders, filename search and cancellation passed")
''')
        sources = [repo / "Sources/Vorssaint/Services/CommandBar" / name for name in
                   ["CommandBarFileSearch.swift", "CommandBarFileSearchSupport.swift"]]
        binary = build / "test"
        subprocess.run(["swiftc", *map(str, sources), str(swift), "-o", str(binary)], check=True)
        subprocess.run([str(binary), str(folder)], check=True)
finally:
    shutil.rmtree(folder)
