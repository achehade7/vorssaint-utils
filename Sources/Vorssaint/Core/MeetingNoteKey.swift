// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

enum MeetingNoteKey {
    /// EventKit's external iCal UID is shared by every occurrence of a series.
    /// Google sessions use recurringEventId (or id for a single event) plus the
    /// occurrence's actual start formatted in the same local time zone.
    static func google(externalIdentifier: String?, start: Date, timeZone: TimeZone = .current) -> String? {
        guard let externalIdentifier, externalIdentifier.hasSuffix("@google.com") else { return nil }
        let id = String(externalIdentifier.dropLast("@google.com".count))
        // Imported iCal UIDs need not be Google IDs. Do not substitute an
        // EventKit-local UUID or write an email address into calendar_event.
        guard (5...1024).contains(id.count),
              id.unicodeScalars.allSatisfy({ (48...57).contains($0.value) || (97...118).contains($0.value) }) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return id + " " + formatter.string(from: start)
    }
}
