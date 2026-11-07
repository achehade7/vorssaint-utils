// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import Foundation
import CoreLocation

/// Compile the complete production service with recording location/notification
/// boundaries and a controlled clock. No location permission or network needed.
enum NotchWeatherLocationTests {
    typealias DispatchQueue = NotchScreenRefreshContract.DispatchQueue
    final class CLLocationManager {
        var delegate: AnyObject?
        var desiredAccuracy: Double = 0
        var authorizationStatus = CLAuthorizationStatus.authorizedAlways
        var lookups = 0
        func requestLocation() { lookups += 1 }
        func requestWhenInUseAuthorization() {}
        func stopUpdatingLocation() {}
    }
    final class DistributedNotificationCenter {
        static let shared = DistributedNotificationCenter()
        static func `default`() -> DistributedNotificationCenter { shared }
        var replies: [[String: Any]] = []
        func postNotificationName(_ name: Notification.Name, object: String?,
                                  userInfo: [String: Any], deliverImmediately: Bool) {
            replies.append(userInfo)
        }
    }

    static func run(_ suite: TestSuite) {
        MainActor.assumeIsolated { checks(suite) }
    }

    @MainActor private static func checks(_ suite: TestSuite) {
        func reset() {
            DispatchQueue.main = NotchScreenRefreshContract.Scheduler()
            DistributedNotificationCenter.shared.replies = []
        }
        func fail(_ service: NotchWeatherLocationService, _ code: CLError.Code) {
            service.locationManager(service.manager, didFailWithError:
                NSError(domain: kCLErrorDomain, code: code.rawValue))
        }
        reset()
        let service = NotchWeatherLocationService()
        service.request("first")
        fail(service, .locationUnknown)
        fail(service, .locationUnknown)
        suite.expect(DistributedNotificationCenter.shared.replies.isEmpty,
                     "temporary startup failure keeps the location request pending")
        DispatchQueue.main.advance(1)
        suite.expect(service.manager.lookups == 1, "retry waits instead of spinning")
        DispatchQueue.main.advance(1)
        suite.expect(service.manager.lookups == 2, "duplicate failures schedule only one retry")
        service.request("second")
        fail(service, .network)
        service.complete(CLLocation(latitude: 1, longitude: 2), city: "Fixture", zone: .gmt,
                         generation: service.generation)
        suite.expect(DistributedNotificationCenter.shared.replies.count == 2
                     && DistributedNotificationCenter.shared.replies.allSatisfy { $0["status"] as? String == "ok" },
                     "recovered lookup replies successfully to all waiting callers")
        DispatchQueue.main.advance(30)
        suite.expect(service.manager.lookups == 2 && DistributedNotificationCenter.shared.replies.count == 2,
                     "success cancels the delayed retry and deadline")

        reset()
        let timedOut = NotchWeatherLocationService()
        timedOut.request("timeout")
        for _ in 0..<9 {
            fail(timedOut, .network)
            DispatchQueue.main.advance(2)
        }
        fail(timedOut, .locationUnknown)
        DispatchQueue.main.advance(2)
        let lookups = timedOut.manager.lookups
        DispatchQueue.main.advance(30)
        suite.expect(DistributedNotificationCenter.shared.replies.count == 1
                     && DistributedNotificationCenter.shared.replies.first?["description"] as? String == "Location lookup timed out"
                     && timedOut.manager.lookups == lookups,
                     "repeated temporary failures cannot extend the original twenty-second deadline")

        reset()
        let denied = NotchWeatherLocationService()
        denied.manager.authorizationStatus = .denied
        denied.request("denied")
        suite.expect(DistributedNotificationCenter.shared.replies.first?["status"] as? String == "location_denied"
                     && denied.manager.lookups == 0 && DispatchQueue.main.pending == 0,
                     "denied permission returns immediately without retries")

        reset()
        let terminal = NotchWeatherLocationService()
        terminal.request("terminal")
        fail(terminal, .headingFailure)
        suite.expect(DistributedNotificationCenter.shared.replies.first?["status"] as? String == "unavailable"
                     && DispatchQueue.main.pending == 0,
                     "non-transient errors finish immediately")
    }
}
