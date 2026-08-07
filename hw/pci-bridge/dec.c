/*
 * DEC 21154 PCI-to-PCI bridge
 *
 * This is a modernized restoration of QEMU's historical DEC 21154 model.
 * The device is used by the PowerMac3,1 (Sawtooth) machine profile to model
 * the 66 MHz UniNorth PCI bus to 33 MHz KeyLargo/slot PCI bus bridge.
 *
 * Copyright (c) 2006-2007 Fabrice Bellard
 * Copyright (c) 2007 Jocelyn Mayer
 *
 * SPDX-License-Identifier: MIT
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_bridge.h"
#include "hw/pci/pci_bus.h"
#include "hw/pci/pci_ids.h"
#include "hw/pci-bridge/dec.h"
#include "migration/vmstate.h"
#include "qom/object.h"

#define DEC_21154_DEVICE_ID 0x0026

static int dec_21154_map_irq(PCIDevice *pci_dev, int irq_num)
{
    return irq_num;
}

static void dec_21154_realize(PCIDevice *dev, Error **errp)
{
    pci_bridge_initfn(dev, TYPE_PCI_BUS);
}

static void dec_21154_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = dec_21154_realize;
    k->exit = pci_bridge_exitfn;
    k->vendor_id = PCI_VENDOR_ID_DEC;
    k->device_id = DEC_21154_DEVICE_ID;
    k->revision = 0x05;
    k->config_write = pci_bridge_write_config;

    dc->desc = "DEC 21154 PCI-PCI bridge";
    device_class_set_legacy_reset(dc, pci_bridge_reset);
    dc->vmsd = &vmstate_pci_device;
    set_bit(DEVICE_CATEGORY_BRIDGE, dc->categories);
}

static const TypeInfo dec_21154_info = {
    .name = TYPE_DEC_21154_P2P_BRIDGE,
    .parent = TYPE_PCI_BRIDGE,
    .instance_size = sizeof(PCIBridge),
    .class_init = dec_21154_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

PCIBus *pci_dec_21154_init(PCIBus *parent_bus, int devfn)
{
    PCIDevice *dev;
    PCIBridge *br;

    dev = pci_new_multifunction(devfn, TYPE_DEC_21154_P2P_BRIDGE);
    br = PCI_BRIDGE(dev);
    pci_bridge_map_irq(br, "DEC 21154 PCI-PCI bridge", dec_21154_map_irq);
    pci_realize_and_unref(dev, parent_bus, &error_fatal);

    return pci_bridge_get_sec_bus(br);
}

static void dec_21154_register_types(void)
{
    type_register_static(&dec_21154_info);
}

type_init(dec_21154_register_types)
