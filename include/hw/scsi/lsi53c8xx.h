/*
 * LSI/NCR 53C8xx SCSI controller family
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_SCSI_LSI53C8XX_H
#define HW_SCSI_LSI53C8XX_H

#include "hw/qdev-core.h"

/*
 * Keep the externally visible QOM names stable while the implementation is
 * shared as one 53C8xx family module.  New family members should extend the
 * common core instead of copying an existing controller implementation.
 */
#define TYPE_LSI53C810  "lsi53c810"
#define TYPE_LSI53C895A "lsi53c895a"

void lsi53c8xx_handle_legacy_cmdline(DeviceState *lsi_dev);

#endif /* HW_SCSI_LSI53C8XX_H */
