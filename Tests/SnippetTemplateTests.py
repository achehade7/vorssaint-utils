#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise real placeholder parsing, form rendering and controller completion/cancel."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration
repo = Path(__file__).resolve().parents[1]
service = 'Sources/Vorssaint/Services/Snippets/SnippetLibraryService.swift'
raw = (repo/service).read_text()
state = raw[raw.index('    enum TemplateAction'):raw.index('    private let hotkey')]
fixture = r'''
import AppKit
import SwiftUI
struct Defaults { static let defaultSnippetSoundName = "Tink" }
final class L10n: ObservableObject {
    static let shared = L10n()
    struct Strings { let uninstallerCancel = "Cancel" }
    let s = Strings(), language = 0
}
enum FeatureStrings {
    struct Strings { let copy = "Copy", dateTimeConfirmInsert = "Insert" }
    static func clipboard(_ language: Int) -> Strings { Strings() }
    static func snippets(_ language: Int) -> Strings { Strings() }
}
final class TextSnippetService {
    static let shared = TextSnippetService()
    func setLibraryVisible(_ value: Bool) {}
}
final class SnippetLibraryService: ObservableObject {
    static let shared = SnippetLibraryService()
    @Published var presentationID = UUID()
    var panel: NSPanel?
    var presentations = 0
    func present() { presentations += 1; presentationID = UUID() }
    func removeMonitors() {}
    // STATE
    // HIDE
}
let app = NSApplication.shared
var snippet = TextSnippet()
snippet.name = "transport_msg"
snippet.replacement = "{{ticket}}: transport message {{message}}"
precondition(SnippetTemplateSupport.fields(in: snippet.replacement) == ["ticket", "message"])
precondition(SnippetTemplateSupport.fields(in: "{{date}} {{time}} {{datetime}} {{clipboard}} {{date:yyyy-MM-dd}} {{ticket}} {{ticket}}") == ["ticket"])
precondition(SnippetTemplateSupport.fill("{{ticket}} / {{ticket}}", values: ["ticket": "SAP-531"]) == "SAP-531 / SAP-531")
precondition(SnippetTemplateSupport.fill("{{ticket}} {{message}}", values: ["ticket": "{{message}}", "message": "literal"]) == "{{message}} literal", "field values are not recursively substituted")
let library = SnippetLibraryService.shared
var results: [TextSnippet] = []
library.resolveTemplate(snippet, action: .copy) { results.append($0) }
precondition(library.presentations == 1 && !library.canFinishTemplate)
library.finishTemplate()
precondition(results.isEmpty, "required fields must be filled")
library.templateValues = ["ticket": "SAP-531", "message": "D01K900123 ready for import"]
precondition(library.canFinishTemplate)
let host = NSHostingView(rootView: SnippetTemplateForm())
host.frame = NSRect(x: 0, y: 0, width: 460, height: 310)
host.layoutSubtreeIfNeeded()
let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
host.cacheDisplay(in: host.bounds, to: bitmap)
precondition(bitmap.pixelsWide >= 460 && bitmap.pixelsHigh >= 310)
if let png = bitmap.representation(using: .png, properties: [:]) {
    try png.write(to: URL(fileURLWithPath: "/tmp/island-transport-template.png"))
}
library.finishTemplate()
precondition(results.count == 1 && results[0].replacement == "SAP-531: transport message D01K900123 ready for import")
precondition(snippet.replacement.contains("{{ticket}}") && results[0].id == snippet.id, "filled result keeps identity without modifying original template")
precondition(library.template == nil && library.templateValues.isEmpty, "values are discarded after completion")
library.resolveTemplate(snippet, action: .insert) { results.append($0) }
precondition(library.templateValues.isEmpty && library.templateAction == .insert, "each use starts empty with requested action")
library.templateValues = ["ticket": "SAP-532", "message": "cancelled"]
library.hide(); library.finishTemplate()
precondition(results.count == 1 && library.templateValues.isEmpty, "Escape/outside close cancels without copying or inserting")
var plain = snippet; plain.replacement = "plain text"
library.resolveTemplate(plain, action: .copy) { results.append($0) }
precondition(results.count == 2 && results.last == plain, "ordinary snippets skip the form")
print("Snippet template: parsing, reserved variables, repeated fields, no recursive substitution, native rendering, completion and cancellation passed")
'''
fixture = fixture.replace('// STATE',state).replace('// HIDE',declaration(service,'    func hide('))
source=''
for path in ['Sources/Vorssaint/Services/Snippets/TextSnippetSupport.swift',
             'Sources/Vorssaint/Services/Snippets/SnippetTemplateSupport.swift',
             'Sources/Vorssaint/UI/SnippetTemplateForm.swift']:
    source += (repo/path).read_text()+'\n'
with tempfile.TemporaryDirectory(prefix='snippet-template-tests-') as directory:
    folder=Path(directory);swift=folder/'main.swift';binary=folder/'test'
    swift.write_text(source+'\n'+fixture)
    subprocess.run(['swiftc',str(swift),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
