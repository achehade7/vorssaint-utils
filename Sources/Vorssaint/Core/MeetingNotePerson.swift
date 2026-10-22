// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct MeetingNotePerson: Equatable, Sendable {
    let name: String
    var isCurrentUser = false

    var initials: String {
        guard !name.contains("@"), !name.contains(":") else { return "" }
        return name.split(whereSeparator: { !$0.isLetter }).compactMap(\.first)
            .map { String($0).uppercased() + "." }.joined()
    }
}

