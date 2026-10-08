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
#include "hw/pcmcia/pcmcia.h"
#include "migration/vmstate.h"
#include "qom/object.h"

#define TYPE_I82092AA "i82092aa"
OBJECT_DECLARE_SIMPLE_TYPE(I82092AAState, I82092AA)

#define I82092AA_MAX_SOCKETS       4
#define I82092AA_IO_WINDOWS        2
#define I82092AA_MEM_WINDOWS       5
#define I82092AA_EXCA_REGS         0x100
#define I82092AA_SOCKET_STRIDE     0x40

#define I82092AA_PCICON            0x40
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

#define I365_IO(map)               (0x08 + ((map) << 2))
#define I365_MEM(map)              (0x10 + ((map) << 3))
#define I365_W_START               0
#define I365_W_STOP                2
#define I365_W_OFF                 4

#define I365_CS_DETECT             0x0c
#define I365_CS_READY              0x20
#define I365_CS_POWERON            0x40

#define I365_PWR_OUT               0x80
#define I365_VCC_MASK              0x18
#define I365_PC_RESET              0x40

#define I365_CSC_DETECT            0x08
#define I365_CSC_READY             0x04
#define I365_CSC_ANY               0x0f

#define I365_ENA_IO(map)           (0x40 << (map))
#define I365_IOCTL_16BIT(map)      (0x01 << ((map) << 2))
#define I365_ENA_MEM(map)          (0x01 << (map))

#define I365_MEM_REG               0x4000

typedef struct I82092AAWindow {
    MemoryRegion mr;
    I82092AAState *owner;
    uint32_t card_base;
    uint8_t socket;
    uint8_t map;
    bool attribute;
} I82092AAWindow;

struct I82092AAState {
    PCIDevice parent_obj;

    MemoryRegion io;
    uint8_t index;
    uint8_t regs[I82092AA_EXCA_REGS];
    uint8_t sockets;

    PCMCIABus socket_bus[I82092AA_MAX_SOCKETS];
    qemu_irq card_irq[I82092AA_MAX_SOCKETS];
    uint8_t card_irq_levels;

    I82092AAWindow io_window[I82092AA_MAX_SOCKETS][I82092AA_IO_WINDOWS];
    I82092AAWindow mem_window[I82092AA_MAX_SOCKETS][I82092AA_MEM_WINDOWS];
};

/* Card detect is mechanical; READY and access require power and released reset. */
static bool i82092aa_socket_powered(I82092AAState *s, unsigned socket)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE;
    uint8_t power = s->regs[base + I365_POWER];

    return (power & I365_PWR_OUT) && (power & I365_VCC_MASK);
}

static bool i82092aa_card_ready(I82092AAState *s, unsigned socket)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE;

    return pcmcia_bus_card_present(&s->socket_bus[socket]) &&
           i82092aa_socket_powered(s, socket) &&
           (s->regs[base + I365_INTCTL] & I365_PC_RESET);
}

static void i82092aa_update_irq(I82092AAState *s)
{
    bool level = false;
    unsigned socket;

    for (socket = 0; socket < s->sockets; socket++) {
        unsigned base = socket * I82092AA_SOCKET_STRIDE;

        if ((s->card_irq_levels & (1U << socket)) &&
            i82092aa_card_ready(s, socket)) {
            level = true;
        }
        if (s->regs[base + I365_CSC] &
            s->regs[base + I365_CSCINT] & I365_CSC_ANY) {
            level = true;
        }
    }
    pci_set_irq(PCI_DEVICE(s), level);
}

static void i82092aa_update_socket_status(I82092AAState *s, unsigned socket)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE;
    uint8_t *status = &s->regs[base + I365_STATUS];
    bool was_ready = !!(*status & I365_CS_READY);
    bool ready = i82092aa_card_ready(s, socket);

    *status &= ~(I365_CS_DETECT | I365_CS_READY | I365_CS_POWERON);
    if (pcmcia_bus_card_present(&s->socket_bus[socket])) {
        *status |= I365_CS_DETECT;
    }
    if (i82092aa_socket_powered(s, socket)) {
        *status |= I365_CS_POWERON;
    }
    if (ready) {
        *status |= I365_CS_READY;
    }
    if (was_ready != ready) {
        s->regs[base + I365_CSC] |= I365_CSC_READY;
    }
    i82092aa_update_irq(s);
}

static uint16_t i82092aa_reg16(I82092AAState *s, unsigned socket,
                               unsigned reg)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE + reg;

    return s->regs[base] | (s->regs[base + 1] << 8);
}

