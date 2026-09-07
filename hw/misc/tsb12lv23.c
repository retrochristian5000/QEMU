/*
 * Texas Instruments TSB12LV23 IEEE-1394 OHCI controller
 *
 * The first user is the Apple Power Mac G4 AGP (PowerMac3,1 / Sawtooth).
 * This models the PCI/OHCI controller boundary only.  A separate IEEE-1394
 * PHY and external bus are deliberately not invented here; PHY accesses
 * therefore report no attached PHY until that layer is implemented.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_device.h"
#include "hw/pci/pci_ids.h"
#include "migration/vmstate.h"
#include "qemu/module.h"
#include "qom/object.h"

#define TYPE_TSB12LV23 "tsb12lv23"
OBJECT_DECLARE_SIMPLE_TYPE(TSB12LV23State, TSB12LV23)

#define TSB12LV23_OHCI_SIZE 0x800
#define TSB12LV23_TI_SIZE 0x4000
#define TSB12LV23_PM_CAP_OFFSET 0x44

/* IEEE-1394 OHCI 1.0 register offsets used by probe/reset paths. */
#define OHCI_VERSION 0x000
#define OHCI_AT_RETRIES 0x008
#define OHCI_CSR_DATA 0x00c
#define OHCI_CSR_COMPARE 0x010
#define OHCI_CSR_CONTROL 0x014
#define OHCI_CONFIG_ROM_HDR 0x018
#define OHCI_BUS_ID 0x01c
#define OHCI_BUS_OPTIONS 0x020
#define OHCI_GUID_HI 0x024
#define OHCI_GUID_LO 0x028
#define OHCI_CONFIG_ROM_MAP 0x034
#define OHCI_POSTED_WRITE_LO 0x038
#define OHCI_POSTED_WRITE_HI 0x03c
#define OHCI_VENDOR_ID 0x040
#define OHCI_HC_CONTROL_SET 0x050
#define OHCI_HC_CONTROL_CLEAR 0x054
#define OHCI_SELF_ID_BUFFER 0x064
#define OHCI_SELF_ID_COUNT 0x068
#define OHCI_IR_MULTI_CHAN_MASK_HI_SET 0x070
#define OHCI_IR_MULTI_CHAN_MASK_HI_CLEAR 0x074
#define OHCI_IR_MULTI_CHAN_MASK_LO_SET 0x078
#define OHCI_IR_MULTI_CHAN_MASK_LO_CLEAR 0x07c
#define OHCI_INT_EVENT_SET 0x080
#define OHCI_INT_EVENT_CLEAR 0x084
#define OHCI_INT_MASK_SET 0x088
#define OHCI_INT_MASK_CLEAR 0x08c
#define OHCI_ISO_TX_INT_EVENT_SET 0x090
#define OHCI_ISO_TX_INT_EVENT_CLEAR 0x094
#define OHCI_ISO_TX_INT_MASK_SET 0x098
#define OHCI_ISO_TX_INT_MASK_CLEAR 0x09c
#define OHCI_ISO_RX_INT_EVENT_SET 0x0a0
#define OHCI_ISO_RX_INT_EVENT_CLEAR 0x0a4
#define OHCI_ISO_RX_INT_MASK_SET 0x0a8
#define OHCI_ISO_RX_INT_MASK_CLEAR 0x0ac
#define OHCI_INITIAL_BANDWIDTH 0x0b0
#define OHCI_INITIAL_CHANNELS_HI 0x0b4
#define OHCI_INITIAL_CHANNELS_LO 0x0b8
#define OHCI_FAIRNESS_CONTROL 0x0dc
#define OHCI_LINK_CONTROL_SET 0x0e0
#define OHCI_LINK_CONTROL_CLEAR 0x0e4
#define OHCI_NODE_ID 0x0e8
#define OHCI_PHY_CONTROL 0x0ec
#define OHCI_CYCLE_TIMER 0x0f0
#define OHCI_ASYNC_REQ_FILTER_HI_SET 0x100
#define OHCI_ASYNC_REQ_FILTER_HI_CLEAR 0x104
#define OHCI_ASYNC_REQ_FILTER_LO_SET 0x108
#define OHCI_ASYNC_REQ_FILTER_LO_CLEAR 0x10c
#define OHCI_PHY_REQ_FILTER_HI_SET 0x110
#define OHCI_PHY_REQ_FILTER_HI_CLEAR 0x114
#define OHCI_PHY_REQ_FILTER_LO_SET 0x118
#define OHCI_PHY_REQ_FILTER_LO_CLEAR 0x11c
#define OHCI_PHY_UPPER_BOUND 0x120

