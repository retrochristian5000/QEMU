/*
 * QEMU graphical console presentation policy
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "ui/console-presentation.h"
#include "console-priv.h"

bool qemu_console_get_window_autoresize(const QemuConsole *con)
{
    return !con || !con->window_autoresize_disabled;
}

void qemu_console_set_window_autoresize(QemuConsole *con, bool enabled)
{
    if (!con) {
        return;
    }

    con->window_autoresize_disabled = !enabled;
}
