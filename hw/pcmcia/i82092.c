/*
 * Intel 82092AA PCI-to-PCMCIA bridge
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/core/qdev-properties.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_ids.h"
#include "migration/vmstate.h"
#include "qom/object.h"

#define TYPE_I82092AA "i82092aa"
OBJECT_DECLARE_SIMPLE_TYPE(I82092AAState, I82092AA)

#define I82092AA_MAX_SOCKETS       4
#define I82092AA_EXCA_REGS         0x100
#define I82092AA_SOCKET_STRIDE     0x40

#define I82092AA_PCICON            0x40
#define I82092AA_PCICON_SOCKETMASK 0x06
#define I82092AA_PCICON_1SOCKET    0x02
#define I82092AA_PCICON_2SOCKET    0x00
#define I82092AA_PCICON_4SOCKET    0x04
#define I82092AA_PCICON_WRMASK     0x39
#define I82092AA_PPIRR             0x50

#define I365_IDENT                 0x00
#define I365_STATUS                0x01
#define I365_POWER                 0x02
#define I365_INTCTL                0x03
#define I365_CSC                   0x04
#define I365_CSCINT                0x05
#define I365_ADDRWIN               0x06
#define I365_IOCTL                 0x07
#define I365_GENCTL                0x16
#define I365_GBLCTL                0x1e

#define I365_PWR_OUT               0x80
#define I365_CS_POWERON            0x40

struct I82092AAState {
    PCIDevice parent_obj;

    MemoryRegion io;
    uint8_t index;
    uint8_t regs[I82092AA_EXCA_REGS];
    uint8_t sockets;
};

static bool i82092aa_socket_present(const I82092AAState *s, uint8_t index)
{
    return (index / I82092AA_SOCKET_STRIDE) < s->sockets;
}

static bool i82092aa_exca_writable(uint8_t reg)
{
    if (reg == I365_IDENT || reg == I365_POWER || reg == I365_INTCTL ||
        reg == I365_CSCINT || reg == I365_ADDRWIN || reg == I365_IOCTL ||
        reg == I365_GENCTL || reg == I365_GBLCTL) {
        return true;
    }

    if (reg >= 0x08 && reg <= 0x15) {
        return true;
    }
    if (reg >= 0x18 && reg <= 0x1d) {
        return true;
    }
    if (reg >= 0x20 && reg <= 0x25) {
        return true;
    }
    if (reg >= 0x28 && reg <= 0x2d) {
        return true;
    }
    if (reg >= 0x30 && reg <= 0x35) {
        return true;
    }

    return false;
}

static uint64_t i82092aa_io_read(void *opaque, hwaddr addr, unsigned size)
{
    I82092AAState *s = opaque;
    uint8_t reg;
    uint8_t value;

    if (addr == 0) {
        return s->index;
    }
    if (addr != 1 || !i82092aa_socket_present(s, s->index)) {
        return 0xff;
    }

    reg = s->index & (I82092AA_SOCKET_STRIDE - 1);
    value = s->regs[s->index];

    /*
     * Card-status-change bits are latched events and are cleared by a read.
     * The current model has no attached PC Card yet, so these bits can only
     * become nonzero through future socket/card integration.
     */
    if (reg == I365_CSC) {
        s->regs[s->index] = 0;
    }

    return value;
}

static void i82092aa_io_write(void *opaque, hwaddr addr,
                              uint64_t value, unsigned size)
{
    I82092AAState *s = opaque;
    uint8_t reg;
    uint8_t socket_base;

    if (addr == 0) {
        s->index = value;
        return;
    }
    if (addr != 1 || !i82092aa_socket_present(s, s->index)) {
        return;
    }

    reg = s->index & (I82092AA_SOCKET_STRIDE - 1);
    if (!i82092aa_exca_writable(reg)) {
        return;
    }

    s->regs[s->index] = value;

    if (reg == I365_POWER) {
        socket_base = s->index & ~(I82092AA_SOCKET_STRIDE - 1);
        if (value & I365_PWR_OUT) {
            s->regs[socket_base + I365_STATUS] |= I365_CS_POWERON;
        } else {
            s->regs[socket_base + I365_STATUS] &= ~I365_CS_POWERON;
        }
    }
}