#define OHCI_HC_CONTROL_SOFT_RESET 0x00010000
#define OHCI_INT_MASTER_ENABLE 0x80000000u

/*
 * BusOptions: max_rec=0xa (2048 bytes), link_spd=2 (S400 capable).
 * No optional bus-manager/isochronous-resource-manager capabilities are
 * asserted until the corresponding IEEE-1394 bus layer exists.
 */
#define TSB12LV23_BUS_OPTIONS_RESET 0x0000a002

struct TSB12LV23State {
    PCIDevice parent_obj;

    MemoryRegion ohci_mmio;
    MemoryRegion ti_mmio;

    uint32_t at_retries;
    uint32_t csr_data;
    uint32_t csr_compare;
    uint32_t csr_control;
    uint32_t config_rom_hdr;
    uint32_t bus_options;
    uint32_t guid_hi;
    uint32_t guid_lo;
    uint32_t config_rom_map;
    uint32_t posted_write_lo;
    uint32_t posted_write_hi;
    uint32_t hc_control;
    uint32_t self_id_buffer;
    uint32_t self_id_count;
    uint32_t ir_mask_hi;
    uint32_t ir_mask_lo;
    uint32_t int_event;
    uint32_t int_mask;
    uint32_t iso_tx_event;
    uint32_t iso_tx_mask;
    uint32_t iso_rx_event;
    uint32_t iso_rx_mask;
    uint32_t initial_bandwidth;
    uint32_t initial_channels_hi;
    uint32_t initial_channels_lo;
    uint32_t fairness_control;
    uint32_t link_control;
    uint32_t cycle_timer;
    uint32_t async_req_filter_hi;
    uint32_t async_req_filter_lo;
    uint32_t phy_req_filter_hi;
    uint32_t phy_req_filter_lo;
    uint32_t phy_upper_bound;
};

static void tsb12lv23_update_irq(TSB12LV23State *s)
{
    uint32_t pending;

    pending = s->int_event & s->int_mask & ~OHCI_INT_MASTER_ENABLE;
    pci_set_irq(PCI_DEVICE(s),
                (s->int_mask & OHCI_INT_MASTER_ENABLE) && pending);
}

static void tsb12lv23_ohci_soft_reset(TSB12LV23State *s)
{
    s->at_retries = 0;
    s->csr_data = 0;
    s->csr_compare = 0;
    s->csr_control = 0;
    s->config_rom_hdr = 0;
    s->config_rom_map = 0;
    s->posted_write_lo = 0;
    s->posted_write_hi = 0;
    s->hc_control = 0;
    s->self_id_buffer = 0;
    s->self_id_count = 0;
    s->ir_mask_hi = 0;
    s->ir_mask_lo = 0;
    s->int_event = 0;
    s->int_mask = 0;
    s->iso_tx_event = 0;
    s->iso_tx_mask = 0;
    s->iso_rx_event = 0;
    s->iso_rx_mask = 0;
    s->initial_bandwidth = 0;
    s->initial_channels_hi = 0;
    s->initial_channels_lo = 0;
    s->fairness_control = 0;
    s->link_control = 0;
    s->cycle_timer = 0;
    s->async_req_filter_hi = 0;
    s->async_req_filter_lo = 0;
    s->phy_req_filter_hi = 0;
    s->phy_req_filter_lo = 0;
    s->phy_upper_bound = 0;

    /* Identity/capability state survives an OHCI software reset. */
    s->bus_options = TSB12LV23_BUS_OPTIONS_RESET;
    tsb12lv23_update_irq(s);
}

