/* SPDX-License-Identifier: MIT */
#ifndef HW_ISA_PIIX_INTERNAL_H
#define HW_ISA_PIIX_INTERNAL_H

#include "hw/southbridge/piix.h"

/* Chipset-specific PCI-to-ISA interrupt routing. */
void piix_rebuild_irq_levels(PIIXState *s);
void piix_set_pci_irq(void *opaque, int pirq, int level);
PCIINTxRoute piix_route_intx_pin_to_irq(void *opaque, int pin);
void piix_write_config(PCIDevice *dev, uint32_t address, uint32_t val,
                       int len);

#endif
