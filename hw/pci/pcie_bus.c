/*
 * QEMU PCI Express bus initialization and topology policy
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
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "pci-internal.h"

/*
 * PCIe and CXL derive from the shared PCI bus. Keep link-specific
 * configuration-space and slot policies here, including for builds
 * that permit PCIe devices on conventional PCI buses.
 */

static void pcie_bus_realize(BusState *qbus, Error **errp)
{
    PCIBus *bus = PCI_BUS(qbus);
    Error *local_err = NULL;

    pci_bus_realize(qbus, &local_err);
    if (local_err) {
        error_propagate(errp, local_err);
        return;
    }

    /*
     * A PCI-E bus can support extended config space if it's the root
     * bus, or if the bus/bridge above it does as well
     */
    if (pci_bus_is_root(bus)) {
        bus->flags |= PCI_BUS_EXTENDED_CONFIG_SPACE;
    } else {
        PCIBus *parent_bus = pci_get_bus(bus->parent_dev);

        if (pci_bus_allows_extended_config_space(parent_bus)) {
            bus->flags |= PCI_BUS_EXTENDED_CONFIG_SPACE;
        }
    }
}

static void pcie_bus_class_init(ObjectClass *klass, const void *data)
{
    BusClass *k = BUS_CLASS(klass);

    k->realize = pcie_bus_realize;
}

static const TypeInfo pcie_bus_info = {
    .name = TYPE_PCIE_BUS,
    .parent = TYPE_PCI_BUS,
    .class_init = pcie_bus_class_init,
};

static const TypeInfo cxl_bus_info = {
    .name       = TYPE_CXL_BUS,
    .parent     = TYPE_PCIE_BUS,
    .class_init = pcie_bus_class_init,
};

bool pcie_has_upstream_port(PCIDevice *dev)
{
    PCIDevice *parent_dev = pci_bridge_get_device(pci_get_bus(dev));

    /* Device associated with an upstream port.
     * As there are several types of these, it's easier to check the
     * parent device: upstream ports are always connected to
     * root or downstream ports.
     */
    return parent_dev &&
        pci_is_express(parent_dev) &&
        parent_dev->exp.exp_cap &&
        (pcie_cap_get_type(parent_dev) == PCI_EXP_TYPE_ROOT_PORT ||
         pcie_cap_get_type(parent_dev) == PCI_EXP_TYPE_DOWNSTREAM);
}

void pcie_bus_check_slot(PCIDevice *pci_dev)
{
    /*
     * A PCIe Downstream Port that do not have ARI Forwarding enabled must
     * associate only Device 0 with the device attached to the bus
     * representing the Link from the Port (PCIe base spec rev 4.0 ver 0.3,
     * sec 7.3.1).
     * With ARI, PCI_SLOT() can return non-zero value as the traditional
     * 5-bit Device Number and 3-bit Function Number fields in its associated
     * Routing IDs, Requester IDs and Completer IDs are interpreted as a
     * single 8-bit Function Number. Hence, ignore ARI capable devices.
     */
    if (!pcie_find_capability(pci_dev, PCI_EXT_CAP_ID_ARI) &&
        pcie_has_upstream_port(pci_dev) &&
        PCI_SLOT(pci_dev->devfn)) {
        warn_report("PCI: slot %d is not valid for %s,"
                    " parent device only allows plugging into slot 0.",
                    PCI_SLOT(pci_dev->devfn), pci_dev->name);
    }
}

void pcie_bus_register_types(void)
{
    type_register_static(&pcie_bus_info);
    type_register_static(&cxl_bus_info);
}
