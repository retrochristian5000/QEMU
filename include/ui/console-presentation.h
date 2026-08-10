/*
 * QEMU graphical console presentation policy
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef UI_CONSOLE_PRESENTATION_H
#define UI_CONSOLE_PRESENTATION_H

#include "ui/console.h"

/*
 * Generic QEMU consoles automatically track guest surface size in host GUI
 * windows.  Physical display models can disable that policy: a real monitor's
 * glass does not change size when the input raster changes.
 *
 * When automatic resizing is disabled, display frontends should keep their
 * current host viewport and stretch the guest raster to fill it.  This is
 * intentionally allowed to produce non-square pixels; historical modes such
 * as 720x400 VGA text were displayed across a 4:3 CRT face.
 */
bool qemu_console_get_window_autoresize(const QemuConsole *con);
void qemu_console_set_window_autoresize(QemuConsole *con, bool enabled);

#ifdef CONFIG_OPENGL
/* Fill the complete host viewport without preserving source pixel aspect. */
void surface_gl_setup_viewport_stretch(int ww, int wh);
#endif

#endif /* UI_CONSOLE_PRESENTATION_H */
