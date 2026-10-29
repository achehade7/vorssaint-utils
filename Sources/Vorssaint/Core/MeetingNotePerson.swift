// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation

struct MeetingNotePerson: Equatable, Sendable {
    let name: String
    var isCurrentUser = false

    /// Calendar providers sometimes supply only a mailto address. Keep only
    /// name-like local-part components; never retain the domain or plus tag.
    static func attendee(name: String?, url: URL?, isCurrentUser: Bool) -> Self? {
        if let name = name?.trimmingCharacters(in: .whitespacesAndNewlines),
           !name.isEmpty, !name.contains("@"), !name.contains(":"),
           name.contains(where: \.isLetter) {
            return Self(name: name, isCurrentUser: isCurrentUser)
        }
        guard let url, url.scheme?.lowercased() == "mailto",
              let address = URLComponents(url: url, resolvingAgainstBaseURL: false)?.path else { return nil }
        let parts = address.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[1].isEmpty else { return nil }
        let local = parts[0].split(separator: "+", maxSplits: 1, omittingEmptySubsequences: false)[0]
        let words = local.split(whereSeparator: { ".-_".contains($0) })
        guard !words.isEmpty, words.allSatisfy({ $0.allSatisfy(\.isLetter) }) else { return nil }
        return Self(name: words.joined(separator: " "), isCurrentUser: isCurrentUser)
    }

    var initials: String {
        guard !name.contains("@"), !name.contains(":") else { return "" }
        return name.split(whereSeparator: { !$0.isLetter }).compactMap(\.first)
            .map { String($0).uppercased() + "." }.joined()
    }
}

