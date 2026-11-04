#!/usr/bin/env python3
"""Exercise production island shortcut opening/toggling with isolated state."""
from pathlib import Path
import subprocess
import tempfile
from generate_sources import declaration

source = r'''
import Foundation
enum NotchModule: CaseIterable { case clipboard, captures, mixer, notifications }
enum NotchSupport {
    static var enabled = true
    static var available = NotchModule.allCases
    static func isEnabled() -> Bool { enabled }
    static func modules() -> [NotchModule] { available }
}
final class Service {
    var acceptsUserInteraction = true
    var expanded = false
    var selected = NotchModule.clipboard
    var showingAppPanel = false, showingSections = false, showingCommandBar = false, showingQuickCapture = false
    var captureControls: Int?, captureContent: Int?
    var opens = 0, closes = 0
    func open(_ module: NotchModule) { selected = module; expanded = true; opens += 1 }
    func collapse() { expanded = false; closes += 1 }
    METHOD
}
var checks = 0
func expect(_ condition: Bool) { checks += 1; precondition(condition) }
for module in [NotchModule.captures, .mixer, .notifications] {
    let service = Service()
    expect(service.showPageFromShortcut(module))
    expect(service.expanded && service.selected == module && service.opens == 1)
    expect(service.showPageFromShortcut(module))
    expect(!service.expanded && service.closes == 1)
    for overlay in 0..<6 {
        let s = Service(); s.expanded = true; s.selected = module
        switch overlay {
        case 0: s.showingAppPanel = true
        case 1: s.showingSections = true
        case 2: s.showingCommandBar = true
        case 3: s.showingQuickCapture = true
        case 4: s.captureControls = 1
        default: s.captureContent = 1
        }
        expect(s.showPageFromShortcut(module) && s.closes == 0 && s.opens == 1)
    }
    service.acceptsUserInteraction = false
    expect(!service.showPageFromShortcut(module))
    service.acceptsUserInteraction = true
    NotchSupport.enabled = false
    expect(!service.showPageFromShortcut(module))
    NotchSupport.enabled = true; NotchSupport.available = [.clipboard]
    expect(!service.showPageFromShortcut(module))
    NotchSupport.available = NotchModule.allCases
}
print("PASS: \(checks) island page shortcut checks")
'''
source = source.replace('METHOD', declaration('Sources/Vorssaint/Services/Notch/NotchService.swift', '    func showPageFromShortcut('))
with tempfile.TemporaryDirectory(prefix='island-page-shortcuts-') as temp:
    main = Path(temp) / 'main.swift'; main.write_text(source)
    binary = Path(temp) / 'test'
    subprocess.run(['swiftc', str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
