/*
 * QEMU ATA legacy task-file register interface
 *
 * Copyright (c) 2003 Fabrice Bellard
 * Copyright (c) 2006 Openedhand Ltd.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "hw/core/irq.h"
#include "ide-internal.h"
#include "trace.h"

/*
 * Legacy task-file register access for PATA and SATA controllers with
 * a compatible register interface (for example, SiI3112).
 * AHCI receives FIS packets instead of these port accesses.
 * Command execution, transfer completion and reset remain in core.c.
 */

const MemoryRegionPortio ide_portio_list[] = {
    { 0, 8, 1, .read = ide_ioport_read, .write = ide_ioport_write },
    { 0, 1, 2, .read = ide_data_readw, .write = ide_data_writew },
    { 0, 1, 4, .read = ide_data_readl, .write = ide_data_writel },
    PORTIO_END_OF_LIST(),
};

const MemoryRegionPortio ide_portio2_list[] = {
    { 0, 1, 1, .read = ide_status_read, .write = ide_ctrl_write },
    PORTIO_END_OF_LIST(),
};

static void ide_clear_hob(IDEBus *bus)
{
    /* any write clears HOB high bit of device control register */
    bus->cmd &= ~(IDE_CTRL_HOB);
}

/* IOport [W]rite [R]egisters */
enum ATA_IOPORT_WR {
    ATA_IOPORT_WR_DATA = 0,
    ATA_IOPORT_WR_FEATURES = 1,
    ATA_IOPORT_WR_SECTOR_COUNT = 2,
    ATA_IOPORT_WR_SECTOR_NUMBER = 3,
    ATA_IOPORT_WR_CYLINDER_LOW = 4,
    ATA_IOPORT_WR_CYLINDER_HIGH = 5,
    ATA_IOPORT_WR_DEVICE_HEAD = 6,
    ATA_IOPORT_WR_COMMAND = 7,
    ATA_IOPORT_WR_NUM_REGISTERS,
};

const char *ATA_IOPORT_WR_lookup[ATA_IOPORT_WR_NUM_REGISTERS] = {
    [ATA_IOPORT_WR_DATA] = "Data",
    [ATA_IOPORT_WR_FEATURES] = "Features",
    [ATA_IOPORT_WR_SECTOR_COUNT] = "Sector Count",
    [ATA_IOPORT_WR_SECTOR_NUMBER] = "Sector Number",
    [ATA_IOPORT_WR_CYLINDER_LOW] = "Cylinder Low",
    [ATA_IOPORT_WR_CYLINDER_HIGH] = "Cylinder High",
    [ATA_IOPORT_WR_DEVICE_HEAD] = "Device/Head",
    [ATA_IOPORT_WR_COMMAND] = "Command"
};

void ide_ioport_write(void *opaque, uint32_t addr, uint32_t val)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    int reg_num = addr & 7;

    trace_ide_ioport_write(addr, ATA_IOPORT_WR_lookup[reg_num], val, bus, s);

    /* ignore writes to command block while busy with previous command */
    if (reg_num != 7 && (s->status & (BUSY_STAT|DRQ_STAT))) {
        return;
    }

    /* NOTE: Device0 and Device1 both receive incoming register writes.
     * (They're on the same bus! They have to!) */

    switch (reg_num) {
    case 0:
        break;
    case ATA_IOPORT_WR_FEATURES:
        ide_clear_hob(bus);
        bus->ifs[0].hob_feature = bus->ifs[0].feature;
        bus->ifs[1].hob_feature = bus->ifs[1].feature;
        bus->ifs[0].feature = val;
        bus->ifs[1].feature = val;
        break;
    case ATA_IOPORT_WR_SECTOR_COUNT:
        ide_clear_hob(bus);
        bus->ifs[0].hob_nsector = bus->ifs[0].nsector;
        bus->ifs[1].hob_nsector = bus->ifs[1].nsector;
        bus->ifs[0].nsector = val;
        bus->ifs[1].nsector = val;
        break;
    case ATA_IOPORT_WR_SECTOR_NUMBER:
        ide_clear_hob(bus);
        bus->ifs[0].hob_sector = bus->ifs[0].sector;
        bus->ifs[1].hob_sector = bus->ifs[1].sector;
        bus->ifs[0].sector = val;
        bus->ifs[1].sector = val;
        break;
    case ATA_IOPORT_WR_CYLINDER_LOW:
        ide_clear_hob(bus);
        bus->ifs[0].hob_lcyl = bus->ifs[0].lcyl;
        bus->ifs[1].hob_lcyl = bus->ifs[1].lcyl;
        bus->ifs[0].lcyl = val;
        bus->ifs[1].lcyl = val;
        break;
    case ATA_IOPORT_WR_CYLINDER_HIGH:
        ide_clear_hob(bus);
        bus->ifs[0].hob_hcyl = bus->ifs[0].hcyl;
        bus->ifs[1].hob_hcyl = bus->ifs[1].hcyl;
        bus->ifs[0].hcyl = val;
        bus->ifs[1].hcyl = val;
        break;
    case ATA_IOPORT_WR_DEVICE_HEAD:
        ide_clear_hob(bus);
        bus->ifs[0].select = val | (ATA_DEV_ALWAYS_ON);
        bus->ifs[1].select = val | (ATA_DEV_ALWAYS_ON);
        /* select drive */
        bus->unit = (val & (ATA_DEV_SELECT)) ? 1 : 0;
        break;
    default:
    case ATA_IOPORT_WR_COMMAND:
        ide_clear_hob(bus);
        qemu_irq_lower(bus->irq);
        ide_bus_exec_cmd(bus, val);
        break;
    }
}