static uint64_t tsb12lv23_ohci_read(void *opaque, hwaddr addr, unsigned size)
{
    TSB12LV23State *s = opaque;

    switch (addr) {
    case OHCI_VERSION:
        return 0x00010000;
    case OHCI_AT_RETRIES:
        return s->at_retries;
    case OHCI_CSR_DATA:
        return s->csr_data;
    case OHCI_CSR_COMPARE:
        return s->csr_compare;
    case OHCI_CSR_CONTROL:
        return s->csr_control;
    case OHCI_CONFIG_ROM_HDR:
        return s->config_rom_hdr;
    case OHCI_BUS_ID:
        return 0x31333934;
    case OHCI_BUS_OPTIONS:
        return s->bus_options;
    case OHCI_GUID_HI:
        return s->guid_hi;
    case OHCI_GUID_LO:
        return s->guid_lo;
    case OHCI_CONFIG_ROM_MAP:
        return s->config_rom_map;
    case OHCI_POSTED_WRITE_LO:
        return s->posted_write_lo;
    case OHCI_POSTED_WRITE_HI:
        return s->posted_write_hi;
    case OHCI_VENDOR_ID:
        return 0;
    case OHCI_HC_CONTROL_SET:
    case OHCI_HC_CONTROL_CLEAR:
        return s->hc_control;
    case OHCI_SELF_ID_BUFFER:
        return s->self_id_buffer;
    case OHCI_SELF_ID_COUNT:
        return s->self_id_count;
    case OHCI_IR_MULTI_CHAN_MASK_HI_SET:
    case OHCI_IR_MULTI_CHAN_MASK_HI_CLEAR:
        return s->ir_mask_hi;
    case OHCI_IR_MULTI_CHAN_MASK_LO_SET:
    case OHCI_IR_MULTI_CHAN_MASK_LO_CLEAR:
        return s->ir_mask_lo;
    case OHCI_INT_EVENT_SET:
    case OHCI_INT_EVENT_CLEAR:
        return s->int_event;
    case OHCI_INT_MASK_SET:
    case OHCI_INT_MASK_CLEAR:
        return s->int_mask;
    case OHCI_ISO_TX_INT_EVENT_SET:
    case OHCI_ISO_TX_INT_EVENT_CLEAR:
        return s->iso_tx_event;
    case OHCI_ISO_TX_INT_MASK_SET:
    case OHCI_ISO_TX_INT_MASK_CLEAR:
        return s->iso_tx_mask;
    case OHCI_ISO_RX_INT_EVENT_SET:
    case OHCI_ISO_RX_INT_EVENT_CLEAR:
        return s->iso_rx_event;
    case OHCI_ISO_RX_INT_MASK_SET:
    case OHCI_ISO_RX_INT_MASK_CLEAR:
        return s->iso_rx_mask;
    case OHCI_INITIAL_BANDWIDTH:
        return s->initial_bandwidth;
    case OHCI_INITIAL_CHANNELS_HI:
        return s->initial_channels_hi;
    case OHCI_INITIAL_CHANNELS_LO:
        return s->initial_channels_lo;
    case OHCI_FAIRNESS_CONTROL:
        return s->fairness_control;
    case OHCI_LINK_CONTROL_SET:
    case OHCI_LINK_CONTROL_CLEAR:
        return s->link_control;
    case OHCI_NODE_ID:
        /* No PHY/self-ID layer exists yet, so no valid node ID is assigned. */
        return 0;
    case OHCI_PHY_CONTROL:
        /* Linux treats all-ones as a clean "PHY absent" response. */
        return UINT32_MAX;
    case OHCI_CYCLE_TIMER:
        return s->cycle_timer;
    case OHCI_ASYNC_REQ_FILTER_HI_SET:
    case OHCI_ASYNC_REQ_FILTER_HI_CLEAR:
        return s->async_req_filter_hi;
    case OHCI_ASYNC_REQ_FILTER_LO_SET:
    case OHCI_ASYNC_REQ_FILTER_LO_CLEAR:
        return s->async_req_filter_lo;
    case OHCI_PHY_REQ_FILTER_HI_SET:
    case OHCI_PHY_REQ_FILTER_HI_CLEAR:
        return s->phy_req_filter_hi;
    case OHCI_PHY_REQ_FILTER_LO_SET:
    case OHCI_PHY_REQ_FILTER_LO_CLEAR:
        return s->phy_req_filter_lo;
    case OHCI_PHY_UPPER_BOUND:
        return s->phy_upper_bound;
    default:
        /* DMA contexts and unimplemented optional registers remain quiescent. */
        return 0;
    }
}

