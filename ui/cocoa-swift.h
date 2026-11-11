/*
 * QEMU Cocoa Swift bridge
 *
 * Copyright (c) 2026
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Keep this boundary plain C.  Swift owns AppKit objects internally; QEMU
 * never passes Objective-C or Swift object pointers across this interface.
 */
#ifndef QEMU_COCOA_SWIFT_H
#define QEMU_COCOA_SWIFT_H

#include <stdint.h>

#define QEMU_COCOA_SWIFT_ABI_VERSION 1

uint32_t qemu_cocoa_swift_interface_version(void);
int64_t qemu_cocoa_swift_pasteboard_change_count(void);
int32_t qemu_cocoa_swift_pasteboard_has_string(void);
double qemu_cocoa_swift_display_refresh_rate(uint32_t display_id);

#endif