static const MemoryRegionOps i82092aa_io_ops = {
    .read = i82092aa_io_read,
    .write = i82092aa_io_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static uint8_t i82092aa_socket_config(unsigned sockets)
{
    switch (sockets) {
    case 1:
        return I82092AA_PCICON_1SOCKET;
    case 2:
        return I82092AA_PCICON_2SOCKET;
    case 4:
        return I82092AA_PCICON_4SOCKET;
    default:
        g_assert_not_reached();
    }
}

static void i82092aa_reset(DeviceState *dev)
{
    I82092AAState *s = I82092AA(dev);
    PCIDevice *pci = PCI_DEVICE(dev);
    unsigned i;

    s->index = 0;
    memset(s->regs, 0, sizeof(s->regs));

    /*
     * Intel documents 0x84 as the default Identification Register value.
     * The low nibble remains writable so software can request 82365SL
     * compatibility behavior.
     */
    for (i = 0; i < s->sockets; i++) {
        s->regs[i * I82092AA_SOCKET_STRIDE + I365_IDENT] = 0x84;
    }

    pci_set_byte(pci->config + I82092AA_PCICON,
                 i82092aa_socket_config(s->sockets));
    pci_set_byte(pci->config + I82092AA_PPIRR, 0x00);
}

static void i82092aa_realize(PCIDevice *dev, Error **errp)
{
    I82092AAState *s = I82092AA(dev);

    if (s->sockets != 1 && s->sockets != 2 && s->sockets != 4) {
        error_setg(errp, "i82092aa sockets must be 1, 2, or 4");
        return;
    }

    /*
     * BAR0 contains the ExCA index/data pair.  PCI I/O BARs have a minimum
     * four-byte aperture; only offsets 0 and 1 are implemented by the PPEC.
     */
    memory_region_init_io(&s->io, OBJECT(s), &i82092aa_io_ops, s,
                          "i82092aa-exca", 4);
    pci_register_bar(dev, 0, PCI_BASE_ADDRESS_SPACE_IO, &s->io);

    pci_set_byte(dev->config + PCI_INTERRUPT_PIN, 1);

    /*
     * PCICON bits 2:1 are read-only socket-configuration straps.  Bits 5:3
     * control enhanced timing/read-prefetch/post-write buffering and bit 0
     * selects the PCI clock timing profile.
     */
    pci_set_byte(dev->wmask + I82092AA_PCICON, I82092AA_PCICON_WRMASK);
    pci_set_byte(dev->wmask + I82092AA_PPIRR, 0xff);

    i82092aa_reset(DEVICE(dev));
}

static const VMStateDescription vmstate_i82092aa = {
    .name = "i82092aa",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_PCI_DEVICE(parent_obj, I82092AAState),
        VMSTATE_UINT8(index, I82092AAState),
        VMSTATE_UINT8_ARRAY(regs, I82092AAState, I82092AA_EXCA_REGS),
        VMSTATE_UINT8(sockets, I82092AAState),
        VMSTATE_END_OF_LIST()
    },
};

static const Property i82092aa_properties[] = {
    DEFINE_PROP_UINT8("sockets", I82092AAState, sockets, 2),
};

static void i82092aa_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);

    pc->realize = i82092aa_realize;
    pc->vendor_id = PCI_VENDOR_ID_INTEL;
    pc->device_id = PCI_DEVICE_ID_INTEL_82092AA_0;
    pc->revision = 0x01;
    pc->class_id = PCI_CLASS_BRIDGE_PCMCIA;

    device_class_set_legacy_reset(dc, i82092aa_reset);
    device_class_set_props(dc, i82092aa_properties);
    dc->desc = "Intel 82092AA PCI-to-PCMCIA bridge";
    dc->vmsd = &vmstate_i82092aa;
    set_bit(DEVICE_CATEGORY_BRIDGE, dc->categories);
}

static const TypeInfo i82092aa_info = {
    .name = TYPE_I82092AA,
    .parent = TYPE_PCI_DEVICE,
    .instance_size = sizeof(I82092AAState),
    .class_init = i82092aa_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void i82092aa_register_types(void)
{
    type_register_static(&i82092aa_info);
}

type_init(i82092aa_register_types)
