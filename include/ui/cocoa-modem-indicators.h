/*
 * External modem indicator inspector for Cocoa.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef UI_COCOA_MODEM_INDICATORS_H
#define UI_COCOA_MODEM_INDICATORS_H

/* Lifecycle gate may be changed by the QEMU thread. */
void cocoa_modem_indicators_set_enabled(bool enabled);
/* Main AppKit thread only. */
void cocoa_modem_indicators_show(void);

#endif
