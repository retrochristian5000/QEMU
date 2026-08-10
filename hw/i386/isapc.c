/*
 * QEMU PC System Emulator
 *
 * Copyright (c) 2003-2004 Fabrice Bellard
 *
 * SPDX-License-Identifier: MIT
 */

#include "qemu/osdep.h"

#include "qemu/units.h"
#include "qemu/error-report.h"
#include "hw/char/parallel-isa.h"
#include "hw/core/or-irq.h"
#include "hw/dma/i8257.h"
#include "hw/i386/pc.h"
#include "hw/i386/weitek4167.h"
#include "hw/ide/isa.h"
#include "hw/ide/ide-bus.h"
#include "system/kvm.h"
#include "hw/i386/kvm/clock.h"
#include "hw/xen/xen-x86.h"
#include "system/xen.h"
#include "hw/rtc/mc146818rtc.h"
#include "target/i386/cpu.h"
#include "e820_memory_layout.h"

static const int ide_iobase[MAX_IDE_BUS] = { 0x1f0, 0x170 };
static const int ide_iobase2[MAX_IDE_BUS] = { 0x3f6, 0x376 };
static const int ide_irq[MAX_IDE_BUS] = { 14, 15 };

static void pc_init_isa_common(MachineState *machine, bool with_weitek4167)
{
    PCMachineState *pcms = PC_MACHINE(machine);
    PCMachineClass *pcmc = PC_MACHINE_GET_CLASS(pcms);
    X86MachineState *x86ms = X86_MACHINE(machine);
    MemoryRegion *system_memory = get_system_memory();
    MemoryRegion *system_io = get_system_io();
    ISABus *isa_bus;
    uint32_t irq;
    GSIState *gsi_state;
    MemoryRegion *ram_memory;
    DriveInfo *hd[MAX_IDE_BUS * MAX_IDE_DEVS];
    int i;

    bool valid_cpu_type = false;
    static const char * const valid_cpu_types[] = {
        X86_CPU_TYPE_NAME("486"),
        X86_CPU_TYPE_NAME("athlon"),
        X86_CPU_TYPE_NAME("kvm32"),
        X86_CPU_TYPE_NAME("pentium"),
        X86_CPU_TYPE_NAME("pentium2"),
        X86_CPU_TYPE_NAME("pentium3"),
        X86_CPU_TYPE_NAME("qemu32"),
    };

    /*
     * The isapc machine is supposed to represent a legacy ISA-only PC with a
     * 32-bit processor. For historical reasons the machine can still accept
     * almost any valid processor, but this is now deprecated in 10.2. Emit
     * a warning if anyone tries to use a deprecated CPU.
     *
     * The Weitek 4167 variant is deliberately stricter: the coprocessor was
     * designed for the 80486 local bus, so do not silently pair it with a
     * different CPU generation.
     */
    if (with_weitek4167 &&
        strcmp(machine->cpu_type, X86_CPU_TYPE_NAME("486"))) {
        error_report("isapc-weitek requires -cpu 486");
        exit(1);
    }

    for (i = 0; i < ARRAY_SIZE(valid_cpu_types); i++) {
        if (!strcmp(machine->cpu_type, valid_cpu_types[i])) {
            valid_cpu_type = true;
        }
    }

    if (!valid_cpu_type) {
        warn_report("cpu type %s is deprecated for isapc machine",
                    machine->cpu_type);
    }

    if (with_weitek4167) {
        /*
         * Keep RAM below the coprocessor aperture. Real 486 systems could
         * remap RAM around the 0xc0000000-0xc1ffffff hole, but this machine
         * variant intentionally avoids changing the legacy isapc RAM-layout
         * code until that remapping is modeled explicitly.
         */
        if (machine->ram_size > WEITEK4167_MMIO_BASE) {
            error_report("Too much memory for isapc-weitek: %" PRId64
                         " MiB, maximum 3072 MiB",
                         machine->ram_size / MiB);
            exit(1);
        }
    } else if (machine->ram_size > 3.5 * GiB) {
        error_report("Too much memory for this machine: %" PRId64 " MiB, "
                     "maximum 3584 MiB", machine->ram_size / MiB);
        exit(1);
    }

    /*
     * There is no RAM split for the isapc machine.
     */
    if (xen_enabled()) {
        xen_hvm_init_pc(pcms, &ram_memory);
    } else {
        ram_memory = machine->ram;

        pcms->max_ram_below_4g = 3.5 * GiB;
        x86ms->above_4g_mem_size = 0;
        x86ms->below_4g_mem_size = machine->ram_size;
    }

    x86_cpus_init(x86ms, pcmc->default_cpu_version);

    if (kvm_enabled()) {
        kvmclock_create(pcmc->kvmclock_create_always);
    }

    if (with_weitek4167) {
        /* Reserve the local-bus decode aperture in the firmware memory map. */
        e820_add_entry(WEITEK4167_MMIO_BASE, WEITEK4167_MMIO_SIZE,
                       E820_RESERVED);
    }

    /* allocate ram and load rom/bios */
    if (!xen_enabled()) {
        pc_memory_init(pcms, system_memory, system_memory, 0);
    } else {
        assert(machine->ram_size == x86ms->below_4g_mem_size +
                                    x86ms->above_4g_mem_size);

        if (machine->kernel_filename != NULL) {
            /* For xen HVM direct kernel boot, load linux here */
            xen_load_linux(pcms);
        }
    }

    gsi_state = pc_gsi_create(&x86ms->gsi, false);

    isa_bus = isa_bus_new(NULL, system_memory, system_io,
                          &error_abort);
    isa_bus_register_input_irqs(isa_bus, x86ms->gsi);

    x86ms->rtc = isa_new(TYPE_MC146818_RTC);
    qdev_prop_set_int32(DEVICE(x86ms->rtc), "base_year", 2000);
    isa_realize_and_unref(x86ms->rtc, isa_bus, &error_fatal);
    irq = object_property_get_uint(OBJECT(x86ms->rtc), "irq",
                                   &error_fatal);
    isa_connect_gpio_out(ISA_DEVICE(x86ms->rtc), 0, irq);

    i8257_dma_init(OBJECT(machine), isa_bus, 0);
    pcms->hpet_enabled = false;

    if (x86ms->pic == ON_OFF_AUTO_ON || x86ms->pic == ON_OFF_AUTO_AUTO) {
        pc_i8259_create(isa_bus, gsi_state->i8259_irq);
    }

    if (with_weitek4167) {
        DeviceState *irq13_or = qdev_new(TYPE_OR_IRQ);
        DeviceState *weitek = qdev_new(TYPE_WEITEK4167);
        SysBusDevice *weitek_sbd = SYS_BUS_DEVICE(weitek);

        /* The 80486 FERR path and the 4167 INTR pin share AT IRQ13. */
        object_property_set_int(OBJECT(irq13_or), "num-lines", 2,
                                &error_abort);
        qdev_realize_and_unref(irq13_or, NULL, &error_fatal);
        qdev_connect_gpio_out(irq13_or, 0, x86ms->gsi[WEITEK4167_IRQ]);

        if (tcg_enabled()) {
            x86_register_ferr_irq(qdev_get_gpio_in(irq13_or, 0));
        }

        /*
         * The 4167 is a 32-bit local-bus memory slave, not an ISA I/O-port
         * device. Mapping the SysBus MMIO region represents M/IO#, address,
         * data, and byte-enable bus cycles; the device's realize hook exposes
         * PRES# to SeaBIOS through fw_cfg.
         */
        sysbus_realize_and_unref(weitek_sbd, &error_fatal);
        sysbus_mmio_map(weitek_sbd, 0, WEITEK4167_MMIO_BASE);
        sysbus_connect_irq(weitek_sbd, 0, qdev_get_gpio_in(irq13_or, 1));
    } else if (tcg_enabled()) {
        x86_register_ferr_irq(x86ms->gsi[13]);
    }

    pc_vga_init(isa_bus, NULL);

    /* init basic PC hardware */
    pc_basic_device_init(pcms, isa_bus, x86ms->gsi, x86ms->rtc,
                         !MACHINE_CLASS(pcmc)->no_floppy, 0x4);

    pc_nic_init(pcmc, isa_bus, NULL);

    ide_drive_get(hd, ARRAY_SIZE(hd));
    for (i = 0; i < MAX_IDE_BUS; i++) {
        ISADevice *dev;
        char busname[] = "ide.0";
        dev = isa_ide_init(isa_bus, ide_iobase[i], ide_iobase2[i],
                           ide_irq[i],
                           hd[MAX_IDE_DEVS * i], hd[MAX_IDE_DEVS * i + 1]);
        /*
         * The ide bus name is ide.0 for the first bus and ide.1 for the
         * second one.
         */
        busname[4] = '0' + i;
        pcms->idebus[i] = qdev_get_child_bus(DEVICE(dev), busname);
    }
}

