#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Headless production draft lifecycle, delayed operations and real temporary files."""
from quick_capture_fixture import run

run(r'''
typealias Capture = NotchQuickCaptureService
typealias Store = NotchQuickCaptureStore
enum TestFailure: Error { case failed }
let files = FileManager.default
let root = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try files.createDirectory(at: root, withIntermediateDirectories: true)
defer { try? files.removeItem(at: root) }
var checks = 0
func check(_ value: Bool, _ message: String) {
    checks += 1
    precondition(value, message)
}
func wait(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !predicate() && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.005)) }
    check(predicate(), "asynchronous operation completed")
}
func blocks(_ text: String) -> Int { text.split(separator: "\n").filter { $0.hasPrefix("## ") }.count }
func key(_ code: UInt16, modifiers: NSEvent.ModifierFlags = []) -> NSEvent {
    NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: modifiers, timestamp: 0,
                    windowNumber: 0, context: nil, characters: "", charactersIgnoringModifiers: "",
                    isARepeat: false, keyCode: code)!
}
let previousZone = NSTimeZone.default
NSTimeZone.default = TimeZone(identifier: "Europe/Berlin")!
defer { NSTimeZone.default = previousZone }
let iso = ISO8601DateFormatter()
let opening = iso.date(from: "2026-10-23T09:19:00Z")!
func picture(_ value: CGFloat = 0.4) -> CGImage {
    let context = CGContext(data: nil, width: 12, height: 8, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.setFillColor(CGColor(red: value, green: 0.2, blue: 0.8, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: 12, height: 8))
    return context.makeImage()!
}
let image = picture()
struct Fixture {
    let vault: URL, images: URL, note: URL
    let queue = DispatchQueue(label: "capture.lifecycle.fixture")
    init() throws {
        let folder = root.appendingPathComponent(UUID().uuidString)
        vault = folder.appendingPathComponent("vault")
        images = folder.appendingPathComponent("images")
        note = vault.appendingPathComponent("Captures.md")
        try files.createDirectory(at: vault, withIntermediateDirectories: true)
    }
    func body() throws -> String {
        files.fileExists(atPath: note.path) ? try String(contentsOf: note, encoding: .utf8) : ""
    }
    func service(now: @escaping () -> Date = { opening },
                 load: @escaping Capture.MeetingLoader = { _, completion in completion(.success([])) },
                 resolve: Capture.NoteResolver? = nil,
                 recognize: Capture.Recognizer? = nil,
                 operations: Store.FileOperations = .init()) -> Capture {
        Capture(store: Store(vault: vault, screenshots: images, operations: operations), now: now,
                io: queue, loadMeetings: load, resolveNote: resolve, recognize: recognize)
    }
}
func completePicture(_ draft: Capture, at date: Date, value: CGFloat = 0.4, modifiers: NSEvent.ModifierFlags = []) {
    let selector = ScreenshotSelectionController.last!
    selector.onSelectionBegan?(modifiers)
    selector.complete(.captured(.init(image: picture(value), capturedAt: date)))
}
func acceptImage(_ draft: Capture, at date: Date = opening) {
    draft.receiveImage(image, capturedAt: date)
    wait { draft.pendingCount == 0 }
}
func choice(_ id: String = "meeting", title: String = "Weekly review", start: Date = opening.addingTimeInterval(-1800)) -> Capture.MeetingChoice {
    .init(id: id, title: title, input: .init(identity: id, title: title, start: start,
                                           end: opening.addingTimeInterval(60), people: []))
}


// Meeting context uses the same anonymized topic with and without an existing note.
for linked in [false, true] {
    let fixture = try Fixture()
    let people = [MeetingNotePerson(name: "Anwar Chehade", isCurrentUser: true),
                  MeetingNotePerson.attendee(name: nil, url: URL(string: "mailto:zorvyn.reed@example.invalid"), isCurrentUser: false)!]
    let input = MeetingNoteInput(identity: "private-meeting", title: "O3 - Anwar - Zorvyn", start: opening,
                                 end: opening.addingTimeInterval(1800), people: people)
    let selection = Capture.MeetingChoice(id: "private-meeting", title: input.title, input: input)
    let note = fixture.vault.appendingPathComponent("meetings/O3 Z.R..md")
    var resolve: ((Result<URL?, Error>) -> Void)?
    let draft = fixture.service(load: { _, done in done(.success([selection])) }, resolve: { _, done in resolve = done })
    draft.open(); draft.text = "Meeting thought"
    check(draft.meeting?.title == "O3 - Z.R.", "pending meeting context already uses cleaned title")
    resolve?(.success(linked ? note : nil))
    check(draft.meeting?.title == "O3 - Z.R.", "note resolution retains cleaned title")
    draft.save(); wait { !draft.saving }
    let body = try fixture.body()
    let expected = linked ? "Meeting: [O3 - Z.R.](<meetings/O3%20Z.R..md>)" : "Meeting: O3 - Z.R."
    check(body.contains(expected + " · 2026-10-23T11:19:00+02:00"), "Meeting line preserves link and timestamp format")
    check(!body.contains("Anwar") && !body.contains("Zorvyn") && !body.contains("@"), "capture metadata contains only initials")
}

// Original stale-count regression, including both ordinary and repeated shots.
let seven = try Fixture()
let draft = seven.service()
draft.open(); draft.text = "All seven pictures belong to this thought."
for index in 0..<3 {
    draft.captureRegion()
    check(ScreenshotSelectionController.last!.freeze, "single region uses frozen selection")
    completePicture(draft, at: opening.addingTimeInterval(Double(index)))
    wait { draft.pendingCount == 0 }
    check(!draft.isSelecting && !draft.capturingGroup, "single region always returns after one capture")
}
draft.captureGroup()
for index in 3..<7 {
    check(!ScreenshotSelectionController.last!.freeze, "repeated capture uses live selection")
    completePicture(draft, at: opening.addingTimeInterval(Double(index)))
    wait { draft.isSelecting && draft.images.count == index + 1 && draft.images.allSatisfy { $0.file != nil } }
}
draft.pauseGroupCapture()
check(draft.imageCount == 7 && !draft.capturingGroup && draft.pendingCount == 0, "pause retains every current-capture image")
check(try seven.body().isEmpty, "pause never publishes a group summary")
let firstImageFiles = draft.images.compactMap(\.file)
draft.hide(); draft.open()
check(draft.imageCount == 7 && draft.text.contains("seven"), "hide/reopen preserves one draft")
draft.save(); draft.save()
wait { !draft.saving }
check(draft.images.isEmpty && draft.extracts.isEmpty && draft.text.isEmpty && !draft.capturingGroup && draft.pendingCount == 0,
      "successful Save completely resets contents, counter and collection mode")
check(blocks(try seven.body()) == 1, "seven images and thought publish once")
draft.open(); draft.text = "Second thought without a picture"; draft.save()
wait { !draft.saving }
let sevenBody = try seven.body()
check(blocks(sevenBody) == 2 && sevenBody.components(separatedBy: "### Screenshots").count == 2,
      "second text-only capture carries no old images")
check(firstImageFiles.allSatisfy { files.fileExists(atPath: $0.path) }, "reset never deletes published images")

// Only repeated selection uses the mouse-down Command modifier to choose text.
// No held-key history carries between drags or changes the one-shot tools.
let commandDrag = try Fixture()
let commandDraft = commandDrag.service(recognize: { _, done in done(.success("Command-drag text")) })
commandDraft.captureGroup()
check(ScreenshotSelectionController.last!.freezeOnCommand, "repeated capture enables press-Command freezing")
completePicture(commandDraft, at: opening, modifiers: .command)
wait { commandDraft.isSelecting && commandDraft.extracts.count == 1 }
check(commandDraft.images.isEmpty, "Command-drag in repeat mode creates text without an image")
completePicture(commandDraft, at: opening.addingTimeInterval(1))
wait { commandDraft.isSelecting && commandDraft.imageCount == 1 }
check(commandDraft.extracts.count == 1, "next plain drag captures an image without stale text intent")
completePicture(commandDraft, at: opening.addingTimeInterval(2), modifiers: [.command, .shift])
wait { commandDraft.isSelecting && commandDraft.extracts.count == 2 }
check(commandDraft.imageCount == 1, "Command text mode can accompany a square selection")
commandDraft.pauseGroupCapture()
commandDraft.captureRegion()
check(!ScreenshotSelectionController.last!.freezeOnCommand, "single Region keeps its existing frozen source")
completePicture(commandDraft, at: opening.addingTimeInterval(3), modifiers: .command)
wait { commandDraft.pendingCount == 0 }
check(commandDraft.imageCount == 2 && commandDraft.extracts.count == 2,
      "single Region remains an image even with Command held")
commandDraft.captureText()
check(!ScreenshotSelectionController.last!.freezeOnCommand, "single Text keeps its existing frozen source")
completePicture(commandDraft, at: opening.addingTimeInterval(4))
wait { commandDraft.pendingCount == 0 }
check(commandDraft.extracts.count == 3, "single Text remains OCR without a modifier")
commandDraft.save(); wait { !commandDraft.saving }
let commandBody = try commandDrag.body()
check(blocks(commandBody) == 1 && commandBody.contains("### Screenshots") && commandBody.contains("### Text extracts"),
      "alternating image and Command-drag text selections publish one capture")

// Repeat-selector totals describe the whole draft and refresh after each result,
// including the new selector shown after Cmd-Z finishes removing an image.
let counted = try Fixture()
let countedDraft = counted.service(recognize: { _, done in done(.success("Counted text")) })
func checkSelectorCounts(_ images: Int, _ extracts: Int, _ reason: String) {
    let strings = NotchQuickCaptureStrings.localized(L10n.shared.language)
    let expected = String(format: strings.count, images, extracts)
    check(ScreenshotSelectionController.last?.purpose?.hasPrefix(expected) == true, reason)
}
countedDraft.captureGroup()
checkSelectorCounts(0, 0, "new repeat selector starts with zero image and text totals")
completePicture(countedDraft, at: opening)
wait { countedDraft.isSelecting && countedDraft.imageCount == 1 }
checkSelectorCounts(1, 0, "repeat selector shows the newly persisted image")
completePicture(countedDraft, at: opening.addingTimeInterval(1), modifiers: .command)
wait { countedDraft.isSelecting && countedDraft.extracts.count == 1 }
checkSelectorCounts(1, 1, "repeat selector shows recognized text without incrementing images")
let beforeUndo = ScreenshotSelectionController.last!
let selectorUndo = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: .command,
    timestamp: 0, windowNumber: 0, context: nil, characters: "z", charactersIgnoringModifiers: "z",
    isARepeat: false, keyCode: 6)!
check(countedDraft.handleKey(selectorUndo, selecting: true), "Cmd-Z is routed to screenshot undo in selection")
wait { countedDraft.isSelecting && countedDraft.imageCount == 0 && ScreenshotSelectionController.last !== beforeUndo }
checkSelectorCounts(0, 1, "new selector confirms Cmd-Z by reducing image count and preserving text count")
countedDraft.pauseGroupCapture()
countedDraft.captureRegion()
completePicture(countedDraft, at: opening.addingTimeInterval(2))
wait { countedDraft.pendingCount == 0 }
countedDraft.captureGroup()
checkSelectorCounts(1, 1, "repeat totals include a one-shot region captured while repetition was paused")
countedDraft.pauseGroupCapture()
for language in AppLanguage.allCases {
    L10n.shared.language = language
    countedDraft.captureGroup()
    checkSelectorCounts(1, 1, "repeat totals use the selected language: " + language.rawValue)
    countedDraft.pauseGroupCapture()
}
L10n.shared.language = .enUS
countedDraft.discard(); countedDraft.captureGroup()
checkSelectorCounts(0, 0, "discarded counts never enter the next repeat capture")
countedDraft.discard()

// Mouse-up accepts acquisition before asynchronous pixels become available.
// Save/hide must retain that accepted region; Discard invalidates it instead.
for textOnly in [false, true] {
    let acquiring = try Fixture()
    var recognized: ((Result<String, Error>) -> Void)?
    let acquiringDraft = acquiring.service(recognize: { _, done in recognized = done })
    if textOnly { acquiringDraft.captureText() } else { acquiringDraft.captureRegion() }
    let selector = ScreenshotSelectionController.last!
    selector.onSelectionBegan?([]); selector.isAcquiring = true
    if !textOnly { acquiringDraft.text = "Save includes accepted delayed picture" }
    acquiringDraft.save(); acquiringDraft.hide()
    check(acquiringDraft.saving && !acquiringDraft.publishing && acquiringDraft.isSelecting,
          "Save and hide preserve accepted acquisition, including capture-only drafts")
    check(try acquiring.body().isEmpty, "accepted acquisition cannot publish a partial snapshot")
    selector.complete(.captured(.init(image: image, capturedAt: opening.addingTimeInterval(19))))
    if textOnly {
        check(acquiringDraft.saving && acquiringDraft.pendingCount == 1, "accepted text acquisition still waits for OCR")
        recognized?(.success("Late pixels\nLate recognition"))
    }
    wait { !acquiringDraft.saving }
    let acquiringBody = try acquiring.body()
    check(blocks(acquiringBody) == 1 && acquiringBody.contains("11:19:19+02:00"),
          "accepted delayed capture retains acquisition timestamp and publishes once")
    check(acquiringBody.contains(textOnly ? "Late pixels\nLate recognition" : "01.png"),
          "accepted delayed pixels enter fixed Save snapshot")
}

let discardedAcquisition = try Fixture()
let discardedAcquisitionDraft = discardedAcquisition.service()
discardedAcquisitionDraft.captureRegion()
let abandonedSelector = ScreenshotSelectionController.last!
abandonedSelector.onSelectionBegan?([]); abandonedSelector.isAcquiring = true
let latePixels = abandonedSelector.completion!
discardedAcquisitionDraft.save(); discardedAcquisitionDraft.discard()
discardedAcquisitionDraft.open(); discardedAcquisitionDraft.text = "Replacement after acquisition"
latePixels(.captured(.init(image: image, capturedAt: opening)))
check(discardedAcquisitionDraft.images.isEmpty && discardedAcquisitionDraft.pendingCount == 0,
      "Discard invalidates accepted acquisition callback before next draft")
discardedAcquisitionDraft.save(); wait { !discardedAcquisitionDraft.saving }
check(!(try discardedAcquisition.body()).contains("### Screenshots"), "old pixels cannot publish through next draft")

let inactive = try Fixture()
var idleClock = opening
let idleDraft = inactive.service(now: { idleClock })
acceptImage(idleDraft)
idleDraft.captureGroup(); idleDraft.pauseGroupCapture()
idleClock = opening.addingTimeInterval(24 * 60 * 60)
idleDraft.hide(); idleDraft.stop(); idleDraft.open()
check(idleDraft.images.count == 1 && !idleDraft.capturingGroup, "inactivity/teardown preserve draft and pause collection")
check(try inactive.body().isEmpty, "inactivity never publishes independent screenshot summary")
idleDraft.discard()
check(idleDraft.images.isEmpty && idleDraft.text.isEmpty && idleDraft.pendingCount == 0, "Discard completely resets unpublished idle capture")

// Required jobs settle before immutable publication. Hide/reopen and duplicate
// Save requests do not restart lookups or omit delayed OCR/meeting results.
let delayed = try Fixture()
var calendarCallbacks: [(Result<[Capture.MeetingChoice], Error>) -> Void] = []
var noteCallbacks: [(Result<URL?, Error>) -> Void] = []
var textCallbacks: [(Result<String, Error>) -> Void] = []
var loadDates: [Date] = []
let pending = delayed.service(load: { date, done in loadDates.append(date); calendarCallbacks.append(done) },
    resolve: { _, done in noteCallbacks.append(done) }, recognize: { _, done in textCallbacks.append(done) })
pending.open(); pending.text = "Thought with pending context"
pending.receiveTextImage(image, capturedAt: opening.addingTimeInterval(13))
pending.save(); pending.save()
check(pending.saving && !pending.publishing && pending.pendingCount == 2, "Save waits for calendar and OCR")
check(try delayed.body().isEmpty, "waiting Save publishes no partial block")
pending.hide(); pending.open()
check(calendarCallbacks.count == 1 && loadDates == [opening], "resuming preserves original meeting read")
textCallbacks[0](.success("First OCR line\nSecond OCR line"))
check(pending.saving && pending.pendingCount == 1, "completed OCR still waits for meeting")
calendarCallbacks[0](.success([choice()]))
check(noteCallbacks.count == 1 && pending.saving && pending.pendingCount == 1, "meeting selection waits for existing-note lookup")
let existing = delayed.vault.appendingPathComponent("meetings/Existing.md")
try files.createDirectory(at: existing.deletingLastPathComponent(), withIntermediateDirectories: true)
try Data("Untouched existing meeting".utf8).write(to: existing)
noteCallbacks[0](.success(existing))
wait { !pending.saving }
let pendingBody = try delayed.body()
check(blocks(pendingBody) == 1 && pendingBody.contains("First OCR line\nSecond OCR line"), "one complete delayed capture")
check(pendingBody.contains("meetings/Existing.md") && pendingBody.contains("meeting +00:30:13"), "resolved note and original OCR acquisition offset included")
check(try String(contentsOf: existing, encoding: .utf8) == "Untouched existing meeting", "meeting reference never edits note")
textCallbacks[0](.success("Duplicate late completion")); calendarCallbacks[0](.success([choice("late")]))
check(pending.images.isEmpty && pending.extracts.isEmpty && pending.meeting == nil, "duplicate completions cannot enter reset draft")

// Discard while Save waits invalidates all prior jobs. Old calendar/OCR results
// cannot start note resolution, mutate the next draft, or schedule publication.
let abandoned = try Fixture()
var oldCalendar: [(Result<[Capture.MeetingChoice], Error>) -> Void] = []
var oldOCR: [(Result<String, Error>) -> Void] = []
var resolves = 0
let abandonedDraft = abandoned.service(load: { _, done in oldCalendar.append(done) },
    resolve: { _, done in resolves += 1; done(.success(nil)) }, recognize: { _, done in oldOCR.append(done) })
abandonedDraft.open(); abandonedDraft.text = "Discard me"
abandonedDraft.receiveTextImage(image, capturedAt: opening)
abandonedDraft.save(); check(abandonedDraft.canDiscard, "waiting Save remains discardable")
abandonedDraft.discard(); abandonedDraft.open(); abandonedDraft.text = "Only the replacement thought"
oldOCR[0](.success("Old text")); oldCalendar[0](.success([choice("old")]))
check(abandonedDraft.extracts.isEmpty && abandonedDraft.meeting == nil && resolves == 0,
      "discard invalidates OCR and calendar before any dependent lookup")
abandonedDraft.save(); oldCalendar[1](.success([])); wait { !abandonedDraft.saving }
let replacementBody = try abandoned.body()
check(blocks(replacementBody) == 1 && !replacementBody.contains("Old text"), "only new draft is published")

// A superseded note lookup also cannot restore an explicitly removed meeting.
let removedMeeting = try Fixture()
var lateNote: ((Result<URL?, Error>) -> Void)?
let withoutMeeting = removedMeeting.service(load: { _, done in done(.success([choice()])) },
    resolve: { _, done in lateNote = done })
withoutMeeting.open(); withoutMeeting.text = "No meeting context"
withoutMeeting.chooseMeeting(nil)
lateNote?(.success(existing))
check(withoutMeeting.meeting == nil && withoutMeeting.pendingCount == 0, "removing meeting invalidates pending note lookup")
withoutMeeting.save(); wait { !withoutMeeting.saving }
check(!(try removedMeeting.body()).contains("Meeting:"), "explicit no-meeting choice is saved")

// Opening-time filtering includes late ongoing meetings; context stays fixed
// after their end. Missing note folders and denied calendars create no notes.
let events = [NotchCalendarEvent(id: "late", title: "Late ongoing", start: opening.addingTimeInterval(-1800), end: opening.addingTimeInterval(5)),
              NotchCalendarEvent(id: "future", start: opening.addingTimeInterval(1), end: opening.addingTimeInterval(90)),
              NotchCalendarEvent(id: "ended", start: opening.addingTimeInterval(-60), end: opening),
              NotchCalendarEvent(id: "day", start: opening.addingTimeInterval(-3600), end: opening.addingTimeInterval(3600), allDay: true)]
check(NotchQuickCaptureMeetings.choices(events, at: opening).map(\.id) == ["late"], "ongoing filter uses opening instant, not five-minute suggestion window")
let contextFixture = try Fixture()
var clock = opening
let contextDraft = contextFixture.service(now: { clock }, load: { at, done in done(.success(NotchQuickCaptureMeetings.choices(events, at: at))) })
contextDraft.open(); wait { contextDraft.pendingCount == 0 }
check(contextDraft.meeting?.title == "Late ongoing" && contextDraft.meeting?.note == nil && !contextDraft.hasFailedWork,
      "absent meeting folder resolves title without creating a note")
clock = opening.addingTimeInterval(4000)
contextDraft.hide(); contextDraft.open()
check(contextDraft.meeting?.title == "Late ongoing", "meeting ending does not replace fixed context")
contextDraft.text = "Capture after meeting ended"; contextDraft.save(); wait { !contextDraft.saving }
check(!files.fileExists(atPath: contextFixture.vault.appendingPathComponent("meetings").path), "no automatic meeting-note creation")
let denied = try Fixture()
NotchCalendarService.shared.events = events; NotchCalendarService.shared.authorized = false
let deniedDraft = Capture(store: .init(vault: denied.vault, screenshots: denied.images), now: { opening }, io: denied.queue)
deniedDraft.open(); wait { deniedDraft.pendingCount == 0 }
check(deniedDraft.meeting == nil && !deniedDraft.needsMeetingChoice, "unavailable calendar context settles without blocking text")
deniedDraft.text = "No calendar access"; deniedDraft.save(); wait { !deniedDraft.saving }
NotchCalendarService.shared.authorized = true
let overlap = try Fixture()
let overlapDraft = overlap.service(load: { _, done in done(.success([choice("a"), choice("b")])) }, resolve: { _, done in done(.success(nil)) })
overlapDraft.open(); overlapDraft.text = "Choose this meeting"
check(overlapDraft.needsMeetingChoice && !overlapDraft.canSave, "overlap never guesses context")
overlapDraft.save(); check(try overlap.body().isEmpty, "unresolved overlap cannot publish")
overlapDraft.chooseMeeting("b"); check(overlapDraft.meeting?.title == "Weekly review", "explicit overlap choice retained")
overlapDraft.save(); wait { !overlapDraft.saving }

// OCR ordering is acquisition ordering, regardless of recognition completion.
// A failed/empty result aborts waiting Save and can be retried or removed.
let ocr = try Fixture()
var ocrCallbacks: [(Result<String, Error>) -> Void] = []
let ocrDraft = ocr.service(recognize: { _, done in ocrCallbacks.append(done) })
ocrDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(3))
ocrDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(8))
ocrCallbacks[1](.success("second\nlines")); ocrCallbacks[0](.success("first\nlines"))
check(ocrDraft.extracts.map(\.text) == ["first\nlines", "second\nlines"], "OCR callback ordering cannot reorder captures")
check(ocrDraft.extracts.map(\.capturedAt) == [opening.addingTimeInterval(3), opening.addingTimeInterval(8)], "OCR retains original acquisition times")
ocrDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(12)); ocrDraft.save()
ocrCallbacks[2](.failure(TestFailure.failed))
let beforeOCRRetry = try ocr.body()
check(!ocrDraft.saving && ocrDraft.hasFailedWork && ocrDraft.error == .ocr && beforeOCRRetry.isEmpty,
      "recognition failure aborts pending Save instead of omitting content")
ocrDraft.retryFailedWork(); ocrCallbacks[3](.success("retried\ntext"))
check(ocrDraft.extracts.last?.capturedAt == opening.addingTimeInterval(12), "OCR retry retains acquisition time")
ocrDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(15)); ocrCallbacks[4](.success(" \n "))
check(ocrDraft.hasFailedAttachments, "empty OCR is actionable failure")
ocrDraft.removeFailedAttachments(); ocrDraft.save(); wait { !ocrDraft.saving }
let savedOCR = try ocr.body()
check(blocks(savedOCR) == 1 && savedOCR.contains("retried\ntext"), "explicit removal allows remaining OCR to publish once")

// Preview edits belong to one existing extract. They preserve acquisition
// metadata and cannot alter a waiting/fixed Save or resurrect a removed draft.
let editableOCR = try Fixture()
let editable = editableOCR.service(load: { _, done in done(.success([choice()])) },
                                   resolve: { _, done in done(.success(nil)) })
editable.receiveTextImage(image, capturedAt: opening.addingTimeInterval(4))
editable.receiveTextImage(image, capturedAt: opening.addingTimeInterval(7))
let editedID = editable.extracts[0].id
let removedID = editable.extracts[1].id
editable.updateExtract(editedID, text: "Corrected first line\nSecond edited line")
check(editable.extracts.map(\.id) == [editedID, removedID]
      && editable.extracts[0].capturedAt == opening.addingTimeInterval(4)
      && editable.extracts[0].text == "Corrected first line\nSecond edited line",
      "OCR edit preserves identity, order, acquisition time and line breaks")
editable.removeExtract(removedID)
editable.updateExtract(removedID, text: "Late removed-editor callback")
check(editable.extracts.map(\.id) == [editedID], "late edit cannot recreate removed extract")
editable.hide(); editable.open()
check(editable.extracts[0].text == "Corrected first line\nSecond edited line", "edited extract survives hide/reopen")
editableOCR.queue.suspend()
editable.save()
check(editable.publishing && !editable.canEdit, "publication freezes OCR edits")
editable.updateExtract(editedID, text: "Too late for fixed snapshot")
check(editable.extracts[0].text == "Corrected first line\nSecond edited line", "late edit cannot change publishing draft")
editableOCR.queue.resume(); wait { !editable.saving }
let editedBody = try editableOCR.body()
check(editedBody.contains("Corrected first line\nSecond edited line") && !editedBody.contains("Too late")
      && editedBody.contains("11:19:04+02:00 · meeting +00:30:04"),
      "Save publishes corrected OCR with unchanged timestamp and meeting offset")
editable.updateExtract(editedID, text: "Late saved-editor callback")
check(editable.extracts.isEmpty && editable.pendingCount == 0, "late edit cannot recreate a successfully saved draft")
editable.receiveTextImage(image, capturedAt: opening.addingTimeInterval(11))
let discardedEditID = editable.extracts[0].id
editable.discard(); editable.receiveTextImage(image, capturedAt: opening.addingTimeInterval(12))
let newExtract = editable.extracts[0]
editable.updateExtract(discardedEditID, text: "Late discarded-editor callback")
check(editable.extracts.count == 1 && editable.extracts[0].id == newExtract.id && editable.extracts[0].text == newExtract.text,
      "discarded editor callback cannot modify a new draft")
editable.discard()

let waitingEdit = try Fixture()
var settleEditMeeting: ((Result<[Capture.MeetingChoice], Error>) -> Void)?
let waitingEditDraft = waitingEdit.service(load: { _, done in settleEditMeeting = done })
waitingEditDraft.receiveTextImage(image, capturedAt: opening)
let waitingExtract = waitingEditDraft.extracts[0]
waitingEditDraft.updateExtract(waitingExtract.id, text: "Accepted edit before Save")
waitingEditDraft.save()
waitingEditDraft.updateExtract(waitingExtract.id, text: "Edit while Save waits")
check(waitingEditDraft.saving && !waitingEditDraft.publishing
      && waitingEditDraft.extracts[0].text == "Accepted edit before Save",
      "Save blocks edits while required lookup is pending, before snapshot creation")
settleEditMeeting?(.success([])); wait { !waitingEditDraft.saving }
let waitingEditBody = try waitingEdit.body()
check(waitingEditBody.contains("Accepted edit before Save") && !waitingEditBody.contains("Edit while Save waits"),
      "waiting Save includes only pre-boundary OCR edit")

let blankOCR = try Fixture()
let blankDraft = blankOCR.service()
blankDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(6))
let blankID = blankDraft.extracts[0].id
let blankText = " \n\0\t "
blankDraft.updateExtract(blankID, text: blankText)
check(!blankDraft.canSave && blankDraft.extracts[0].text == blankText,
      "whitespace/NUL-only OCR remains editable but cannot save an empty draft")
blankDraft.save()
let blankOnlyBody = try blankOCR.body()
check(!blankDraft.saving && blankOnlyBody.isEmpty, "blank-only OCR Save publishes nothing")
blankDraft.updateExtract(blankID, text: "Restored text\nRestored line")
check(blankDraft.canSave && blankDraft.extracts[0].id == blankID
      && blankDraft.extracts[0].capturedAt == opening.addingTimeInterval(6),
      "undo-like restoration of deleted text keeps extract identity and becomes saveable")
blankDraft.updateExtract(blankID, text: blankText)
blankDraft.text = "A thought with an emptied OCR preview"
acceptImage(blankDraft)
check(blankDraft.canSave, "blank OCR cannot block other capture content")
blankDraft.save(); wait { !blankDraft.saving }
let mixedBlankBody = try blankOCR.body()
check(mixedBlankBody.contains("A thought with an emptied OCR preview") && mixedBlankBody.contains("01.png")
      && !mixedBlankBody.contains("### Text extracts"), "mixed Save omits empty edited extract and retains thought/image")
blankDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(14))
let restoredID = blankDraft.extracts[0].id
blankDraft.updateExtract(restoredID, text: blankText)
blankDraft.updateExtract(restoredID, text: "Restored after delete-all\nSecond line")
blankDraft.save(); wait { !blankDraft.saving }
let restoredBody = try blankOCR.body()
check(blocks(restoredBody) == 2 && restoredBody.contains("Restored after delete-all\nSecond line")
      && restoredBody.contains("11:19:14+02:00"), "restored edited OCR publishes with original metadata")

// Main editor Cmd-W discards, Escape only hides, and Cmd-S retains Save routing.
// Selector-specific handling is unchanged and does not accept Cmd-W or Cmd-S.
let closing = try Fixture()
let closingDraft = closing.service()
closingDraft.open(); closingDraft.text = "Thought retained by Escape"
acceptImage(closingDraft)
closingDraft.receiveTextImage(image, capturedAt: opening)
let closeExtractID = closingDraft.extracts[0].id
check(closingDraft.handleKey(key(53), selecting: false), "Escape is handled by main editor")
check(!NotchService.shared.showingQuickCapture && closingDraft.images.count == 1
      && closingDraft.extracts.count == 1 && closingDraft.text == "Thought retained by Escape",
      "Escape collapses and preserves complete draft")
closingDraft.open()
check(!closingDraft.handleKey(key(13), selecting: false) && !closingDraft.text.isEmpty, "bare W cannot discard draft")
check(!closingDraft.handleKey(key(13, modifiers: .command), selecting: true)
      && !closingDraft.handleKey(key(1, modifiers: .command), selecting: true),
      "selector Cmd-W/Cmd-S routes remain untouched")
check(closingDraft.handleKey(key(13, modifiers: .command), selecting: false), "Cmd-W is handled by main editor")
check(!NotchService.shared.showingQuickCapture && closingDraft.text.isEmpty && closingDraft.images.isEmpty
      && closingDraft.extracts.isEmpty && closingDraft.pendingCount == 0 && !closingDraft.capturingGroup,
      "main Cmd-W discards whole draft and collapses")
closingDraft.updateExtract(closeExtractID, text: "Late editor callback after Cmd-W")
let beforeCloseSave = try closing.body()
check(closingDraft.extracts.isEmpty && beforeCloseSave.isEmpty, "Cmd-W publishes nothing and invalidates late editor updates")
closingDraft.open(); closingDraft.text = "Cmd-S publishes this replacement"
check(closingDraft.handleKey(key(1, modifiers: .command), selecting: false), "main Cmd-S still requests Save")
wait { !closingDraft.saving }
check(blocks(try closing.body()) == 1 && closingDraft.text.isEmpty, "main Cmd-S publishes and resets")

// Both confirmed append failure and an uncertain append retain the complete
// draft. Reconciliation acknowledges the existing block without duplicate files.
let retry = try Fixture()
try Data("Existing user text".utf8).write(to: retry.note)
let retryDraft = retry.service()
acceptImage(retryDraft); retryDraft.text = "Retry this complete capture"
let retainedFiles = retryDraft.images.compactMap(\.file)
let noteLock = Darwin.open(retry.note.path, O_RDWR)
check(flock(noteLock, LOCK_EX | LOCK_NB) == 0, "fixture holds publication lock")
retryDraft.save(); wait { !retryDraft.saving }
check(retryDraft.error == .save && retryDraft.canEdit && retryDraft.images.count == 1 && !retryDraft.text.isEmpty,
      "confirmed append failure retains editable thought and images")
flock(noteLock, LOCK_UN); Darwin.close(noteLock)
retryDraft.save(); wait { !retryDraft.saving }
check(blocks(try retry.body()) == 1, "confirmed failure retry publishes one complete entry")
check(retainedFiles.allSatisfy { files.fileExists(atPath: $0.path) }, "publication retries retain persisted files")

let uncertainty = try Fixture()
var failSync = true
var writes = 0
var operations = Store.FileOperations()
operations.write = { fd, data in writes += 1; return data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) } }
operations.synchronize = { fd in if failSync { errno = EIO; return -1 }; return fsync(fd) }
operations.truncate = { fd, size in if failSync { errno = EIO; return -1 }; return ftruncate(fd, size) }
let uncertainDraft = uncertainty.service(operations: operations)
acceptImage(uncertainDraft); uncertainDraft.text = "Keep ambiguous publication evidence"
uncertainDraft.receiveTextImage(image, capturedAt: opening.addingTimeInterval(5))
let uncertainExtract = uncertainDraft.extracts[0]
let uncertainFiles = uncertainDraft.images.compactMap(\.file)
uncertainDraft.save(); wait { !uncertainDraft.saving }
check(uncertainDraft.error == .uncertain && !uncertainDraft.canEdit && uncertainDraft.images.count == 1,
      "uncertain append retains draft and prevents mutable retries")
uncertainDraft.updateExtract(uncertainExtract.id, text: "Edit forbidden during uncertain append")
check(uncertainDraft.extracts[0].text == uncertainExtract.text, "uncertain append blocks OCR edits until reconciled")
check(blocks(try uncertainty.body()) == 1, "ambiguous block may already exist")
failSync = false; uncertainDraft.retryFailedWork(); wait { !uncertainDraft.saving }
check(writes == 1 && uncertainDraft.images.isEmpty && uncertainDraft.error == nil,
      "service reconciliation acknowledges existing block then resets")
check(blocks(try uncertainty.body()) == 1 && uncertainFiles.allSatisfy { files.fileExists(atPath: $0.path) },
      "reconciliation neither duplicates block nor discards its images")

// Full-size pixels persist while previews become bounded thumbnails.
let large = try Fixture()
let largeDraft = large.service()
let largeContext = CGContext(data: nil, width: 1600, height: 900, bitsPerComponent: 8, bytesPerRow: 0,
                             space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
largeDraft.receiveImage(largeContext.makeImage()!, capturedAt: opening)
wait { largeDraft.pendingCount == 0 }
let preview = largeDraft.images[0]
check(max(preview.image.width, preview.image.height) <= 176, "persisted thumbnail releases full-resolution preview")
let persisted = NSBitmapImageRep(data: try Data(contentsOf: preview.file!))!
check(persisted.pixelsWide == 1600 && persisted.pixelsHigh == 900, "preview scaling never resizes persisted image")
largeDraft.discard()

// A suspended real serial queue provides deterministic pending persistence,
// accepted undo, reorder, Discard and publication-boundary coverage.
let serial = try Fixture()
let serialDraft = serial.service()
serial.queue.suspend()
serialDraft.receiveImage(image, capturedAt: opening)
serialDraft.receiveImage(picture(0.6), capturedAt: opening.addingTimeInterval(1))
serialDraft.text = "Keep only first image"
serialDraft.undoLastScreenshot(); serialDraft.save()
check(serialDraft.saving && !serialDraft.publishing, "Save waits behind accepted persistence and queued undo")
serial.queue.resume(); wait { !serialDraft.saving }
let serialBody = try serial.body()
check(blocks(serialBody) == 1 && serialBody.contains("01.png") && !serialBody.contains("02.png"), "queued latest-image undo completes before publication")

let discardedIO = try Fixture()
let discardedIODraft = discardedIO.service()
discardedIO.queue.suspend()
discardedIODraft.receiveImage(image, capturedAt: opening)
discardedIODraft.save(); discardedIODraft.discard()
discardedIODraft.receiveImage(picture(0.7), capturedAt: opening.addingTimeInterval(8))
discardedIODraft.text = "New draft after discarded I/O"; discardedIODraft.save()
discardedIO.queue.resume(); wait { !discardedIODraft.saving }
let discardedIOBody = try discardedIO.body()
check(blocks(discardedIOBody) == 1 && discardedIOBody.contains("11:19:08+02:00"), "discarded persistence cannot enter next snapshot")

let reordered = try Fixture()
let reorderedDraft = reordered.service()
for value in 0..<3 { reorderedDraft.receiveImage(picture(CGFloat(value) / 3), capturedAt: opening.addingTimeInterval(Double(value))); wait { reorderedDraft.pendingCount == 0 } }
let identities = reorderedDraft.images.map(\.id)
let imageFiles = reorderedDraft.images.compactMap(\.file)
let originalBytes = try imageFiles.map { try Data(contentsOf: $0) }
reordered.queue.suspend()
check(reorderedDraft.moveImage(identities[2], to: identities[0]), "reorder accepted")
reorderedDraft.save(); reordered.queue.resume(); wait { !reorderedDraft.saving }
check(try Data(contentsOf: imageFiles[0]) == originalBytes[2], "reordering changes file numbering without changing pixels")
let reorderBody = try reordered.body()
let orderedTimes = ["11:19:02+02:00", "11:19:00+02:00", "11:19:01+02:00"].map { reorderBody.range(of: $0, range: reorderBody.range(of: "### Screenshots")!.upperBound..<reorderBody.endIndex)!.lowerBound }
check(orderedTimes[0] < orderedTimes[1] && orderedTimes[1] < orderedTimes[2], "timestamp identity follows images through reorder and pending Save")

for mutation in ["reorder", "undo"] {
    let failure = try Fixture()
    let failing = failure.service()
    acceptImage(failing); acceptImage(failing, at: opening.addingTimeInterval(1))
    let folder = failing.images[0].file!.deletingLastPathComponent()
    let obstruction = folder.appendingPathComponent("unrelated.txt")
    try Data("preserve this".utf8).write(to: obstruction)
    failure.queue.suspend()
    if mutation == "reorder" { check(failing.moveImage(failing.images[1].id, to: failing.images[0].id), "reorder queued before failure") }
    else { failing.undoLastScreenshot() }
    failing.save(); failure.queue.resume(); wait { !failing.saving && failing.pendingCount == 0 }
    let failedBody = try failure.body()
    check(failing.hasFailedWork && failing.error == .save && failedBody.isEmpty, "failed \(mutation) aborts Save")
    check(try String(contentsOf: obstruction, encoding: .utf8) == "preserve this", "mutation failure preserves unrelated file")
    try files.removeItem(at: obstruction)
    failing.retryFailedWork(); wait { failing.pendingCount == 0 }
    check(!failing.hasFailedWork, "failed \(mutation) can be retried explicitly")
    failing.save(); wait { !failing.saving }
    check(blocks(try failure.body()) == 1, "retried \(mutation) publishes once")
}

for mutation in ["reorder", "undo"] {
    let abandonedMutation = try Fixture()
    let abandoned = abandonedMutation.service()
    acceptImage(abandoned); acceptImage(abandoned, at: opening.addingTimeInterval(1))
    abandonedMutation.queue.suspend()
    if mutation == "reorder" { check(abandoned.moveImage(abandoned.images[1].id, to: abandoned.images[0].id), "reorder starts") }
    else { abandoned.undoLastScreenshot() }
    abandoned.save(); abandoned.discard(); abandoned.open(); abandoned.text = "Replacement after \(mutation)"
    abandoned.save()
    check(abandoned.publishing && !abandoned.canDiscard, "queued publication establishes non-discardable boundary")
    abandoned.discard()
    check(abandoned.text == "Replacement after \(mutation)", "Discard cannot race active publication")
    abandonedMutation.queue.resume(); wait { !abandoned.saving }
    let afterMutation = try abandonedMutation.body()
    check(blocks(afterMutation) == 1 && !afterMutation.contains("### Screenshots"), "late \(mutation) callback cannot modify replacement draft")
}

// Persistence and a previously accepted removal can fail together. Retrying
// the image must not silently consume the removal while the file queue is busy.
let combinedFailure = try Fixture()
let combinedDraft = combinedFailure.service()
acceptImage(combinedDraft)
let firstID = combinedDraft.images[0].id
let collision = combinedDraft.images[0].file!.deletingLastPathComponent().appendingPathComponent("02.png")
try Data("unrelated collision".utf8).write(to: collision)
combinedDraft.receiveImage(picture(0.8), capturedAt: opening.addingTimeInterval(9))
wait { combinedDraft.pendingCount == 0 }
check(combinedDraft.hasFailedAttachments && combinedDraft.images.count == 2,
      "number collision produces failed persistence beside retained first image")
combinedDraft.removeImage(firstID)
wait { combinedDraft.pendingCount == 0 }
check(combinedDraft.hasFailedWork && combinedDraft.images.contains { $0.id == firstID },
      "unrelated collision also blocks accepted first-image removal")
try files.removeItem(at: collision)
combinedDraft.retryFailedWork()
wait { combinedDraft.pendingCount == 0 }
check(!combinedDraft.hasFailedWork && combinedDraft.images.count == 1 && combinedDraft.images[0].id != firstID,
      "combined retry must finish accepted removal after image persistence; retained \(combinedDraft.images.count) images")
combinedDraft.save(); wait { !combinedDraft.saving }
let combinedBody = try combinedFailure.body()
check(blocks(combinedBody) == 1 && combinedBody.contains("11:19:09+02:00") && !combinedBody.contains("02.png"),
      "combined retry publishes only the requested remaining image with original acquisition time")

print("PASS: \(checks) headless quick capture lifecycle checks")
''')
