/*
 * Apple Power Mac G4 AGP (PowerMac3,1 / Sawtooth) machine profile
 *
 * This profile specializes the generic mac99 implementation with defaults
 * matching the 1999 Power Mac G4 AGP family.  It intentionally inherits the
 * mac99 device model and firmware loading path so compatibility fixes remain
 * shared between the generic and historical machine types.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qapi/error.h"
#include "qom/compat-properties.h"
#include "qom/object.h"
#include "hw/core/boards.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_host.h"
#include "hw/pci-host/uninorth.h"
#include "hw/ppc/ppc.h"
#include "system/system.h"

#define TYPE_POWERMAC3_1_MACHINE MACHINE_TYPE_NAME("powermac3_1")
#define TYPE_CORE99_MACHINE MACHINE_TYPE_NAME("mac99")

static void (*powermac3_1_parent_init)(MachineState *machine);

static PCIDevice *powermac3_1_vga_init(PCIBus *bus, VGAInterfaceType vga_type)
{
    vga_interface_created = true;

    switch (vga_type) {
    case VGA_CIRRUS:
        return pci_create_simple(bus, PCI_DEVFN(16, 0), "cirrus-vga");
    case VGA_QXL:
        return pci_create_simple(bus, PCI_DEVFN(16, 0), "qxl-vga");
    case VGA_STD:
        return pci_create_simple(bus, PCI_DEVFN(16, 0), "VGA");
    case VGA_VMWARE:
        return pci_create_simple(bus, PCI_DEVFN(16, 0), "vmware-svga");
    case VGA_VIRTIO:
        return pci_create_simple(bus, PCI_DEVFN(16, 0), "virtio-vga");
    case VGA_NONE:
    case VGA_DEVICE:
    default:
        return NULL;
    }
}

static void powermac3_1_machine_init(MachineState *machine)
{
    VGAInterfaceType requested_vga = vga_interface_type;
    Object *agp_host;
    PCIBus *agp_bus;

    /*
     * The generic mac99 initializer creates its automatic VGA device on the
     * main PCI bus.  Sawtooth instead has its display card in the UniNorth
     * AGP slot at device 0x10.  Suppress only the inherited automatic display;
     * VGA_DEVICE remains entirely under the user's explicit -device wiring.
     */
    if (requested_vga != VGA_NONE && requested_vga != VGA_DEVICE) {
        vga_interface_type = VGA_NONE;
    }

    powermac3_1_parent_init(machine);
    vga_interface_type = requested_vga;

    if (requested_vga == VGA_NONE || requested_vga == VGA_DEVICE) {
        return;
    }

    agp_host = object_resolve_type_unambiguous(
        TYPE_UNI_NORTH_AGP_HOST_BRIDGE, &error_abort);
    agp_bus = PCI_HOST_BRIDGE(agp_host)->bus;
    powermac3_1_vga_init(agp_bus, requested_vga);
}

static void powermac3_1_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    static const char * const valid_cpu_types[] = {
        POWERPC_CPU_TYPE_NAME("7400_v2.9"),
        NULL,
    };
    static GlobalProperty sawtooth_compat[] = {
        { "pci-ohci", "num-ports", "2" },
    };

    mc->desc = "Apple Power Mac G4 AGP (PowerMac3,1 / Sawtooth)";
    mc->default_cpu_type = POWERPC_CPU_TYPE_NAME("7400_v2.9");
    mc->valid_cpu_types = valid_cpu_types;
    mc->default_ram_size = 128 * MiB;

    /* KeyLargo provides two independent two-port OHCI root hubs. */
    compat_props_add(mc->compat_props, sawtooth_compat,
                     G_N_ELEMENTS(sawtooth_compat));

    /* Retain the inherited mac99 implementation and specialize its wiring. */
    powermac3_1_parent_init = mc->init;
    mc->init = powermac3_1_machine_init;
}

static void powermac3_1_instance_init(Object *obj)
{
    /*
     * A real PowerMac3,1 uses the KeyLargo PMU and USB input rather than the
     * generic mac99 CUDA/ADB default.  The parent instance has already created
     * the via property, so selecting pmu also makes the inherited board omit
     * ADB and instantiate USB keyboard and mouse devices.
     */
    object_property_set_str(obj, "via", "pmu", &error_abort);
}

static const TypeInfo powermac3_1_machine_info = {
    .name          = TYPE_POWERMAC3_1_MACHINE,
    .parent        = TYPE_CORE99_MACHINE,
    .class_init    = powermac3_1_machine_class_init,
    .instance_init = powermac3_1_instance_init,
};

static void powermac3_1_machine_register_types(void)
{
    type_register_static(&powermac3_1_machine_info);
}

type_init(powermac3_1_machine_register_types)