static bool i82092aa_socket_present(const I82092AAState *s, uint8_t index)
{
    return (index / I82092AA_SOCKET_STRIDE) < s->sockets;
}

static uint64_t i82092aa_card_io_read(void *opaque, hwaddr addr,
                                      unsigned size)
{
    I82092AAWindow *window = opaque;
    PCMCIABus *bus = &window->owner->socket_bus[window->socket];

    I82092AAState *s = window->owner;
    uint32_t card_addr = window->card_base + addr;
    uint16_t lo = pcmcia_bus_io_read(bus, card_addr) & 0xff;

    if (size == 2) {
        uint8_t ioctl = s->regs[window->socket * I82092AA_SOCKET_STRIDE +
                                I365_IOCTL];

        /* A 16-bit card window performs one word transaction. */
        if (ioctl & I365_IOCTL_16BIT(window->map)) {
            return pcmcia_bus_io_read(bus, card_addr);
        }
        /* In 8-bit mode, a host word access is two byte transactions. */
        return lo | ((pcmcia_bus_io_read(bus, card_addr + 1) & 0xff) << 8);
    }
    return lo;
}

static void i82092aa_card_io_write(void *opaque, hwaddr addr,
                                    uint64_t value, unsigned size)
{
    I82092AAWindow *window = opaque;
    PCMCIABus *bus = &window->owner->socket_bus[window->socket];

    I82092AAState *s = window->owner;
    uint32_t card_addr = window->card_base + addr;

    if (size == 2) {
        uint8_t ioctl = s->regs[window->socket * I82092AA_SOCKET_STRIDE +
                                I365_IOCTL];

        if (!(ioctl & I365_IOCTL_16BIT(window->map))) {
            pcmcia_bus_io_write(bus, card_addr, value & 0xff);
            pcmcia_bus_io_write(bus, card_addr + 1, (value >> 8) & 0xff);
            return;
        }
    }
    pcmcia_bus_io_write(bus, card_addr, value);
}

static const MemoryRegionOps i82092aa_card_io_ops = {
    .read = i82092aa_card_io_read,
    .write = i82092aa_card_io_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 2,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 2,
    },
};

static uint64_t i82092aa_card_mem_read(void *opaque, hwaddr addr,
                                       unsigned size)
{
    I82092AAWindow *window = opaque;
    PCMCIABus *bus = &window->owner->socket_bus[window->socket];
    uint32_t card_addr = window->card_base + addr;
    uint64_t value = 0;
    unsigned i;

    if (window->attribute) {
        for (i = 0; i < size; i++) {
            value |= (uint64_t)pcmcia_bus_attr_read(bus, card_addr + i)
                     << (i * 8);
        }
        return value;
    }

    if (size == 2) {
        return pcmcia_bus_common_read(bus, card_addr);
    }
    return pcmcia_bus_common_read(bus, card_addr) & 0xff;
}

static void i82092aa_card_mem_write(void *opaque, hwaddr addr,
                                    uint64_t value, unsigned size)
{
    I82092AAWindow *window = opaque;
    PCMCIABus *bus = &window->owner->socket_bus[window->socket];
    uint32_t card_addr = window->card_base + addr;
    unsigned i;

    if (window->attribute) {
        for (i = 0; i < size; i++) {
            pcmcia_bus_attr_write(bus, card_addr + i,
                                  (value >> (i * 8)) & 0xff);
        }
        return;
    }

    if (size == 2) {
        pcmcia_bus_common_write(bus, card_addr, value);
    } else {
        pcmcia_bus_common_write(bus, card_addr, value & 0xff);
    }
}

static const MemoryRegionOps i82092aa_card_mem_ops = {
    .read = i82092aa_card_mem_read,
    .write = i82092aa_card_mem_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 2,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 2,
    },
};

static void i82092aa_update_io_window(I82092AAState *s, unsigned socket,
                                       unsigned map)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE;
    I82092AAWindow *window = &s->io_window[socket][map];
    uint16_t start = i82092aa_reg16(s, socket, I365_IO(map) + I365_W_START);
    uint16_t stop = i82092aa_reg16(s, socket, I365_IO(map) + I365_W_STOP);
    bool enabled = i82092aa_card_ready(s, socket) &&
                   (s->regs[base + I365_ADDRWIN] & I365_ENA_IO(map)) &&
                   stop >= start;

    memory_region_transaction_begin();
    memory_region_set_enabled(&window->mr, false);
    if (stop >= start) {
        window->card_base = 0;
        memory_region_set_size(&window->mr, (uint32_t)stop - start + 1);
        memory_region_set_address(&window->mr, start);
    }
    memory_region_set_enabled(&window->mr, enabled);
    memory_region_transaction_commit();
}

