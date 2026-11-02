// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Vorssaint

import AppKit
import CoreLocation
import MapKit

/// A bounded, city-level lookup for the local SketchyBar weather helper.
/// Coordinates remain in memory here; only a requested reply is published.
/// Core Location calls this delegate on the main run loop where it was created.
@MainActor
final class NotchWeatherLocationService: NSObject, @preconcurrency CLLocationManagerDelegate {
    static let shared = NotchWeatherLocationService()
    private let manager = CLLocationManager()
    private var requests: [String] = []
    private var timeout: DispatchWorkItem?
    private var generation = 0
    private var cached: (at: Date, values: [String: Any])?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    func request(_ id: String) {
        if let cached, Date().timeIntervalSince(cached.at) < 300 {
            reply(id, cached.values)
            return
        }
        requests.append(id)
        guard requests.count == 1 else { return }
        generation += 1
        let current = generation
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.generation == current else { return }
            self.finish(["status": "unavailable", "description": "Location lookup timed out"])
        }
        timeout = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 20, execute: work)
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() }
        else { updateAuthorization() }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard !requests.isEmpty else { return }
        updateAuthorization()
    }

    private func updateAuthorization() {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse: manager.requestLocation()
        case .denied, .restricted:
            finish(["status": "location_denied", "description": "Allow Vorssaint location access in System Settings"])
        case .notDetermined: break
        @unknown default: finish(["status": "unavailable", "description": "Location unavailable"])
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        guard !requests.isEmpty else { return }
        finish(["status": "unavailable", "description": "Could not determine current location"])
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard !requests.isEmpty, let location = locations.last,
              location.horizontalAccuracy >= 0,
              abs(location.timestamp.timeIntervalSinceNow) < 300,
              CLLocationCoordinate2DIsValid(location.coordinate) else { return }
        let current = generation
        if #available(macOS 26, *) {
            guard let lookup = MKReverseGeocodingRequest(location: location) else {
                complete(location, city: nil, zone: nil, generation: current); return
            }
            Task { [weak self] in
                let item = try? await lookup.mapItems.first
                self?.complete(location, city: item?.addressRepresentations?.cityName,
                               zone: item?.timeZone, generation: current)
            }
        } else {
            CLGeocoder().reverseGeocodeLocation(location) { [weak self] places, _ in
                DispatchQueue.main.async {
                    self?.complete(location, city: places?.first?.locality,
                                   zone: places?.first?.timeZone, generation: current)
                }
            }
        }
    }

    private func complete(_ location: CLLocation, city: String?, zone: TimeZone?, generation current: Int) {
        guard !requests.isEmpty, generation == current else { return }
        let values: [String: Any] = ["status": "ok", "city": city ?? "Current location",
            "latitude": (location.coordinate.latitude * 100).rounded() / 100,
            "longitude": (location.coordinate.longitude * 100).rounded() / 100,
            "timezone": (zone ?? .autoupdatingCurrent).identifier]
        cached = (Date(), values)
        finish(values)
    }

    private func finish(_ values: [String: Any]) {
        timeout?.cancel(); timeout = nil
        manager.stopUpdatingLocation()
        generation += 1
        let pending = requests
        requests.removeAll()
        pending.forEach { reply($0, values) }
    }

    private func reply(_ id: String, _ values: [String: Any]) {
        var payload = values
        payload["request"] = id
        DistributedNotificationCenter.default().postNotificationName(
            Notification.Name("com.vorssaint.island.weatherLocation"), object: nil,
            userInfo: payload, deliverImmediately: true)
    }
}
