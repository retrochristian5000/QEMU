#ifndef HW_PCI_PCI_INTERNAL_H
#define HW_PCI_PCI_INTERNAL_H

#include "qemu/queue.h"

typedef struct {
    uint16_t class;
    const char *desc;
    const char *fw_name;
    uint16_t fw_ign_bits;
} pci_class_desc;

typedef QLIST_HEAD(, PCIHostState) PCIHostStateList;

extern PCIHostStateList pci_host_bridges;

const pci_class_desc *get_class_desc(int class);
PCIBus *pci_find_bus_nr(PCIBus *bus, int bus_num);
void pcibus_dev_print(Monitor *mon, DeviceState *dev, int indent);

/* Internal lifecycle and PCIe topology helpers. */
void pci_bus_realize(BusState *qbus, Error **errp);
void pcie_bus_register_types(void);
bool pcie_has_upstream_port(PCIDevice *dev);
void pcie_bus_check_slot(PCIDevice *pci_dev);

int pcie_aer_parse_error_string(const char *error_name,
                                uint32_t *status, bool *correctable);

#endif
