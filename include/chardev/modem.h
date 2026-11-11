/*
 * Reset input for QEMU's Hayes-compatible serial modem substitute.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_CHARDEV_MODEM_H
#define QEMU_CHARDEV_MODEM_H

#include "chardev/char.h"

/* Physical modem reset GPIO has been asserted; BQL must be held. */
void qemu_modem_hardware_reset(Chardev *chr);

#endif