static void i82092aa_update_mem_window(I82092AAState *s, unsigned socket,
                                        unsigned map)
{
    unsigned base = socket * I82092AA_SOCKET_STRIDE;
    unsigned reg = I365_MEM(map);
    I82092AAWindow *window = &s->mem_window[socket][map];
    uint16_t start_reg = i82092aa_reg16(s, socket, reg + I365_W_START);
    uint16_t stop_reg = i82092aa_reg16(s, socket, reg + I365_W_STOP);
    uint16_t off_reg = i82092aa_reg16(s, socket, reg + I365_W_OFF);
    uint32_t start = (start_reg & 0x0fff) << 12;
    uint32_t stop = ((stop_reg & 0x0fff) << 12) | 0xfff;
    int32_t page_offset = off_reg & 0x3fff;
    int64_t card_base;
    bool enabled;

    if (page_offset & 0x2000) {
        page_offset |= ~0x3fff;
    }
    card_base = (int64_t)start + ((int64_t)page_offset << 12);

    enabled = i82092aa_card_ready(s, socket) &&
              (s->regs[base + I365_ADDRWIN] & I365_ENA_MEM(map)) &&
              stop >= start && card_base >= 0;

    memory_region_transaction_begin();
    memory_region_set_enabled(&window->mr, false);
    if (stop >= start && card_base >= 0) {
        window->card_base = card_base;
        window->attribute = off_reg & I365_MEM_REG;
        memory_region_set_size(&window->mr, (uint64_t)stop - start + 1);
        memory_region_set_address(&window->mr, start);
    }
    memory_region_set_enabled(&window->mr, enabled);
    memory_region_transaction_commit();
}

static void i82092aa_update_windows(I82092AAState *s, unsigned socket)
{
    unsigned i;

    for (i = 0; i < I82092AA_IO_WINDOWS; i++) {
        i82092aa_update_io_window(s, socket, i);
    }
    for (i = 0; i < I82092AA_MEM_WINDOWS; i++) {
        i82092aa_update_mem_window(s, socket, i);
    }
}

static void i82092aa_card_irq(void *opaque, int n, int level)
{
    I82092AAState *s = opaque;

    if (level) {
        s->card_irq_levels |= 1U << n;
    } else {
        s->card_irq_levels &= ~(1U << n);
    }
    i82092aa_update_irq(s);
}

static void i82092aa_card_event(PCMCIABus *bus, bool inserted, void *opaque)
{
    I82092AAState *s = opaque;
    unsigned base = bus->socket * I82092AA_SOCKET_STRIDE;

    s->regs[base + I365_CSC] |= I365_CSC_DETECT;
    i82092aa_update_socket_status(s, bus->socket);
    i82092aa_update_windows(s, bus->socket);
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

    if (reg == I365_CSC) {
        s->regs[s->index] = 0;
        i82092aa_update_irq(s);
    }

    return value;
}

