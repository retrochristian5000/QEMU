/*
 * QEMU PCI-family bus topology and root bus registry
 *
 * Copyright (c) 2004 Fabrice Bellard
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
#include "hw/pci/pci.h"
#include "hw/pci/pci_bus.h"
#include "hw/pci/pci_bridge.h"
#include "hw/pci/pci_host.h"
#include "pci-internal.h"

/*
 * Shared PCI-family topology. Conventional PCI, PCIe and CXL buses
 * retain their existing type hierarchy and configuration-space policies.
 * Chipset registers, device lifecycle, interrupt delivery and IOMMU
 * operations belong to their respective implementation layers.
 */

PCIHostStateList pci_host_bridges;

static void pci_host_bus_register(DeviceState *host)
{
    PCIHostState *host_bridge = PCI_HOST_BRIDGE(host);

    QLIST_INSERT_HEAD(&pci_host_bridges, host_bridge, next);
}

static void pci_host_bus_unregister(DeviceState *host)
{
    PCIHostState *host_bridge = PCI_HOST_BRIDGE(host);

    QLIST_REMOVE(host_bridge, next);
}

PCIBus *pci_device_root_bus(const PCIDevice *d)
{
    PCIBus *bus = pci_get_bus(d);

    while (!pci_bus_is_root(bus)) {
        d = bus->parent_dev;
        assert(d != NULL);

        bus = pci_get_bus(d);
    }

    return bus;
}

const char *pci_root_bus_path(PCIDevice *dev)
{
    PCIBus *rootbus = pci_device_root_bus(dev);
    PCIHostState *host_bridge = PCI_HOST_BRIDGE(rootbus->qbus.parent);
    PCIHostBridgeClass *hc = PCI_HOST_BRIDGE_GET_CLASS(host_bridge);

    assert(host_bridge->bus == rootbus);

    if (hc->root_bus_path) {
        return (*hc->root_bus_path)(host_bridge, rootbus);
    }

    return rootbus->qbus.name;
}

bool pci_bus_bypass_iommu(PCIBus *bus)
{
    PCIBus *rootbus = bus;
    PCIHostState *host_bridge;

    if (!pci_bus_is_root(bus)) {
        rootbus = pci_device_root_bus(bus->parent_dev);
    }

    host_bridge = PCI_HOST_BRIDGE(rootbus->qbus.parent);

    assert(host_bridge->bus == rootbus);

    return host_bridge->bypass_iommu;
}

static void pci_root_bus_internal_init(PCIBus *bus, DeviceState *parent,
                                       MemoryRegion *mem, MemoryRegion *io,
                                       uint8_t devfn_min)
{
    assert(PCI_FUNC(devfn_min) == 0);
    bus->devfn_min = devfn_min;
    bus->slot_reserved_mask = 0x0;
    bus->address_space_mem = mem;
    bus->address_space_io = io;
    bus->flags |= PCI_BUS_IS_ROOT;

    /* host bridge */
    QLIST_INIT(&bus->child);

    pci_host_bus_register(parent);
}

static void pci_bus_uninit(PCIBus *bus)
{
    pci_host_bus_unregister(BUS(bus)->parent);
}

bool pci_bus_is_express(const PCIBus *bus)
{
    return object_dynamic_cast(OBJECT(bus), TYPE_PCIE_BUS);
}

void pci_root_bus_init(PCIBus *bus, size_t bus_size, DeviceState *parent,
                       const char *name,
                       MemoryRegion *mem, MemoryRegion *io,
                       uint8_t devfn_min, const char *typename)
{
    qbus_init(bus, bus_size, typename, parent, name);
    pci_root_bus_internal_init(bus, parent, mem, io, devfn_min);
}

PCIBus *pci_root_bus_new(DeviceState *parent, const char *name,
                         MemoryRegion *mem, MemoryRegion *io,
                         uint8_t devfn_min, const char *typename)
{
    PCIBus *bus;

    bus = PCI_BUS(qbus_new(typename, parent, name));
    pci_root_bus_internal_init(bus, parent, mem, io, devfn_min);
    return bus;
}

void pci_root_bus_cleanup(PCIBus *bus)
{
    pci_bus_uninit(bus);
    /* the caller of the unplug hotplug handler will delete this device */
    qbus_unrealize(BUS(bus));
}

PCIBus *pci_register_root_bus(DeviceState *parent, const char *name,
                              pci_set_irq_fn set_irq, pci_map_irq_fn map_irq,
                              void *irq_opaque,
                              MemoryRegion *mem, MemoryRegion *io,
                              uint8_t devfn_min, int nirq,
                              const char *typename)
{
    PCIBus *bus;

    bus = pci_root_bus_new(parent, name, mem, io, devfn_min, typename);
    pci_bus_irqs(bus, set_irq, irq_opaque, nirq);
    pci_bus_map_irqs(bus, map_irq);
    return bus;
}

void pci_unregister_root_bus(PCIBus *bus)
{
    pci_bus_irqs_cleanup(bus);
    pci_root_bus_cleanup(bus);
}

int pci_bus_num(PCIBus *s)
{
    return PCI_BUS_GET_CLASS(s)->bus_num(s);
}

