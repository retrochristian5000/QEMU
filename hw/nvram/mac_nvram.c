/*
 * PowerMac NVRAM emulation
 *
 * Copyright (c) 2005-2007 Fabrice Bellard
 * Copyright (c) 2007 Jocelyn Mayer
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
#include "qapi/error.h"
#include "hw/nvram/chrp_nvram.h"
#include "hw/nvram/mac_nvram.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/qdev-properties-system.h"
#include "system/block-backend.h"
#include "system/blockdev.h"
#include "migration/vmstate.h"
#include "qemu/module.h"
#include "qemu/error-report.h"
#include "trace.h"

#define DEF_SYSTEM_SIZE 0xc10
#define MACOS75_NVRAM_SIGNATURE 0xa0
#define MACOS75_NVRAM_PARTITION_SIZE 0x520
#define OSXPANIC_NVRAM_SIGNATURE 0xa1
#define OSXPANIC_NVRAM_PARTITION_SIZE 0x810
#define LEGACY_OSX_NVRAM_SIGNATURE 0x5a

/* macio style NVRAM device */
static void macio_nvram_writeb(void *opaque, hwaddr addr,
                               uint64_t value, unsigned size)
{
    MacIONVRAMState *s = opaque;

    addr = (addr >> s->it_shift) & (s->size - 1);
    trace_macio_nvram_write(addr, value);
    s->data[addr] = value;
    if (s->blk) {
        if (blk_pwrite(s->blk, addr, 1, &s->data[addr], 0) < 0) {
            error_report("%s: write of NVRAM data to backing store failed",
                         blk_name(s->blk));
        }
    }
}

static uint64_t macio_nvram_readb(void *opaque, hwaddr addr,
                                  unsigned size)
{
    MacIONVRAMState *s = opaque;
    uint32_t value;

    addr = (addr >> s->it_shift) & (s->size - 1);
    value = s->data[addr];
    trace_macio_nvram_read(addr, value);

    return value;
}

static const MemoryRegionOps macio_nvram_ops = {
    .read = macio_nvram_readb,
    .write = macio_nvram_writeb,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 1,
    .impl.max_access_size = 1,
    .endianness = DEVICE_BIG_ENDIAN,
};

static const VMStateDescription vmstate_macio_nvram = {
    .name = "macio_nvram",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_VBUFFER_UINT32(data, MacIONVRAMState, 0, NULL, size),
        VMSTATE_END_OF_LIST()
    }
};

static void macio_nvram_reset(DeviceState *dev)
{
}

static void macio_nvram_realizefn(DeviceState *dev, Error **errp)
{
    SysBusDevice *d = SYS_BUS_DEVICE(dev);
    MacIONVRAMState *s = MACIO_NVRAM(dev);

    if (!s->blk) {
        DriveInfo *dinfo = drive_get(IF_MTD, 0, 0);

        if (dinfo) {
            qdev_prop_set_drive(dev, "drive", blk_by_legacy_dinfo(dinfo));
        }
    }

    s->data = g_malloc0(s->size);

    if (s->blk) {
        int64_t len = blk_getlength(s->blk);
        if (len < 0) {
            error_setg_errno(errp, -len,
                             "could not get length of nvram backing image");
            return;
        } else if (len != s->size) {
            error_setg(errp,
                       "invalid size nvram backing image: expected %u bytes, "
                       "got %" PRId64 " bytes",
                       s->size, len);
            return;
        }
        if (blk_set_perm(s->blk, BLK_PERM_CONSISTENT_READ | BLK_PERM_WRITE,
                         BLK_PERM_ALL, errp) < 0) {
            return;
        }
        if (blk_pread(s->blk, 0, s->size, s->data, 0) < 0) {
            error_setg(errp, "can't read-nvram contents");
            return;
        }
    }

    memory_region_init_io(&s->mem, OBJECT(s), &macio_nvram_ops, s,
                          "macio-nvram", s->size << s->it_shift);
    sysbus_init_mmio(d, &s->mem);
}

static void macio_nvram_unrealizefn(DeviceState *dev)
{
    MacIONVRAMState *s = MACIO_NVRAM(dev);

    g_free(s->data);
}

static const Property macio_nvram_properties[] = {
    DEFINE_PROP_UINT32("size", MacIONVRAMState, size, 0),
    DEFINE_PROP_UINT32("it_shift", MacIONVRAMState, it_shift, 0),
    DEFINE_PROP_DRIVE("drive", MacIONVRAMState, blk),
};

static void macio_nvram_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = macio_nvram_realizefn;
    dc->unrealize = macio_nvram_unrealizefn;
    device_class_set_legacy_reset(dc, macio_nvram_reset);
    dc->vmsd = &vmstate_macio_nvram;
    device_class_set_props(dc, macio_nvram_properties);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo macio_nvram_type_info = {
    .name = TYPE_MACIO_NVRAM,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(MacIONVRAMState),
    .class_init = macio_nvram_class_init,
};

static void macio_nvram_register_types(void)
{
    type_register_static(&macio_nvram_type_info);
}

