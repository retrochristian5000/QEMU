/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef UI_COCOA_DEVICE_HELP_H
#define UI_COCOA_DEVICE_HELP_H

/* Called on the main thread before guest initialization.
 * Returns false if the window cannot be displayed. */
bool cocoa_device_help_show(const char *catalog);

#endif
