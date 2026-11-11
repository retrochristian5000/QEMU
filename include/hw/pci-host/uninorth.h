/*
 * QEMU Uninorth PCI host (for all Mac99 and newer machines)
 *
 * Copyright (c) 2006 Fabrice Bellard
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

#ifndef UNINORTH_H
#define UNINORTH_H

#include "hw/pci/pci_host.h"
#include "qom/object.h"

/* UniNorth version */
#define UNINORTH_VERSION_10A    0x7

/* UniNorth memory-mapped registers (big-endian). */
#define UNINORTH_REG_VERSION        0x0000
#define UNINORTH_REG_CLOCK_CNTL     0x0020
#define UNINORTH_REG_POWER_MGMT     0x0030
#define UNINORTH_REG_ARB_CTRL       0x0040
#define UNINORTH_REG_CPU_NUMBER     0x0050
/*
 * Mac99/Core99 currently exposes only the bootstrap processor.  UniNorth
 * CPU_NUMBER is not the same contract as QEMU's internal CPUState.cpu_index.
 */
#define UNINORTH_CPU_NUMBER_BOOT     0x00000000U
#define UNINORTH_REG_HW_INIT_STATE  0x0070

#define UNINORTH_CLOCK_CNTL_PCI     0x00000001
#define UNINORTH_CLOCK_CNTL_GMAC    0x00000002
#define UNINORTH_CLOCK_CNTL_FW      0x00000004

/* UniNorth AGP PCI configuration registers (little-endian). */
#define UNINORTH_CFG_GART_BASE       0x8c
#define UNINORTH_CFG_AGP_BASE        0x90
#define UNINORTH_CFG_GART_CTRL       0x94
#define UNINORTH_CFG_INTERNAL_STATUS 0x98

#define UNINORTH_GART_CTRL_INVAL     0x00000001
#define UNINORTH_GART_CTRL_ENABLE    0x00000100
#define UNINORTH_GART_CTRL_2XRESET   0x00010000
#define UNINORTH_GART_CTRL_DISSBADET 0x00020000
#define UNINORTH_GART_CTRL_WRITABLE_MASK \
    (UNINORTH_GART_CTRL_INVAL | UNINORTH_GART_CTRL_ENABLE | \
     UNINORTH_GART_CTRL_2XRESET | UNINORTH_GART_CTRL_DISSBADET)

/* PowerMac3,1 UniNorth AGP PCI I/O range. */
#define UNINORTH_AGP_IO_BASE    0xf0000000ULL
#define UNINORTH_AGP_IO_SIZE    0x00800000ULL

#define TYPE_UNI_NORTH_PCI_HOST_BRIDGE "uni-north-pci-pcihost"
#define TYPE_UNI_NORTH_AGP_HOST_BRIDGE "uni-north-agp-pcihost"
#define TYPE_UNI_NORTH_INTERNAL_PCI_HOST_BRIDGE "uni-north-internal-pci-pcihost"
#define TYPE_U3_AGP_HOST_BRIDGE "u3-agp-pcihost"

typedef struct UNINHostState UNINHostState;
DECLARE_INSTANCE_CHECKER(UNINHostState, UNI_NORTH_PCI_HOST_BRIDGE,
                         TYPE_UNI_NORTH_PCI_HOST_BRIDGE)
DECLARE_INSTANCE_CHECKER(UNINHostState, UNI_NORTH_AGP_HOST_BRIDGE,
                         TYPE_UNI_NORTH_AGP_HOST_BRIDGE)
DECLARE_INSTANCE_CHECKER(UNINHostState, UNI_NORTH_INTERNAL_PCI_HOST_BRIDGE,
                         TYPE_UNI_NORTH_INTERNAL_PCI_HOST_BRIDGE)
DECLARE_INSTANCE_CHECKER(UNINHostState, U3_AGP_HOST_BRIDGE,
                         TYPE_U3_AGP_HOST_BRIDGE)

struct UNINHostState {
    PCIHostState parent_obj;

    uint32_t ofw_addr;
    qemu_irq irqs[4];
    MemoryRegion pci_mmio;
    MemoryRegion pci_hole;
    MemoryRegion pci_hole_high;
    MemoryRegion pci_io;
};

struct UNINState {
    SysBusDevice parent_obj;

    MemoryRegion mem;
    uint32_t clock_cntl;
    uint32_t power_mgmt;
    uint32_t arb_ctrl;
    uint32_t hw_init_state;
};

#define TYPE_UNI_NORTH "uni-north"
OBJECT_DECLARE_SIMPLE_TYPE(UNINState, UNI_NORTH)

#endif /* UNINORTH_H */