static bool pmac_nvram_buffer_is_erased(const uint8_t *data, int len)
{
    bool all_zero = true;
    bool all_ones = true;
    int i;

    for (i = 0; i < len; i++) {
        all_zero &= data[i] == 0x00;
        all_ones &= data[i] == 0xff;
        if (!all_zero && !all_ones) {
            return false;
        }
    }

    return true;
}

static void pmac_nvram_set_partition_name(ChrpNvramPartHdr *header,
                                          const char *name)
{
    size_t len = MIN(strlen(name), sizeof(header->name));

    memset(header->name, 0, sizeof(header->name));
    memcpy(header->name, name, len);
}

static bool pmac_nvram_header_matches(const uint8_t *data, int len,
                                      uint8_t signature, const char *name)
{
    const ChrpNvramPartHdr *header;
    uint32_t part_len;

    if (len < sizeof(*header)) {
        return false;
    }

    header = (const ChrpNvramPartHdr *)data;
    part_len = be16_to_cpu(header->len) << 4;

    return header->signature == signature &&
           part_len >= sizeof(*header) && part_len <= len &&
           !strncmp(header->name, name, sizeof(header->name));
}

static bool pmac_nvram_has_legacy_qemu_layout(MacIONVRAMState *nvr, int len)
{
    int half = len / 2;

    return pmac_nvram_header_matches(nvr->data, half,
                                     CHRP_NVPART_SYSTEM, "system") &&
           pmac_nvram_header_matches(&nvr->data[half], half,
                                     LEGACY_OSX_NVRAM_SIGNATURE,
                                     "wwwwwwwwwww");
}

static void pmac_nvram_name_system_partition(uint8_t *data)
{
    ChrpNvramPartHdr *header = (ChrpNvramPartHdr *)data;
    uint32_t part_len = be16_to_cpu(header->len) << 4;

    pmac_nvram_set_partition_name(header, "common");
    chrp_nvram_finish_partition(header, part_len);
}

/* Set up a system Open Firmware NVRAM partition. */
static void pmac_format_nvram_partition_of(MacIONVRAMState *nvr, int off,
                                           int len)
{
    int sysp_len;

    sysp_len = chrp_nvram_create_system_partition(
        &nvr->data[off], DEF_SYSTEM_SIZE,
        len - sizeof(ChrpNvramPartHdr));
    pmac_nvram_name_system_partition(&nvr->data[off]);

    chrp_nvram_create_free_partition(&nvr->data[off + sysp_len],
                                     len - sysp_len);
}

static int pmac_format_nvram_os_partition(uint8_t *data, uint8_t signature,
                                          const char *name, int len)
{
    ChrpNvramPartHdr *header = (ChrpNvramPartHdr *)data;

    header->signature = signature;
    pmac_nvram_set_partition_name(header, name);
    chrp_nvram_finish_partition(header, len);

    return len;
}

/* Set up the XPRAM, Name Registry and panic partitions used by NewWorld Macs. */
static void pmac_format_nvram_partition_macos(MacIONVRAMState *nvr, int off,
                                              int len)
{
    int end = 0;

    assert(len >= MACOS75_NVRAM_PARTITION_SIZE +
                  OSXPANIC_NVRAM_PARTITION_SIZE +
                  sizeof(ChrpNvramPartHdr));

    memset(&nvr->data[off], 0, len);
    end += pmac_format_nvram_os_partition(
        &nvr->data[off + end], MACOS75_NVRAM_SIGNATURE,
        "APL,MacOS75", MACOS75_NVRAM_PARTITION_SIZE);
    end += pmac_format_nvram_os_partition(
        &nvr->data[off + end], OSXPANIC_NVRAM_SIGNATURE,
        "APL,OSXPanic", OSXPANIC_NVRAM_PARTITION_SIZE);

    chrp_nvram_create_free_partition(&nvr->data[off + end], len - end);
}

/* Set up NVRAM with Open Firmware and Mac OS partitions. */
void pmac_format_nvram_partition(MacIONVRAMState *nvr, int len)
{
    bool erased = pmac_nvram_buffer_is_erased(nvr->data, len);
    bool legacy = pmac_nvram_has_legacy_qemu_layout(nvr, len);
    int half = len / 2;

    /* Preserve unknown or already-populated images rather than erase them. */
    if (!erased && !legacy) {
        return;
    }

    if (erased) {
        memset(nvr->data, 0, len);
        pmac_format_nvram_partition_of(nvr, 0, half);
    } else {
        /* Upgrade the layout emitted by older QEMU builds in place. */
        pmac_nvram_name_system_partition(nvr->data);
    }

    pmac_format_nvram_partition_macos(nvr, half, len - half);

    if (nvr->blk) {
        if (blk_pwrite(nvr->blk, 0, len, nvr->data, 0) < 0 ||
            blk_flush(nvr->blk) < 0) {
            error_report("%s: initialization of NVRAM backing store failed",
                         blk_name(nvr->blk));
        }
    }
}
type_init(macio_nvram_register_types)