static void tsb12lv23_ohci_write(void *opaque, hwaddr addr, uint64_t value,
                                 unsigned size)
{
    TSB12LV23State *s = opaque;
    uint32_t val = value;

    switch (addr) {
    case OHCI_AT_RETRIES:
        s->at_retries = val;
        break;
    case OHCI_CSR_DATA:
        s->csr_data = val;
        break;
    case OHCI_CSR_COMPARE:
        s->csr_compare = val;
        break;
    case OHCI_CSR_CONTROL:
        s->csr_control = val;
        break;
    case OHCI_CONFIG_ROM_HDR:
        s->config_rom_hdr = val;
        break;
    case OHCI_BUS_OPTIONS:
        s->bus_options = val;
        break;
    case OHCI_GUID_HI:
        s->guid_hi = val;
        break;
    case OHCI_GUID_LO:
        s->guid_lo = val;
        break;
    case OHCI_CONFIG_ROM_MAP:
        s->config_rom_map = val;
        break;
    case OHCI_POSTED_WRITE_LO:
        s->posted_write_lo = val;
        break;
    case OHCI_POSTED_WRITE_HI:
        s->posted_write_hi = val;
        break;
    case OHCI_HC_CONTROL_SET:
        if (val & OHCI_HC_CONTROL_SOFT_RESET) {
            tsb12lv23_ohci_soft_reset(s);
            val &= ~OHCI_HC_CONTROL_SOFT_RESET;
        }
        s->hc_control |= val;
        break;
    case OHCI_HC_CONTROL_CLEAR:
        s->hc_control &= ~val;
        break;
    case OHCI_SELF_ID_BUFFER:
        s->self_id_buffer = val;
        break;
    case OHCI_SELF_ID_COUNT:
        s->self_id_count = val;
        break;
    case OHCI_IR_MULTI_CHAN_MASK_HI_SET:
        s->ir_mask_hi |= val;
        break;
    case OHCI_IR_MULTI_CHAN_MASK_HI_CLEAR:
        s->ir_mask_hi &= ~val;
        break;
    case OHCI_IR_MULTI_CHAN_MASK_LO_SET:
        s->ir_mask_lo |= val;
        break;
    case OHCI_IR_MULTI_CHAN_MASK_LO_CLEAR:
        s->ir_mask_lo &= ~val;
        break;
    case OHCI_INT_EVENT_SET:
        s->int_event |= val;
        tsb12lv23_update_irq(s);
        break;
    case OHCI_INT_EVENT_CLEAR:
        s->int_event &= ~val;
        tsb12lv23_update_irq(s);
        break;
    case OHCI_INT_MASK_SET:
        s->int_mask |= val;
        tsb12lv23_update_irq(s);
        break;
    case OHCI_INT_MASK_CLEAR:
        s->int_mask &= ~val;
        tsb12lv23_update_irq(s);
        break;
    case OHCI_ISO_TX_INT_EVENT_SET:
        s->iso_tx_event |= val;
        break;
    case OHCI_ISO_TX_INT_EVENT_CLEAR:
        s->iso_tx_event &= ~val;
        break;
    case OHCI_ISO_TX_INT_MASK_SET:
        s->iso_tx_mask |= val;
        break;
    case OHCI_ISO_TX_INT_MASK_CLEAR:
        s->iso_tx_mask &= ~val;
        break;
    case OHCI_ISO_RX_INT_EVENT_SET:
        s->iso_rx_event |= val;
        break;
    case OHCI_ISO_RX_INT_EVENT_CLEAR:
        s->iso_rx_event &= ~val;
        break;
    case OHCI_ISO_RX_INT_MASK_SET:
        s->iso_rx_mask |= val;
        break;
    case OHCI_ISO_RX_INT_MASK_CLEAR:
        s->iso_rx_mask &= ~val;
        break;
    case OHCI_INITIAL_BANDWIDTH:
        s->initial_bandwidth = val;
        break;
    case OHCI_INITIAL_CHANNELS_HI:
        s->initial_channels_hi = val;
        break;
    case OHCI_INITIAL_CHANNELS_LO:
        s->initial_channels_lo = val;
        break;
    case OHCI_FAIRNESS_CONTROL:
        s->fairness_control = val;
        break;
    case OHCI_LINK_CONTROL_SET:
        s->link_control |= val;
        break;
    case OHCI_LINK_CONTROL_CLEAR:
        s->link_control &= ~val;
        break;
    case OHCI_CYCLE_TIMER:
        s->cycle_timer = val;
        break;
    case OHCI_ASYNC_REQ_FILTER_HI_SET:
        s->async_req_filter_hi |= val;
        break;
    case OHCI_ASYNC_REQ_FILTER_HI_CLEAR:
        s->async_req_filter_hi &= ~val;
        break;
    case OHCI_ASYNC_REQ_FILTER_LO_SET:
        s->async_req_filter_lo |= val;
        break;
    case OHCI_ASYNC_REQ_FILTER_LO_CLEAR:
        s->async_req_filter_lo &= ~val;
        break;
    case OHCI_PHY_REQ_FILTER_HI_SET:
        s->phy_req_filter_hi |= val;
        break;
    case OHCI_PHY_REQ_FILTER_HI_CLEAR:
        s->phy_req_filter_hi &= ~val;
        break;
    case OHCI_PHY_REQ_FILTER_LO_SET:
        s->phy_req_filter_lo |= val;
        break;
    case OHCI_PHY_REQ_FILTER_LO_CLEAR:
        s->phy_req_filter_lo &= ~val;
        break;
    case OHCI_PHY_UPPER_BOUND:
        s->phy_upper_bound = val;
        break;
    case OHCI_PHY_CONTROL:
        /* No PHY is attached in this controller-only implementation. */
        break;
    default:
        /* Keep unimplemented DMA/PHY functionality inert, not fabricated. */
        break;
    }
}