static void pc_init_isa(MachineState *machine)
{
    pc_init_isa_common(machine, false);
}

static void pc_init_isa_weitek(MachineState *machine)
{
    pc_init_isa_common(machine, true);
}

static void isapc_machine_options(MachineClass *m)
{
    PCMachineClass *pcmc = PC_MACHINE_CLASS(m);

    m->desc = "ISA-only PC";
    m->max_cpus = 1;
    m->option_rom_has_mr = true;
    m->rom_file_has_mr = false;
    pcmc->pci_enabled = false;
    pcmc->has_acpi_build = false;
    pcmc->smbios_defaults = false;
    pcmc->gigabyte_align = false;
    pcmc->smbios_legacy_mode = true;
    pcmc->has_reserved_memory = false;
    m->default_nic = "ne2k_isa";
    m->default_cpu_type = X86_CPU_TYPE_NAME("486");
    m->no_floppy = !module_object_class_by_name(TYPE_ISA_FDC);
    m->no_parallel = !module_object_class_by_name(TYPE_ISA_PARALLEL);
}

static void isapc_weitek_machine_options(MachineClass *m)
{
    isapc_machine_options(m);
    m->desc = "ISA-only 486 PC with Weitek 4167 coprocessor";
}

DEFINE_PC_MACHINE(isapc, "isapc", pc_init_isa,
                  isapc_machine_options);
DEFINE_PC_MACHINE(isapc_weitek, "isapc-weitek", pc_init_isa_weitek,
                  isapc_weitek_machine_options);
