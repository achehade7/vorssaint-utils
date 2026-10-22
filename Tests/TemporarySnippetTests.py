#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Expiry, collision rules and the OCR save draft, with isolated preferences."""
from pathlib import Path
import subprocess
import os
import tempfile

repo = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import Combine
enum Defaults { static let defaultSnippetSoundName = "Tink" }
enum DefaultsKey { static let textSnippets = "snippets" }
var checks = 0
func expect(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
    checks += 1; if try !value() { fatalError(message) }
}
let domain = "vorss.tests.snippet-save." + UUID().uuidString
let defaults = UserDefaults(suiteName: domain)!
defer { defaults.removePersistentDomain(forName: domain) }
let now = Date()
var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(identifier: "Europe/Berlin")!
let formatter = ISO8601DateFormatter()
let spring = formatter.date(from: "2027-03-28T01:30:00Z")!
let savedData = try TextSnippetSupport.saving(name: "scratch", text: "value", temporary: true,
                                              expected: nil, data: nil, now: spring, calendar: calendar)
let temporary = TextSnippetSupport.decode(savedData, now: spring)[0]
try expect(temporary.expiresAt == formatter.date(from: "2027-03-28T22:00:00Z"), "expiry is next local midnight across DST, not 24 hours")
try expect(TextSnippetSupport.decode(savedData, now: temporary.expiresAt!.addingTimeInterval(-0.01)).count == 1, "available before expiry")
try expect(TextSnippetSupport.decode(savedData, now: temporary.expiresAt!).isEmpty, "unavailable exactly at expiry, including app restart")
var legacy = TextSnippet(); legacy.name = "IBAN"; legacy.replacement = "permanent"; legacy.trigger = ";iban"; legacy.folder = "Banking"
let legacyData = try JSONEncoder().encode([legacy])
try expect(TextSnippetSupport.decode(legacyData).first?.expiresAt == nil, "old JSON with no expiry remains permanent")
do {
    _ = try TextSnippetSupport.saving(name: "iban", text: "temp", temporary: true, expected: legacy, data: legacyData)
    fatalError("must protect permanent name")
} catch TextSnippetSupport.SaveFailure.permanentName { checks += 1 }
var existing = legacy; existing.expiresAt = now.addingTimeInterval(60)
let promoted = try TextSnippetSupport.saving(name: "iban", text: "new value", temporary: false, expected: existing,
                                            data: JSONEncoder().encode([existing]))
let permanent = TextSnippetSupport.decode(promoted)[0]
try expect(permanent.expiresAt == nil && permanent.id == legacy.id && permanent.trigger == legacy.trigger
           && permanent.folder == legacy.folder, "promotion preserves identity/trigger/folder and removes expiry")
var expired = legacy; expired.expiresAt = now.addingTimeInterval(-1)
let reclaimed = try TextSnippetSupport.saving(name: "IBAN", text: "new", temporary: false, expected: nil,
                                             data: JSONEncoder().encode([expired]))
try expect(TextSnippetSupport.decode(reclaimed).count == 1, "expired name can be reclaimed")
try expect(TextSnippetSupport.match(buffer: ";iban", expansion: .afterDelimiter, snippets: [expired]) == nil,
           "cached expired typing trigger cannot run")
try expect(TextSnippetSupport.librarySections([expired], query: "").isEmpty, "cached library hides expired snippets")
let draft = SnippetSaveDraft(text: "OCR column\n123\n456", defaults: defaults)
try expect(defaults.data(forKey: DefaultsKey.textSnippets) == nil && !draft.canSave, "opening or cancelling the form writes nothing")
try expect(draft.temporary, "new OCR drafts default to until midnight")
draft.name = "column"
try expect(draft.text == "OCR column\n123\n456", "draft retains exact captured text, independent of clipboard")
draft.text = "123\n456"
try expect(draft.save(), "editable captured text saves without a clipboard read")
let untilMidnight = TextSnippetSupport.decode(defaults.data(forKey: DefaultsKey.textSnippets))[0]
try expect(untilMidnight.replacement == "123\n456" && untilMidnight.expiresAt == Calendar.current.dateInterval(of: .day, for: Date())!.end,
           "default OCR save keeps line breaks and expires at midnight")
let keepDraft = SnippetSaveDraft(text: "123\n456", defaults: defaults); keepDraft.name = "column"; keepDraft.temporary = false
try expect(!keepDraft.save() && keepDraft.save(), "unchecking until midnight explicitly promotes after confirmation")
let first = TextSnippetSupport.decode(defaults.data(forKey: DefaultsKey.textSnippets))[0]
try expect(first.expiresAt == nil, "unchecked OCR save is permanent")
let clash = SnippetSaveDraft(text: "replacement", defaults: defaults); clash.name = "COLUMN"; clash.temporary = true
try expect(!clash.save() && clash.error == .permanentName && clash.replacement == nil, "OCR temp collision is blocked before confirmation")
clash.temporary = false
try expect(!clash.save() && clash.replacement?.id == first.id, "normal duplicate requires a second explicit save")
clash.text = "changed draft"
try expect(clash.replacement == nil && !clash.save(), "editing invalidates confirmation")
var externallyEdited = first; externallyEdited.replacement = "elsewhere"
defaults.set(try JSONEncoder().encode([externallyEdited]), forKey: DefaultsKey.textSnippets)
try expect(!clash.save() && clash.error == .changed, "concurrent edit invalidates replacement confirmation")
try expect(TextSnippetSupport.decode(defaults.data(forKey: DefaultsKey.textSnippets))[0] == externallyEdited, "concurrent contents preserved")
try expect(!clash.save() && clash.replacement == externallyEdited && clash.save(), "fresh confirmation can replace the new value")
let tempDraft = SnippetSaveDraft(text: "keep", defaults: defaults); tempDraft.name = "today"
try expect(tempDraft.temporary, "a previous permanent save does not change the next draft default")
try expect(tempDraft.save(), "fresh OCR draft uses temporary lifetime")
let promoteDraft = SnippetSaveDraft(text: "forever", defaults: defaults); promoteDraft.name = "TODAY"; promoteDraft.temporary = false
try expect(!promoteDraft.save() && promoteDraft.save(), "OCR permanent save can replace temporary after confirmation")
try expect(TextSnippetSupport.decode(defaults.data(forKey: DefaultsKey.textSnippets)).first { $0.name == "TODAY" }?.expiresAt == nil,
           "promotion clears expiry")
defaults.set(Data("broken".utf8), forKey: DefaultsKey.textSnippets)
let failed = SnippetSaveDraft(text: "do not lose", defaults: defaults); failed.name = "safe"
try expect(!failed.save() && failed.error == .changed && failed.text == "do not lose", "failed save keeps draft")
try expect(defaults.data(forKey: DefaultsKey.textSnippets) == Data("broken".utf8), "corrupt store is never overwritten")
print("Temporary snippets and OCR draft: \(checks) checks passed")
'''
with tempfile.TemporaryDirectory(prefix='temporary-snippet-tests-') as folder:
    main = Path(folder) / 'main.swift'
    main.write_text(code)
    binary = Path(folder) / 'tests'
    subprocess.run(['swiftc', str(repo / 'Sources/Vorssaint/Services/Snippets/TextSnippetSupport.swift'),
                    str(repo / 'Sources/Vorssaint/Services/Snippets/SnippetSaveDraft.swift'), str(main), '-o', str(binary)], check=True)
    preferences = Path(folder) / "preferences"
    preferences.mkdir()
    subprocess.run([str(binary)], env=dict(os.environ, CFFIXED_USER_HOME=str(preferences)), check=True)
