/*
 * QEMU Smram/pam logic implementation
 *
 * Copyright (c) 2006 Fabrice Bellard
 * Copyright (c) 2011 Isaku Yamahata <yamahata at valinux co jp>
 *                    VA Linux Systems Japan K.K.
 * Copyright (c) 2012 Jason Baron <jbaron@redhat.com>
 *
 * Split out from piix.c
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
#include "qemu/bswap.h"
#include "hw/pci-host/pam.h"

/*
 * Intel 82441FX datasheet 290549-001, section 3.2.18: WE=1, RE=0
 * directs writes to DRAM and reads to PCI, allowing in-place ROM shadowing.
 * Use separate address spaces to avoid reentering the system PAM mapping.
 */
static MemTxResult pam_write_only_read(void *opaque, hwaddr addr,
                                       uint64_t *data, unsigned size,
                                       MemTxAttrs attrs)
{
    PAMMemoryRegion *mem = opaque;
    uint64_t value = 0;
    MemTxResult ret;

    ret = address_space_read(mem->pci_as, mem->start + addr, attrs,
                             &value, size);
    *data = le64_to_cpu(value);
    return ret;
}

static MemTxResult pam_write_only_write(void *opaque, hwaddr addr,
                                        uint64_t data, unsigned size,
                                        MemTxAttrs attrs)
{
    PAMMemoryRegion *mem = opaque;
    uint64_t value = cpu_to_le64(data);

    return address_space_write(mem->ram_as, mem->start + addr, attrs,
                               &value, size);
}

static const MemoryRegionOps pam_write_only_ops = {
    .read_with_attrs = pam_write_only_read,
    .write_with_attrs = pam_write_only_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
    .impl = { .min_access_size = 1, .max_access_size = 8, .unaligned = true },
};

void init_pam_write_only(PAMMemoryRegion *mem, Object *owner,
                         MemoryRegion *ram_memory, MemoryRegion *system_memory,
                         MemoryRegion *pci_address_space, uint32_t start,
                         uint32_t size, AddressSpace *ram_as,
                         AddressSpace *pci_as)
{
    int i;

    /* RAM */
    memory_region_init_alias(&mem->alias[3], owner, "pam-ram", ram_memory,
                             start, size);
    /* ROM (XXX: not quite correct) */
    memory_region_init_alias(&mem->alias[1], owner, "pam-rom", ram_memory,
                             start, size);
    memory_region_set_readonly(&mem->alias[1], true);

    memory_region_init_alias(&mem->alias[0], owner, "pam-pci", pci_address_space,
                             start, size);
    if (ram_as && pci_as) {
        mem->ram_as = ram_as;
        mem->pci_as = pci_as;
        mem->start = start;
        memory_region_init_io(&mem->alias[2], owner, &pam_write_only_ops,
                              mem, "pam-write-only", size);
    } else {
        /* Preserve the legacy mapping for existing machine profiles. */
        memory_region_init_alias(&mem->alias[2], owner, "pam-pci", ram_memory,
                                 start, size);
    }

    memory_region_transaction_begin();
    for (i = 0; i < 4; ++i) {
        memory_region_set_enabled(&mem->alias[i], false);
        memory_region_add_subregion_overlap(system_memory, start,
                                            &mem->alias[i], 1);
    }
    memory_region_transaction_commit();
    /* No alias is enabled until the first register update. */
    mem->current = ARRAY_SIZE(mem->alias);
}

void init_pam(PAMMemoryRegion *mem, Object *owner, MemoryRegion *ram_memory,
              MemoryRegion *system_memory, MemoryRegion *pci_address_space,
              uint32_t start, uint32_t size)
{
    init_pam_write_only(mem, owner, ram_memory, system_memory,
                        pci_address_space, start, size, NULL, NULL);
}

void pam_update(PAMMemoryRegion *pam, int idx, uint8_t val)
{
    unsigned next;

    assert(0 <= idx && idx < PAM_REGIONS_COUNT);

    next = (val >> ((!(idx & 1)) * 4)) & PAM_ATTR_MASK;
    if (pam->current == next) {
        return;
    }

    if (pam->current < ARRAY_SIZE(pam->alias)) {
        memory_region_set_enabled(&pam->alias[pam->current], false);
    }
    pam->current = next;
    memory_region_set_enabled(&pam->alias[pam->current], true);
}
