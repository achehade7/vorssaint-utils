// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint
import SwiftUI

/// A completed download is the file itself, so the landing notice can be dragged.
struct NotchDownloadDrag: ViewModifier {
    let url: URL?
    @ViewBuilder func body(content: Content) -> some View {
        if let url {
            content.onDrag { NSItemProvider(contentsOf: url) ?? NSItemProvider() }
                .help("Open file · drag to move or share")
        } else { content }
    }
}