static void i82092aa_io_write(void *opaque, hwaddr addr,
                              uint64_t value, unsigned size)
{
    I82092AAState *s = opaque;
    uint8_t reg;
    uint8_t socket;

    if (addr == 0) {
        s->index = value;
        return;
    }
    if (addr != 1 || !i82092aa_socket_present(s, s->index)) {
        return;
    }

    socket = s->index / I82092AA_SOCKET_STRIDE;
    reg = s->index & (I82092AA_SOCKET_STRIDE - 1);
    if (!i82092aa_exca_writable(reg)) {
        return;
    }

    s->regs[s->index] = value;

    if (reg == I365_POWER || reg == I365_INTCTL) {
        i82092aa_update_socket_status(s, socket);
    }
    if (reg == I365_CSCINT) {
        i82092aa_update_irq(s);
    }
    if (reg == I365_POWER || reg == I365_INTCTL ||
        reg == I365_ADDRWIN || (reg >= 0x08 && reg <= 0x35)) {
        i82092aa_update_windows(s, socket);
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
    s->card_irq_levels = 0;
    memset(s->regs, 0, sizeof(s->regs));

    /*
     * Intel documents 0x84 as the default Identification Register value.
     * The register remains writable for 82365SL compatibility behavior.
     */
    for (i = 0; i < s->sockets; i++) {
        unsigned base = i * I82092AA_SOCKET_STRIDE;

        s->regs[base + I365_IDENT] = 0x84;
        i82092aa_update_socket_status(s, i);
        i82092aa_update_windows(s, i);
    }

    pci_set_byte(pci->config + I82092AA_PCICON,
                 i82092aa_socket_config(s->sockets));
    pci_set_byte(pci->config + I82092AA_PPIRR, 0x00);
    pci_set_irq(pci, 0);
}

static void i82092aa_realize(PCIDevice *dev, Error **errp)
{
    I82092AAState *s = I82092AA(dev);
    MemoryRegion *pci_io = pci_address_space_io(dev);
    MemoryRegion *pci_mem = pci_address_space(dev);
    unsigned socket;
    unsigned map;

    if (s->sockets != 1 && s->sockets != 2 && s->sockets != 4) {
        error_setg(errp, "i82092aa sockets must be 1, 2, or 4");
        return;
    }

    memory_region_init_io(&s->io, OBJECT(s), &i82092aa_io_ops, s,
                          "i82092aa-exca", 4);
    pci_register_bar(dev, 0, PCI_BASE_ADDRESS_SPACE_IO, &s->io);
    pci_set_byte(dev->config + PCI_INTERRUPT_PIN, 1);

    pci_set_byte(dev->wmask + I82092AA_PCICON, I82092AA_PCICON_WRMASK);
    pci_set_byte(dev->wmask + I82092AA_PPIRR, 0xff);

    for (socket = 0; socket < s->sockets; socket++) {
        s->card_irq[socket] = qemu_allocate_irq(i82092aa_card_irq, s, socket);
        pcmcia_bus_init(&s->socket_bus[socket], DEVICE(s), NULL, socket,
                        s->card_irq[socket], i82092aa_card_event, s);

        for (map = 0; map < I82092AA_IO_WINDOWS; map++) {
            I82092AAWindow *window = &s->io_window[socket][map];
            g_autofree char *name =
                g_strdup_printf("i82092aa-s%u-io%u", socket, map);

            window->owner = s;
            window->socket = socket;
            window->map = map;
            memory_region_init_io(&window->mr, OBJECT(s),
                                  &i82092aa_card_io_ops, window, name, 0x10000);
            memory_region_set_enabled(&window->mr, false);
            memory_region_add_subregion_overlap(pci_io, 0, &window->mr, 1);
        }

        for (map = 0; map < I82092AA_MEM_WINDOWS; map++) {
            I82092AAWindow *window = &s->mem_window[socket][map];
            g_autofree char *name =
                g_strdup_printf("i82092aa-s%u-mem%u", socket, map);

            window->owner = s;
            window->socket = socket;
            window->map = map;
            memory_region_init_io(&window->mr, OBJECT(s),
                                  &i82092aa_card_mem_ops, window, name,
                                  1U << 24);
            memory_region_set_enabled(&window->mr, false);
            memory_region_add_subregion_overlap(pci_mem, 0, &window->mr, 1);
        }
    }

    i82092aa_reset(DEVICE(dev));
}

static void i82092aa_exit(PCIDevice *dev)
{
    I82092AAState *s = I82092AA(dev);
    unsigned socket;
    unsigned map;

    for (socket = 0; socket < s->sockets; socket++) {
        for (map = 0; map < I82092AA_IO_WINDOWS; map++) {
            memory_region_del_subregion(pci_address_space_io(dev),
                                        &s->io_window[socket][map].mr);
        }
        for (map = 0; map < I82092AA_MEM_WINDOWS; map++) {
            memory_region_del_subregion(pci_address_space(dev),
                                        &s->mem_window[socket][map].mr);
        }
        qemu_free_irq(s->card_irq[socket]);
    }
}

static int i82092aa_post_load(void *opaque, int version_id)
{
    I82092AAState *s = opaque;
    unsigned socket;

    for (socket = 0; socket < s->sockets; socket++) {
        i82092aa_update_windows(s, socket);
    }
    i82092aa_update_irq(s);
    return 0;
}

static const VMStateDescription vmstate_i82092aa = {
    .name = "i82092aa",
    .version_id = 2,
    .minimum_version_id = 1,
    .post_load = i82092aa_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_PCI_DEVICE(parent_obj, I82092AAState),
        VMSTATE_UINT8(index, I82092AAState),
        VMSTATE_UINT8_ARRAY(regs, I82092AAState, I82092AA_EXCA_REGS),
        VMSTATE_UINT8(sockets, I82092AAState),
        VMSTATE_UINT8_V(card_irq_levels, I82092AAState, 2),
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
    pc->exit = i82092aa_exit;
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
