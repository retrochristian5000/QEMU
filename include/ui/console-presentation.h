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
 */
bool qemu_console_get_window_autoresize(const QemuConsole *con);
void qemu_console_set_window_autoresize(QemuConsole *con, bool enabled);

/*
 * Give a console a fixed physical-display face.  Guest raster changes are
 * resampled into this stable presentation surface, so modes with non-square
 * pixels (for example 720x400 VGA text on a 4:3 CRT) fill the same monitor
 * face without teaching individual host GUIs about historical timings.
 *
 * Width and height are presentation geometry, not guest-visible mode limits.
 * Setting a fixed face also disables guest-driven host-window autoresizing.
 */
void qemu_console_set_fixed_display_face(QemuConsole *con,
                                         int width, int height);
bool qemu_console_has_fixed_display_face(const QemuConsole *con);

/* Internal display-core helpers; frontends normally do not need these. */
DisplaySurface *qemu_console_get_display_surface(QemuConsole *con);
void qemu_console_update_display_surface(QemuConsole *con);
void qemu_console_free_display_surface(QemuConsole *con);

#endif /* UI_CONSOLE_PRESENTATION_H */