static const MemoryRegionOps tsb12lv23_ohci_ops = {
    .read = tsb12lv23_ohci_read,
    .write = tsb12lv23_ohci_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static uint64_t tsb12lv23_ti_read(void *opaque, hwaddr addr, unsigned size)
{
    /* TI extension registers are not needed for controller discovery yet. */
    return 0;
}

static void tsb12lv23_ti_write(void *opaque, hwaddr addr, uint64_t value,
                               unsigned size)
{
    /* Intentionally inert until an attested guest-visible behavior needs it. */
}

static const MemoryRegionOps tsb12lv23_ti_ops = {
    .read = tsb12lv23_ti_read,
    .write = tsb12lv23_ti_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static void tsb12lv23_reset(DeviceState *dev)
{
    TSB12LV23State *s = TSB12LV23(dev);

    tsb12lv23_ohci_soft_reset(s);
}

static void tsb12lv23_realize(PCIDevice *pdev, Error **errp)
{
    TSB12LV23State *s = TSB12LV23(pdev);

    pdev->config[PCI_CLASS_PROG] = 0x10;
    pci_config_set_interrupt_pin(pdev->config, 1);
    pdev->config[PCI_MIN_GNT] = 0x02;
    pdev->config[PCI_MAX_LAT] = 0x04;

    if (pci_pm_init(pdev, TSB12LV23_PM_CAP_OFFSET, errp) < 0) {
        return;
    }
    pci_set_word(pdev->config + TSB12LV23_PM_CAP_OFFSET + PCI_PM_PMC, 0x6411);

    /* PCI OHCI Control: bit 0 is TI GLOBAL_SWAP and is guest-writable. */
    pdev->wmask[0x40] = 0x01;

    memory_region_init_io(&s->ohci_mmio, OBJECT(s), &tsb12lv23_ohci_ops,
                          s, "tsb12lv23-ohci", TSB12LV23_OHCI_SIZE);
    memory_region_init_io(&s->ti_mmio, OBJECT(s), &tsb12lv23_ti_ops,
                          s, "tsb12lv23-ti", TSB12LV23_TI_SIZE);
    pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ohci_mmio);
    pci_register_bar(pdev, 1, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ti_mmio);
}

static const VMStateDescription vmstate_tsb12lv23 = {
    .name = "tsb12lv23",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(at_retries, TSB12LV23State),
        VMSTATE_UINT32(csr_data, TSB12LV23State),
        VMSTATE_UINT32(csr_compare, TSB12LV23State),
        VMSTATE_UINT32(csr_control, TSB12LV23State),
        VMSTATE_UINT32(config_rom_hdr, TSB12LV23State),
        VMSTATE_UINT32(bus_options, TSB12LV23State),
        VMSTATE_UINT32(guid_hi, TSB12LV23State),
        VMSTATE_UINT32(guid_lo, TSB12LV23State),
        VMSTATE_UINT32(config_rom_map, TSB12LV23State),
        VMSTATE_UINT32(posted_write_lo, TSB12LV23State),
        VMSTATE_UINT32(posted_write_hi, TSB12LV23State),
        VMSTATE_UINT32(hc_control, TSB12LV23State),
        VMSTATE_UINT32(self_id_buffer, TSB12LV23State),
        VMSTATE_UINT32(self_id_count, TSB12LV23State),
        VMSTATE_UINT32(ir_mask_hi, TSB12LV23State),
        VMSTATE_UINT32(ir_mask_lo, TSB12LV23State),
        VMSTATE_UINT32(int_event, TSB12LV23State),
        VMSTATE_UINT32(int_mask, TSB12LV23State),
        VMSTATE_UINT32(iso_tx_event, TSB12LV23State),
        VMSTATE_UINT32(iso_tx_mask, TSB12LV23State),
        VMSTATE_UINT32(iso_rx_event, TSB12LV23State),
        VMSTATE_UINT32(iso_rx_mask, TSB12LV23State),
        VMSTATE_UINT32(initial_bandwidth, TSB12LV23State),
        VMSTATE_UINT32(initial_channels_hi, TSB12LV23State),
        VMSTATE_UINT32(initial_channels_lo, TSB12LV23State),
        VMSTATE_UINT32(fairness_control, TSB12LV23State),
        VMSTATE_UINT32(link_control, TSB12LV23State),
        VMSTATE_UINT32(cycle_timer, TSB12LV23State),
        VMSTATE_UINT32(async_req_filter_hi, TSB12LV23State),
        VMSTATE_UINT32(async_req_filter_lo, TSB12LV23State),
        VMSTATE_UINT32(phy_req_filter_hi, TSB12LV23State),
        VMSTATE_UINT32(phy_req_filter_lo, TSB12LV23State),
        VMSTATE_UINT32(phy_upper_bound, TSB12LV23State),
        VMSTATE_END_OF_LIST()
    },
};

static void tsb12lv23_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = tsb12lv23_realize;
    k->vendor_id = PCI_VENDOR_ID_TI;
    k->device_id = 0x8019;
    k->revision = 0x00;
    k->class_id = PCI_CLASS_SERIAL_FIREWIRE;

    dc->desc = "Texas Instruments TSB12LV23 IEEE-1394 OHCI controller";
    dc->vmsd = &vmstate_tsb12lv23;
    device_class_set_legacy_reset(dc, tsb12lv23_reset);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo tsb12lv23_info = {
    .name = TYPE_TSB12LV23,
    .parent = TYPE_PCI_DEVICE,
    .instance_size = sizeof(TSB12LV23State),
    .class_init = tsb12lv23_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void tsb12lv23_register_types(void)
{
    type_register_static(&tsb12lv23_info);
}

type_init(tsb12lv23_register_types)