/* IOport [R]ead [R]egisters */
enum ATA_IOPORT_RR {
    ATA_IOPORT_RR_DATA = 0,
    ATA_IOPORT_RR_ERROR = 1,
    ATA_IOPORT_RR_SECTOR_COUNT = 2,
    ATA_IOPORT_RR_SECTOR_NUMBER = 3,
    ATA_IOPORT_RR_CYLINDER_LOW = 4,
    ATA_IOPORT_RR_CYLINDER_HIGH = 5,
    ATA_IOPORT_RR_DEVICE_HEAD = 6,
    ATA_IOPORT_RR_STATUS = 7,
    ATA_IOPORT_RR_NUM_REGISTERS,
};

const char *ATA_IOPORT_RR_lookup[ATA_IOPORT_RR_NUM_REGISTERS] = {
    [ATA_IOPORT_RR_DATA] = "Data",
    [ATA_IOPORT_RR_ERROR] = "Error",
    [ATA_IOPORT_RR_SECTOR_COUNT] = "Sector Count",
    [ATA_IOPORT_RR_SECTOR_NUMBER] = "Sector Number",
    [ATA_IOPORT_RR_CYLINDER_LOW] = "Cylinder Low",
    [ATA_IOPORT_RR_CYLINDER_HIGH] = "Cylinder High",
    [ATA_IOPORT_RR_DEVICE_HEAD] = "Device/Head",
    [ATA_IOPORT_RR_STATUS] = "Status"
};

uint32_t ide_ioport_read(void *opaque, uint32_t addr)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    uint32_t reg_num;
    int ret, hob;

    reg_num = addr & 7;
    hob = bus->cmd & (IDE_CTRL_HOB);
    switch (reg_num) {
    case ATA_IOPORT_RR_DATA:
        /*
         * The pre-GRUB Solaris x86 bootloader relies upon inb
         * consuming a word from the drive's sector buffer.
         */
        ret = ide_data_readw(bus, addr) & 0xff;
        break;
    case ATA_IOPORT_RR_ERROR:
        if ((!bus->ifs[0].blk && !bus->ifs[1].blk) ||
            (s != bus->ifs && !s->blk)) {
            ret = 0;
        } else if (!hob) {
            ret = s->error;
        } else {
            ret = s->hob_feature;
        }
        break;
    case ATA_IOPORT_RR_SECTOR_COUNT:
        if (!bus->ifs[0].blk && !bus->ifs[1].blk) {
            ret = 0;
        } else if (!hob) {
            ret = s->nsector & 0xff;
        } else {
            ret = s->hob_nsector;
        }
        break;
    case ATA_IOPORT_RR_SECTOR_NUMBER:
        if (!bus->ifs[0].blk && !bus->ifs[1].blk) {
            ret = 0;
        } else if (!hob) {
            ret = s->sector;
        } else {
            ret = s->hob_sector;
        }
        break;
    case ATA_IOPORT_RR_CYLINDER_LOW:
        if (!bus->ifs[0].blk && !bus->ifs[1].blk) {
            ret = 0;
        } else if (!hob) {
            ret = s->lcyl;
        } else {
            ret = s->hob_lcyl;
        }
        break;
    case ATA_IOPORT_RR_CYLINDER_HIGH:
        if (!bus->ifs[0].blk && !bus->ifs[1].blk) {
            ret = 0;
        } else if (!hob) {
            ret = s->hcyl;
        } else {
            ret = s->hob_hcyl;
        }
        break;
    case ATA_IOPORT_RR_DEVICE_HEAD:
        if (!bus->ifs[0].blk && !bus->ifs[1].blk) {
            ret = 0;
        } else {
            ret = s->select;
        }
        break;
    default:
    case ATA_IOPORT_RR_STATUS:
        if ((!bus->ifs[0].blk && !bus->ifs[1].blk) ||
            (s != bus->ifs && !s->blk)) {
            ret = 0;
        } else {
            ret = s->status;
        }
        qemu_irq_lower(bus->irq);
        break;
    }

    trace_ide_ioport_read(addr, ATA_IOPORT_RR_lookup[reg_num], ret, bus, s);
    return ret;
}

