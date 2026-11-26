/*
 * Explicit routing of legacy disk command-line shortcuts.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/option.h"
#include "hw/core/qdev-properties.h"
#include "hw/ide/ide-bus.h"
#include "system/legacy-drive.h"

typedef struct LegacyDrive {
    QemuOpts *opts;
    DriveInfo *drive;
    int index;
    bool cdrom;
} LegacyDrive;

static GArray *legacy_drives;
static const char *controller_id;

void legacy_drive_select_controller(const char *id)
{
    if (!*id || controller_id) {
        error_report("-legacy-drive-controller requires one nonempty device ID");
        exit(1);
    }
    controller_id = id;
}

bool legacy_drive_has_controller(void)
{
    return controller_id != NULL;
}

void legacy_drive_record(QemuOpts *opts, int index, bool cdrom)
{
    LegacyDrive entry = {
        .opts = opts,
        .index = index,
        .cdrom = cdrom,
    };

    if (!opts) {
        exit(1);
    }
    if (!legacy_drives) {
        legacy_drives = g_array_new(false, false, sizeof(entry));
    }
    g_array_append_val(legacy_drives, entry);
}

void legacy_drive_prepare(void)
{
    if (!controller_id || !legacy_drives) {
        return;
    }

    /*
     * The machine's built-in storage controller must not claim these drives.
     * Keep the shortcut's slot separately from the block backend index.
     */
    for (guint i = 0; i < legacy_drives->len; i++) {
        LegacyDrive *entry = &g_array_index(legacy_drives, LegacyDrive, i);

        qemu_opt_set(entry->opts, "if", "none", &error_abort);
        qemu_opt_unset(entry->opts, "index");
    }
}

void legacy_drive_record_backend(QemuOpts *opts, DriveInfo *drive)
{
    if (!controller_id || !legacy_drives) {
        return;
    }

    for (guint i = 0; i < legacy_drives->len; i++) {
        LegacyDrive *entry = &g_array_index(legacy_drives, LegacyDrive, i);

        if (entry->opts == opts) {
            entry->drive = drive;
            return;
        }
    }
}

static IDEBus *controller_bus(DeviceState *controller, int index)
{
    BusState *child;

    QLIST_FOREACH(child, &controller->child_bus, sibling) {
        if (object_dynamic_cast(OBJECT(child), TYPE_IDE_BUS) &&
            IDE_BUS(child)->bus_id == index) {
            return IDE_BUS(child);
        }
    }
    return NULL;
}

static bool attach_slot(DeviceState *controller, LegacyDrive *entry,
                        int units, int slot, bool optional)
{
    IDEBus *bus = controller_bus(controller, slot / units);
    int unit = slot % units;
    DeviceState *dev;

    if (!bus || bus->max_units != units ||
        (unit == 0 ? bus->master != NULL : bus->slave != NULL)) {
        if (optional) {
            return false;
        }
        error_report("legacy disk slot %d is unavailable on controller '%s'",
                     slot, controller_id);
        exit(1);
    }

    dev = qdev_new(entry->cdrom ? "ide-cd" : "ide-hd");
    qdev_prop_set_uint32(dev, "unit", unit);
    qdev_prop_set_drive_err(dev, "drive", blk_by_legacy_dinfo(entry->drive),
                            &error_fatal);
    qdev_realize_and_unref(dev, &bus->qbus, &error_fatal);
    return true;
}

void legacy_drive_attach(void)
{
    DeviceState *controller;
    IDEBus *first;
    int units;
    static const int cd_slots[] = { 2, 3, 0, 1, 4, 5 };

    if (!controller_id) {
        g_clear_pointer(&legacy_drives, g_array_unref);
        return;
    }

    controller = qdev_find_recursive(sysbus_get_default(), controller_id);
    first = controller ? controller_bus(controller, 0) : NULL;
    if (!first || (first->max_units != 1 && first->max_units != 2)) {
        error_report("legacy drive controller '%s' must identify a realized "
                     "IDE or SATA controller with an IDE bus", controller_id);
        exit(1);
    }
    units = first->max_units;
    if (!legacy_drives) {
        return;
    }

    /* Hard disk slots are fixed, irrespective of command-line order. */
    for (guint i = 0; i < legacy_drives->len; i++) {
        LegacyDrive *entry = &g_array_index(legacy_drives, LegacyDrive, i);

        if (!entry->drive) {
            error_report("legacy drive backend was not initialized");
            exit(1);
        }
        if (!entry->cdrom) {
            attach_slot(controller, entry, units, entry->index, false);
        }
    }

    /* Prefer the historical CD-ROM slot, then use an available slot. */
    for (guint i = 0; i < legacy_drives->len; i++) {
        LegacyDrive *entry = &g_array_index(legacy_drives, LegacyDrive, i);
        bool attached = false;

        if (!entry->cdrom) {
            continue;
        }
        for (size_t j = 0; j < ARRAY_SIZE(cd_slots); j++) {
            if (attach_slot(controller, entry, units, cd_slots[j], true)) {
                attached = true;
                break;
            }
        }
        if (!attached) {
            error_report("no free CD-ROM slot on legacy drive controller '%s'",
                         controller_id);
            exit(1);
        }
    }
    g_clear_pointer(&legacy_drives, g_array_unref);
}
