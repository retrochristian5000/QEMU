/*
 * Generic original 16-bit x86 machines.
 *
 * Copyright (c) 2026 Vincent Menezes
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qemu/datadir.h"
#include "qemu/error-report.h"
#include "qemu/units.h"
#include "qapi/error.h"
#include "system/cpus.h"
#include "system/memory.h"
#include "system/qtest.h"

#include "hw/char/serial-isa.h"
#include "hw/core/irq.h"
#include "hw/core/loader.h"
#include "hw/i386/x86.h"
#include "hw/isa/isa.h"
#include "target/i386/cpu.h"

#define TYPE_X86_8086_MACHINE MACHINE_TYPE_NAME("x86-8086")
#define TYPE_X86_8088_MACHINE MACHINE_TYPE_NAME("x86-8088")

#define X86_16BIT_RAM_SIZE (640 * KiB)
#define X86_16BIT_ROM_BASE 0xf0000
#define X86_16BIT_ROM_SIZE (64 * KiB)

static const char * const x86_8086_valid_cpu_types[] = {
    X86_CPU_TYPE_NAME("8086"),
    NULL,
};

static const char * const x86_8088_valid_cpu_types[] = {
    X86_CPU_TYPE_NAME("8088"),
    NULL,
};

static void x86_16bit_ignore_irq(void *opaque, int irq, int level)
{
}

static void x86_16bit_load_bios(X86MachineState *x86ms,
                                MachineState *machine)
{
    g_autofree char *filename = NULL;
    uint8_t *rom;
    int64_t size;

    if (!machine->firmware) {
        error_report("The %s machine requires -bios FILE",
                     MACHINE_GET_CLASS(machine)->name);
        exit(EXIT_FAILURE);
    }

    filename = qemu_find_file(QEMU_FILE_TYPE_BIOS, machine->firmware);
    if (!filename) {
        error_report("Could not find BIOS image '%s'", machine->firmware);
        exit(EXIT_FAILURE);
    }

    size = get_image_size(filename, &error_fatal);
    if (size > X86_16BIT_ROM_SIZE) {
        error_report("BIOS image '%s' is larger than 64 KiB", filename);
        exit(EXIT_FAILURE);
    }

    memory_region_init_rom(&x86ms->bios, OBJECT(machine),
                           "x86-16bit.bios", X86_16BIT_ROM_SIZE,
                           &error_fatal);
    rom = memory_region_get_ram_ptr(&x86ms->bios);
    memset(rom, 0xff, X86_16BIT_ROM_SIZE);
    if (load_image_size(filename, rom + X86_16BIT_ROM_SIZE - size,
                        size) != size) {
        error_report("Could not load BIOS image '%s'", filename);
        exit(EXIT_FAILURE);
    }

    memory_region_add_subregion(get_system_memory(), X86_16BIT_ROM_BASE,
                                &x86ms->bios);
}

static void x86_16bit_create_cpu(MachineState *machine)
{
    Object *cpu = object_new(machine->cpu_type);

    object_property_set_uint(cpu, "apic-id", 0, &error_fatal);
    qdev_realize(DEVICE(cpu), NULL, &error_fatal);
    object_unref(cpu);
}

static void x86_16bit_machine_init(MachineState *machine)
{
    X86MachineState *x86ms = X86_MACHINE(machine);
    ISABus *isa_bus;

    if (!tcg_enabled() && !qtest_enabled()) {
        error_report("The %s machine supports only the TCG accelerator",
                     MACHINE_GET_CLASS(machine)->name);
        exit(EXIT_FAILURE);
    }
    if (machine->ram_size > X86_16BIT_RAM_SIZE) {
        error_report("The %s machine supports at most 640 KiB of RAM",
                     MACHINE_GET_CLASS(machine)->name);
        exit(EXIT_FAILURE);
    }

    memory_region_add_subregion(get_system_memory(), 0, machine->ram);
    x86_16bit_load_bios(x86ms, machine);
    x86_16bit_create_cpu(machine);

    x86ms->gsi = qemu_allocate_irqs(x86_16bit_ignore_irq, NULL,
                                    ISA_NUM_IRQS);
    isa_bus = isa_bus_new(NULL, get_system_memory(), get_system_io(),
                          &error_fatal);
    isa_bus_register_input_irqs(isa_bus, x86ms->gsi);
    serial_hds_isa_init(isa_bus, 0, 1);
}

static void x86_16bit_machine_class_init(MachineClass *mc)
{
    mc->desc = "Generic original 16-bit x86 machine";
    mc->init = x86_16bit_machine_init;
    mc->max_cpus = 1;
    mc->default_ram_size = X86_16BIT_RAM_SIZE;
    mc->default_ram_id = "x86-16bit.ram";
    mc->no_floppy = true;
    mc->no_cdrom = true;
    mc->no_parallel = true;
}

static void x86_8086_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);

    x86_16bit_machine_class_init(mc);
    mc->desc = "Generic Intel 8086 machine (16-bit external data bus)";
    mc->default_cpu_type = X86_CPU_TYPE_NAME("8086");
    mc->valid_cpu_types = x86_8086_valid_cpu_types;
    mc->is_default = true;
}

static void x86_8088_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);

    x86_16bit_machine_class_init(mc);
    mc->desc = "Generic Intel 8088 machine (8-bit external data bus)";
    mc->default_cpu_type = X86_CPU_TYPE_NAME("8088");
    mc->valid_cpu_types = x86_8088_valid_cpu_types;
}

static const TypeInfo x86_8086_machine_type = {
    .name = TYPE_X86_8086_MACHINE,
    .parent = TYPE_X86_MACHINE,
    .class_init = x86_8086_machine_class_init,
};

static const TypeInfo x86_8088_machine_type = {
    .name = TYPE_X86_8088_MACHINE,
    .parent = TYPE_X86_MACHINE,
    .class_init = x86_8088_machine_class_init,
};

static void x86_16bit_machine_register_types(void)
{
    type_register_static(&x86_8086_machine_type);
    type_register_static(&x86_8088_machine_type);
}

type_init(x86_16bit_machine_register_types)
