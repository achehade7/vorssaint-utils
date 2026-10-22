// SPDX-License-Identifier: GPL-3.0-or-later
import AppKit
import ImageIO

/// Native screenshots join the same preview used by Vorssaint's capture tool.
/// Spotlight delivers file arrivals; no timer scans the Desktop.
final class NotchScreenshotInbox {
    static let shared = NotchScreenshotInbox()
    private var query: NSMetadataQuery?
    private var observers: [NSObjectProtocol] = []
    private var consumed = Set<String>()
    private var generation = 0
    private var captureFolder = ""
    private let imageQueue = DispatchQueue(label: "com.vorssaint.utils.native-capture-images",
                                          qos: .userInitiated)

    func start() {
        guard query == nil else { return }
        let location = UserDefaults(suiteName: "com.apple.screencapture")?.string(forKey: "location")
            ?? "~/Desktop"
        let folder = URL(fileURLWithPath: (location as NSString).expandingTildeInPath)
        let query = NSMetadataQuery()
        captureFolder = folder.standardizedFileURL.path
        // A direct Desktop scope synchronously opens the protected folder
        // before AppKit finishes launching. Search the index, then filter its
        // paths; image access (and any consent prompt) happens off the UI thread.
        query.searchScopes = [NSMetadataQueryLocalComputerScope]
        query.predicate = NSPredicate(format: "kMDItemIsScreenCapture == 1 AND kMDItemFSCreationDate >= %@", Date() as NSDate)
        query.notificationBatchingInterval = 0.25
        self.query = query
        for name in [NSNotification.Name.NSMetadataQueryDidFinishGathering, NSNotification.Name.NSMetadataQueryDidUpdate] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: query, queue: .main) {
                [weak self] _ in self?.receive()
            })
        }
        if !query.start() { stop() }
    }

    func stop() {
        generation += 1
        query?.stop(); query = nil
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
        consumed.removeAll()
    }

    private func receive() {
        guard let query else { return }
        query.disableUpdates()
        let items = query.results.compactMap { $0 as? NSMetadataItem }
        let paths = items.compactMap { $0.value(forAttribute: NSMetadataItemPathKey) as? String }
        query.enableUpdates()
        let arrivals = paths.filter {
            URL(fileURLWithPath: $0).deletingLastPathComponent().standardizedFileURL.path == captureFolder
                && consumed.insert($0).inserted
        }
        guard !arrivals.isEmpty, NotchService.shared.acceptsSystemFeedback else { return }
        let requested = generation
        let scale = NSScreen.main?.backingScaleFactor ?? 2
        let anchor = NSScreen.main?.visibleFrame ?? .zero
        imageQueue.async { [weak self] in
            let native = arrivals.filter { getxattr($0, "com.vorssaint.capture", nil, 0, 0, XATTR_NOFOLLOW) < 0 }
                .sorted { Self.modificationDate($0) < Self.modificationDate($1) }
                .suffix(ScreenshotSupport.recentCaptureLimit)
            // Keep every screenshot in a burst in the existing bounded cache;
            // serial loading preserves arrival order across metadata batches.
            for path in native {
                guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
                      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { continue }
                DispatchQueue.main.async {
                    guard let self, self.query != nil, self.generation == requested,
                          NotchSupport.routes(.capture), NotchService.shared.acceptsSystemFeedback else { return }
                    let capture = ScreenshotSelectionController.Capture(image: image,
                        scale: scale, anchorRect: anchor)
                    let historyID = RecentCaptureService.shared.recordScreenshot(capture)
                    if path == native.last {
                        ScreenshotService.shared.restorePreview(
                            capture, historyID: historyID,
                            dismissInterval: ScreenshotSupport.confirmationPreviewDismissInterval())
                    }
                }
            }
        }
    }

    private static func modificationDate(_ path: String) -> Date {
        (try? URL(fileURLWithPath: path).resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
    }
}