uint32_t ide_status_read(void *opaque, uint32_t addr)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    int ret;

    if ((!bus->ifs[0].blk && !bus->ifs[1].blk) ||
        (s != bus->ifs && !s->blk)) {
        ret = 0;
    } else {
        ret = s->status;
    }

    trace_ide_status_read(addr, ret, bus, s);
    return ret;
}

/*
 * Returns true if the running PIO transfer is a PIO out (i.e. data is
 * transferred from the device to the guest), false if it's a PIO in
 */
static bool ide_is_pio_out(IDEState *s)
{
    switch (s->end_transfer_fn_idx) {
    case IDE_TRANSFER_END_SECTOR_WRITE:
    case IDE_TRANSFER_END_ATAPI_CMD:
        return false;
    case IDE_TRANSFER_END_SECTOR_READ:
    case IDE_TRANSFER_END_STOP:
    case IDE_TRANSFER_END_ATAPI_REPLY:
    case IDE_TRANSFER_END_DUMMY_STOP:
        return true;
    default:
        abort();
    }
}

void ide_data_writew(void *opaque, uint32_t addr, uint32_t val)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    uint8_t *p;

    trace_ide_data_writew(addr, val, bus, s);

    /* PIO data access allowed only when DRQ bit is set. The result of a write
     * during PIO out is indeterminate, just ignore it. */
    if (!(s->status & DRQ_STAT) || ide_is_pio_out(s)) {
        return;
    }

    p = s->data_ptr;
    if (s->io8) {
        if (p + 1 > s->data_end) {
            return;
        }

        *p++ = val;
    } else {
        if (p + 2 > s->data_end) {
            return;
        }

        *(uint16_t *)p = le16_to_cpu(val);
        p += 2;
    }
    s->data_ptr = p;
    if (p >= s->data_end) {
        s->status &= ~DRQ_STAT;
        s->end_transfer_func(s);
    }
}

uint32_t ide_data_readw(void *opaque, uint32_t addr)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    uint8_t *p;
    int ret;

    /* PIO data access allowed only when DRQ bit is set. The result of a read
     * during PIO in is indeterminate, return 0 and don't move forward. */
    if (!(s->status & DRQ_STAT) || !ide_is_pio_out(s)) {
        return 0;
    }

    p = s->data_ptr;
    if (s->io8) {
        if (p + 1 > s->data_end) {
            return 0;
        }

        ret = *p++;
    } else {
        if (p + 2 > s->data_end) {
            return 0;
        }

        ret = cpu_to_le16(*(uint16_t *)p);
        p += 2;
    }
    s->data_ptr = p;
    if (p >= s->data_end) {
        s->status &= ~DRQ_STAT;
        s->end_transfer_func(s);
    }

    trace_ide_data_readw(addr, ret, bus, s);
    return ret;
}

void ide_data_writel(void *opaque, uint32_t addr, uint32_t val)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    uint8_t *p;

    trace_ide_data_writel(addr, val, bus, s);

    /* PIO data access allowed only when DRQ bit is set. The result of a write
     * during PIO out is indeterminate, just ignore it. */
    if (!(s->status & DRQ_STAT) || ide_is_pio_out(s)) {
        return;
    }

    p = s->data_ptr;
    if (p + 4 > s->data_end) {
        return;
    }

    *(uint32_t *)p = le32_to_cpu(val);
    p += 4;
    s->data_ptr = p;
    if (p >= s->data_end) {
        s->status &= ~DRQ_STAT;
        s->end_transfer_func(s);
    }
}

uint32_t ide_data_readl(void *opaque, uint32_t addr)
{
    IDEBus *bus = opaque;
    IDEState *s = ide_bus_active_if(bus);
    uint8_t *p;
    int ret;

    /* PIO data access allowed only when DRQ bit is set. The result of a read
     * during PIO in is indeterminate, return 0 and don't move forward. */
    if (!(s->status & DRQ_STAT) || !ide_is_pio_out(s)) {
        ret = 0;
        goto out;
    }

    p = s->data_ptr;
    if (p + 4 > s->data_end) {
        return 0;
    }

    ret = cpu_to_le32(*(uint32_t *)p);
    p += 4;
    s->data_ptr = p;
    if (p >= s->data_end) {
        s->status &= ~DRQ_STAT;
        s->end_transfer_func(s);
    }

out:
    trace_ide_data_readl(addr, ret, bus, s);
    return ret;
}
