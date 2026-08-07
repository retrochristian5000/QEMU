/*
 * DEC 21154 PCI-to-PCI bridge
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef HW_PCI_BRIDGE_DEC_H
#define HW_PCI_BRIDGE_DEC_H

#include "hw/pci/pci.h"

#define TYPE_DEC_21154_P2P_BRIDGE "dec-21154-p2p-bridge"

PCIBus *pci_dec_21154_init(PCIBus *parent_bus, int devfn);

#endif /* HW_PCI_BRIDGE_DEC_H */
