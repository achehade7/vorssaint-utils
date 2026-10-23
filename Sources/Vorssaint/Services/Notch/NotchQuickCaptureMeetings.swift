// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

/// Capture context is evaluated at opening time, not the later lookup result.
/// This reader never creates a meeting note or asks for Calendar permission.
enum NotchQuickCaptureMeetings {
    static func choices(_ events: [NotchCalendarEvent], at openedAt: Date) -> [NotchQuickCaptureService.MeetingChoice] {
        events.filter { !$0.allDay && $0.start <= openedAt && $0.end > openedAt }
            .sorted { $0.start == $1.start ? $0.id < $1.id : $0.start < $1.start }
            .map { event in
                .init(id: event.id, title: event.title, input: MeetingNoteInput(
                    identity: event.noteEventKey, title: event.title, start: event.start,
                    end: event.end, people: event.notePeople))
            }
    }

    static func load(at openedAt: Date, completion: @escaping (Result<[NotchQuickCaptureService.MeetingChoice], Error>) -> Void) {
        Task { @MainActor in
            let events = await NotchCalendarService.shared.meetingEvents(now: openedAt)
            completion(.success(choices(events, at: openedAt)))
        }
    }

    static func existingNote(for choice: NotchQuickCaptureService.MeetingChoice, vault: URL) throws -> URL? {
        let folder = vault.appendingPathComponent("meetings", isDirectory: true)
        do { _ = try folder.resourceValues(forKeys: [.isDirectoryKey]) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return nil }
        return try MeetingNoteStore(vault: vault).existing(choice.input, topic: choice.title)
    }
}
