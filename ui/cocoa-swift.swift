/*
 * Swift implementation helpers for the macOS Cocoa display backend.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The exported surface intentionally uses only fixed-width C-compatible
 * scalars.  AppKit/CoreGraphics ownership remains entirely inside Swift.
 */

import AppKit
import CoreGraphics

private let qemuCocoaSwiftABIVersion: UInt32 = 1

@c(qemu_cocoa_swift_interface_version)
public func qemuCocoaSwiftInterfaceVersion() -> UInt32 {
    qemuCocoaSwiftABIVersion
}

@MainActor
@c(qemu_cocoa_swift_pasteboard_change_count)
public func qemuCocoaSwiftPasteboardChangeCount() -> Int64 {
    Int64(NSPasteboard.general.changeCount)
}

@MainActor
@c(qemu_cocoa_swift_pasteboard_has_string)
public func qemuCocoaSwiftPasteboardHasString() -> Int32 {
    NSPasteboard.general.availableType(from: [.string]) == nil ? 0 : 1
}

@c(qemu_cocoa_swift_display_refresh_rate)
public func qemuCocoaSwiftDisplayRefreshRate(_ displayID: UInt32) -> Double {
    guard let mode = CGDisplayCopyDisplayMode(CGDirectDisplayID(displayID)) else {
        return 0
    }

    let rate = mode.refreshRate
    return rate.isFinite && rate > 0 ? rate : 0
}