/* Returns the min and max bus numbers of a PCI bus hierarchy */
void pci_bus_range(PCIBus *bus, int *min_bus, int *max_bus)
{
    int i;
    *min_bus = *max_bus = pci_bus_num(bus);

    for (i = 0; i < ARRAY_SIZE(bus->devices); ++i) {
        PCIDevice *dev = bus->devices[i];

        if (dev && IS_PCI_BRIDGE(dev)) {
            *min_bus = MIN(*min_bus, dev->config[PCI_SECONDARY_BUS]);
            *max_bus = MAX(*max_bus, dev->config[PCI_SUBORDINATE_BUS]);
        }
    }
}

int pci_bus_numa_node(PCIBus *bus)
{
    return PCI_BUS_GET_CLASS(bus)->numa_node(bus);
}

uint32_t pci_bus_get_slot_reserved_mask(PCIBus *bus)
{
    return bus->slot_reserved_mask;
}

void pci_bus_set_slot_reserved_mask(PCIBus *bus, uint32_t mask)
{
    bus->slot_reserved_mask |= mask;
}

void pci_bus_clear_slot_reserved_mask(PCIBus *bus, uint32_t mask)
{
    bus->slot_reserved_mask &= ~mask;
}

/* Whether a given bus number is in range of the secondary
 * bus of the given bridge device. */
static bool pci_secondary_bus_in_range(PCIDevice *dev, int bus_num)
{
    return !(pci_get_word(dev->config + PCI_BRIDGE_CONTROL) &
             PCI_BRIDGE_CTL_BUS_RESET) /* Don't walk the bus if it's reset. */ &&
        dev->config[PCI_SECONDARY_BUS] <= bus_num &&
        bus_num <= dev->config[PCI_SUBORDINATE_BUS];
}

/* Whether a given bus number is in a range of a root bus */
static bool pci_root_bus_in_range(PCIBus *bus, int bus_num)
{
    int i;

    for (i = 0; i < ARRAY_SIZE(bus->devices); ++i) {
        PCIDevice *dev = bus->devices[i];

        if (dev && IS_PCI_BRIDGE(dev)) {
            if (pci_secondary_bus_in_range(dev, bus_num)) {
                return true;
            }
        }
    }

    return false;
}

PCIBus *pci_find_bus_nr(PCIBus *bus, int bus_num)
{
    PCIBus *sec;

    if (!bus) {
        return NULL;
    }

    if (pci_bus_num(bus) == bus_num) {
        return bus;
    }

    /* Consider all bus numbers in range for the host pci bridge. */
    if (!pci_bus_is_root(bus) &&
        !pci_secondary_bus_in_range(bus->parent_dev, bus_num)) {
        return NULL;
    }

    /* try child bus */
    for (; bus; bus = sec) {
        QLIST_FOREACH(sec, &bus->child, sibling) {
            if (pci_bus_num(sec) == bus_num) {
                return sec;
            }
            /* PXB buses assumed to be children of bus 0 */
            if (pci_bus_is_root(sec)) {
                if (pci_root_bus_in_range(sec, bus_num)) {
                    break;
                }
            } else {
                if (pci_secondary_bus_in_range(sec->parent_dev, bus_num)) {
                    break;
                }
            }
        }
    }

    return NULL;
}

void pci_for_each_bus_depth_first(PCIBus *bus, pci_bus_ret_fn begin,
                                  pci_bus_fn end, void *parent_state)
{
    PCIBus *sec;
    void *state;

    if (!bus) {
        return;
    }

    if (begin) {
        state = begin(bus, parent_state);
    } else {
        state = parent_state;
    }

    QLIST_FOREACH(sec, &bus->child, sibling) {
        pci_for_each_bus_depth_first(sec, begin, end, state);
    }

    if (end) {
        end(bus, state);
    }
}


PCIDevice *pci_find_device(PCIBus *bus, int bus_num, uint8_t devfn)
{
    bus = pci_find_bus_nr(bus, bus_num);

    if (!bus)
        return NULL;

    return bus->devices[devfn];
}

void pci_for_each_device_under_bus_reverse(PCIBus *bus,
                                           pci_bus_dev_fn fn,
                                           void *opaque)
{
    PCIDevice *d;
    int devfn;

    for (devfn = 0; devfn < ARRAY_SIZE(bus->devices); devfn++) {
        d = bus->devices[ARRAY_SIZE(bus->devices) - 1 - devfn];
        if (d) {
            fn(bus, d, opaque);
        }
    }
}

void pci_for_each_device_reverse(PCIBus *bus, int bus_num,
                                 pci_bus_dev_fn fn, void *opaque)
{
    bus = pci_find_bus_nr(bus, bus_num);

    if (bus) {
        pci_for_each_device_under_bus_reverse(bus, fn, opaque);
    }
}

void pci_for_each_device_under_bus(PCIBus *bus,
                                   pci_bus_dev_fn fn, void *opaque)
{
    PCIDevice *d;
    int devfn;

    for(devfn = 0; devfn < ARRAY_SIZE(bus->devices); devfn++) {
        d = bus->devices[devfn];
        if (d) {
            fn(bus, d, opaque);
        }
    }
}

void pci_for_each_device(PCIBus *bus, int bus_num,
                         pci_bus_dev_fn fn, void *opaque)
{
    bus = pci_find_bus_nr(bus, bus_num);

    if (bus) {
        pci_for_each_device_under_bus(bus, fn, opaque);
    }
}

