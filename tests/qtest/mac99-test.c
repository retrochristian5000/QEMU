/*
 * Mac99 firmware reset tests.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "elf.h"
#include "qemu/bswap.h"
#include "libqtest.h"

typedef struct {
    bool elf;
    const char *machine_options;
    uint64_t reset_entry;
} FirmwareTest;

static void check_reset_entry(QTestState *qts, uint64_t expected)
{
    g_autofree char *registers = qtest_hmp(qts, "info registers");
    const char *nip = strstr(registers, "NIP ");
    char *end;
    uint64_t entry;

    g_assert_nonnull(nip);
    entry = g_ascii_strtoull(nip + 4, &end, 16);
    g_assert_true(end != nip + 4);
    g_assert_cmphex(entry, ==, expected);
}

static void test_firmware_reset(const void *opaque)
{
    const FirmwareTest *test = opaque;
    struct {
        Elf32_Ehdr ehdr;
        Elf32_Phdr phdr;
        uint8_t data[0x1000];
    } firmware = {
        .ehdr = {
            .e_ident = {
                [EI_MAG0] = ELFMAG0,
                [EI_MAG1] = ELFMAG1,
                [EI_MAG2] = ELFMAG2,
                [EI_MAG3] = ELFMAG3,
                [EI_CLASS] = ELFCLASS32,
                [EI_DATA] = ELFDATA2MSB,
                [EI_VERSION] = EV_CURRENT,
            },
            .e_type = cpu_to_be16(ET_EXEC),
            .e_machine = cpu_to_be16(EM_PPC),
            .e_version = cpu_to_be32(EV_CURRENT),
            /* An ELF entry is not necessarily a CPU reset entry. */
            .e_entry = cpu_to_be32(0xfff00800),
            .e_phoff = cpu_to_be32(sizeof(Elf32_Ehdr)),
            .e_ehsize = cpu_to_be16(sizeof(Elf32_Ehdr)),
            .e_phentsize = cpu_to_be16(sizeof(Elf32_Phdr)),
            .e_phnum = cpu_to_be16(1),
        },
        .phdr = {
            .p_type = cpu_to_be32(PT_LOAD),
            .p_offset = cpu_to_be32(sizeof(Elf32_Ehdr) + sizeof(Elf32_Phdr)),
            .p_vaddr = cpu_to_be32(0xfff00000),
            .p_paddr = cpu_to_be32(0xfff00000),
            .p_filesz = cpu_to_be32(0x1000),
            .p_memsz = cpu_to_be32(0x1000),
            .p_flags = cpu_to_be32(PF_R | PF_X),
            .p_align = cpu_to_be32(4),
        },
        .data = { 0x12, 0x34, 0x56, 0x78 },
    };
    g_autofree char *path = NULL;
    const char *contents;
    size_t size;
    QTestState *qts;
    int fd;

    fd = g_file_open_tmp("qtest-mac99-firmware-XXXXXX", &path, NULL);
    g_assert_cmpint(fd, >=, 0);
    close(fd);
    contents = test->elf ? (const char *)&firmware :
                          (const char *)firmware.data;
    size = test->elf ? sizeof(firmware) : sizeof(firmware.data);
    g_assert_true(g_file_set_contents(path, contents, size, NULL));

    /* qtest leaves the CPU stopped, so no firmware instructions execute. */
    qts = qtest_initf("-nodefaults -M mac99%s -bios '%s'",
                      test->machine_options, path);
    unlink(path);
    g_assert_cmphex(qtest_readl(qts, 0xfff00000), ==, 0x12345678);
    check_reset_entry(qts, test->reset_entry);
    qtest_system_reset(qts);
    check_reset_entry(qts, test->reset_entry);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    static const FirmwareTest elf_default = { true, "", 0xfff00100 };
    static const FirmwareTest raw_default = { false, "", 0xfff00100 };
    static const FirmwareTest elf_override = {
        true, ",firmware-entry=0xfff00200", 0xfff00200,
    };
    static const FirmwareTest raw_override = {
        false, ",firmware-entry=0xfff00200", 0xfff00200,
    };

    g_test_init(&argc, &argv, NULL);
    if (qtest_has_machine("mac99")) {
        qtest_add_data_func("mac99/firmware/elf-default", &elf_default,
                            test_firmware_reset);
        qtest_add_data_func("mac99/firmware/raw-default", &raw_default,
                            test_firmware_reset);
        qtest_add_data_func("mac99/firmware/elf-override", &elf_override,
                            test_firmware_reset);
        qtest_add_data_func("mac99/firmware/raw-override", &raw_override,
                            test_firmware_reset);
    }
    return g_test_run();
}
