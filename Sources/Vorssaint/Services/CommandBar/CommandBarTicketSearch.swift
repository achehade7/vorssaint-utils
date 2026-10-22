// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit

/// Extract ticket keys locally for `j clip`; use the user's saved `j` URL.
/// No clipboard content is sent anywhere until a specific row is activated.
final class CommandBarTicketSearch {
    var onResult: (() -> Void)?
    private var generation = UUID()
    private var loaded = false
    private var keys: [String] = []
    private(set) var isAwaiting = false

    func reset() {
        generation = UUID()
        loaded = false
        isAwaiting = false
        keys = []
    }

    static func ticketKeys(in text: String) -> [String] {
        let text = String(text.prefix(100_000))
        guard let regex = try? NSRegularExpression(pattern: "(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*-[1-9][0-9]*(?![A-Za-z0-9_])") else { return [] }
        var seen = Set<String>(), result: [String] = []
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let range = Range(match.range, in: text) else { continue }
            let key = String(text[range]).uppercased()
            if seen.insert(key).inserted { result.append(key) }
            if result.count == 12 { break }
        }
        return result
    }

    func rows() -> [CommandBarEntry] {
        let strings = FeatureStrings.commandBar(L10n.shared.language)
        guard let link = CommandBarLinks.decode(UserDefaults.standard.data(forKey: DefaultsKey.commandBarLinks))
            .first(where: { $0.name.lowercased() == "j" && $0.kind == .link && $0.takesQuery }) else {
            return [CommandBarEntry(id: "action.jclip.setup", title: strings.linksTitle,
                                    subtitle: "j SAP-531", icon: .symbol("link"), countsUsage: false,
                                    keepsBarOpen: true, run: { _ in })]
        }
        guard loaded else {
            if !isAwaiting {
                isAwaiting = true
                let token = generation
                GeneralPasteboardAccess.shared.async({
                    Self.ticketKeys(in: NSPasteboard.general.string(forType: .string) ?? "")
                }, then: { [weak self] keys in
                    guard let self, self.generation == token else { return }
                    self.keys = keys
                    self.loaded = true
                    self.isAwaiting = false
                    self.onResult?()
                })
            }
            return []
        }
        let entries = keys.compactMap { key -> CommandBarEntry? in
            let destination = CommandBarLinks.expand(link.destination, kind: .link, query: key)
            guard let url = URL(string: destination), ["https", "http"].contains(url.scheme?.lowercased() ?? ""),
                  url.host != nil, url.user == nil, url.password == nil else { return nil }
            return CommandBarEntry(id: "action.jclip." + key, title: key,
                                    subtitle: strings.openInBrowser + " · " + (url.host ?? ""),
                                    icon: .symbol("link"), countsUsage: false,
                                    run: { _ in NSWorkspace.shared.open(url) })
        }
        guard entries.isEmpty else { return entries }
        return [CommandBarEntry(id: "action.jclip.empty", title: strings.noResultsTitle,
                                subtitle: strings.sourceClipboard + " · SAP-531", icon: .symbol("doc.on.clipboard"),
                                countsUsage: false, keepsBarOpen: true, run: { _ in })]
    }
}
