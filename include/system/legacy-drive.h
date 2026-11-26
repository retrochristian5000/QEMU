/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYSTEM_LEGACY_DRIVE_H
#define SYSTEM_LEGACY_DRIVE_H

#include "system/blockdev.h"

void legacy_drive_select_controller(const char *id);
bool legacy_drive_has_controller(void);
void legacy_drive_record(QemuOpts *opts, int index, bool cdrom);
void legacy_drive_prepare(void);
void legacy_drive_record_backend(QemuOpts *opts, DriveInfo *drive);
void legacy_drive_attach(void);

#endif
