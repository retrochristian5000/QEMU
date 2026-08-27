#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build-ls120-tdd"
TEST = ROOT / "tests/qtest/ide-test.c"
IDE_DEV_H = ROOT / "include/hw/ide/ide-dev.h"
IDE_DEV_C = ROOT / "hw/ide/ide-dev.c"
IDE_INTERNAL = ROOT / "hw/ide/ide-internal.h"
IDE_CORE = ROOT / "hw/ide/core.c"
ATAPI = ROOT / "hw/ide/atapi.c"
AHCI = ROOT / "hw/ide/ahci.c"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1))


def insert_before(path: Path, marker: str, addition: str) -> None:
    replace_once(path, marker, addition + marker)


def run(cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if check and result.returncode:
        raise RuntimeError(f"command failed with status {result.returncode}: {' '.join(cmd)}")
    return result


def build() -> None:
    run(["ninja", "-C", str(BUILD), "qemu-system-i386", "tests/qtest/ide-test"])


def run_ide_test(path: str | None, should_pass: bool) -> None:
    env = os.environ.copy()
    env["QTEST_QEMU_BINARY"] = str(BUILD / "qemu-system-i386")
    cmd = [str(BUILD / "tests/qtest/ide-test"), "--verbose"]
    if path:
        cmd.extend(["-p", path])
    result = run(cmd, check=False, env=env)
    if should_pass and result.returncode != 0:
        raise RuntimeError(f"expected GREEN for {path or 'full ide-test'}")
    if not should_pass and result.returncode == 0:
        raise RuntimeError(f"expected RED for {path}")
    print(f"{'GREEN' if should_pass else 'RED'} verified: {path or 'full ide-test'}", flush=True)


def apply_stage1_test() -> None:
    replace_once(
        TEST,
        "#define ATAPI_BLOCK_SIZE 2048\n",
        "#define ATAPI_BLOCK_SIZE 2048\n"
        "#define SUPERDISK_BLOCK_SIZE 512\n"
        "#define ATAPI_PACKET_SIZE 12\n",
    )
    replace_once(
        TEST,
        "    CMD_PACKET      = 0xa0,\n",
        "    CMD_PACKET      = 0xa0,\n"
        "    CMD_PIDENTIFY   = 0xa1,\n",
    )

    block = r'''
static void atapi_pio_send_cdb(QTestState *qts, QPCIDevice *dev,
                                QPCIBar ide_bar, const uint8_t *cdb,
                                uint16_t byte_count_limit)
{
    uint8_t data;
    size_t i;

    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_feature, 0);
    qpci_io_writeb(dev, ide_bar, reg_lba_middle, byte_count_limit & 0xff);
    qpci_io_writeb(dev, ide_bar, reg_lba_high, byte_count_limit >> 8);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET);

    nsleep(qts, 400);
    data = ide_wait_clear(qts, BSY);
    assert_bit_set(data, DRQ | DRDY);
    assert_bit_clear(data, ERR | DF | BSY);

    for (i = 0; i < ATAPI_PACKET_SIZE; i += 2) {
        uint16_t word;

        memcpy(&word, cdb + i, sizeof(word));
        qpci_io_writew(dev, ide_bar, reg_data, le16_to_cpu(word));
    }
}

static size_t atapi_pio_read_reply(QTestState *qts, QPCIDevice *dev,
                                   QPCIBar ide_bar, uint8_t *reply,
                                   size_t reply_size)
{
    size_t offset = 0;

    while (offset < reply_size) {
        uint16_t transfer;
        uint8_t data;
        size_t i;

        ide_wait_intr(qts, IDE_PRIMARY_IRQ);
        data = ide_wait_clear(qts, BSY);
        assert_bit_set(data, DRQ | DRDY);
        assert_bit_clear(data, ERR | DF | BSY);

        transfer = qpci_io_readb(dev, ide_bar, reg_lba_middle);
        transfer |= (uint16_t)qpci_io_readb(dev, ide_bar, reg_lba_high) << 8;
        g_assert_cmpuint(transfer, >, 0);
        g_assert_cmpuint(transfer & 1, ==, 0);
        g_assert_cmpuint(offset + transfer, <=, reply_size);

        for (i = 0; i < transfer; i += 2) {
            uint16_t word = cpu_to_le16(qpci_io_readw(dev, ide_bar, reg_data));
            memcpy(reply + offset + i, &word, sizeof(word));
        }
        offset += transfer;
    }

    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    {
        uint8_t data = ide_wait_clear(qts, BSY | DRQ);
        assert_bit_set(data, DRDY);
        assert_bit_clear(data, ERR | DF | BSY | DRQ);
    }

    return offset;
}

static void test_superdisk_identify(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint16_t identify[256];
    uint8_t inquiry[36] = { 0 };
    uint8_t cdb[ATAPI_PACKET_SIZE] = { 0 };
    uint8_t data;
    int i;

    qts = ide_test_start("-device ide-superdisk,bus=ide.0");
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PIDENTIFY);

    for (i = 0; i < ARRAY_SIZE(identify); i++) {
        data = qpci_io_readb(dev, ide_bar, reg_status);
        assert_bit_set(data, DRDY | DRQ);
        assert_bit_clear(data, BSY | DF | ERR);
        identify[i] = qpci_io_readw(dev, ide_bar, reg_data);
    }

    data = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(data, DRDY);
    assert_bit_clear(data, BSY | DF | ERR | DRQ);

    g_assert_cmphex((identify[0] >> 8) & 0x1f, ==, 0x00);
    assert_bit_set(identify[0], 1 << 7);
    g_assert_cmphex(identify[0] & 0x3, ==, 0x0);

    cdb[0] = 0x12;
    cdb[4] = sizeof(inquiry);
    atapi_pio_send_cdb(qts, dev, ide_bar, cdb, 64);
    g_assert_cmpuint(atapi_pio_read_reply(qts, dev, ide_bar,
                                          inquiry, sizeof(inquiry)),
                     ==, sizeof(inquiry));
    g_assert_cmphex(inquiry[0] & 0x1f, ==, 0x00);
    assert_bit_set(inquiry[1], 0x80);
    g_assert_cmpint(memcmp(inquiry + 8, "QEMU    ", 8), ==, 0);
    g_assert_cmpint(memcmp(inquiry + 16, "QEMU LS-120     ", 16), ==, 0);

    free_pci_device(dev);
    ide_test_quit(qts);
}

'''
    insert_before(TEST, "static void cdrom_pio_impl(int nblocks)\n", block)
    replace_once(
        TEST,
        "    qtest_add_func(\"/ide/cdrom/pio\", test_cdrom_pio);\n",
        "    qtest_add_func(\"/ide/superdisk/identify\", test_superdisk_identify);\n\n"
        "    qtest_add_func(\"/ide/cdrom/pio\", test_cdrom_pio);\n",
    )


def apply_stage1_production() -> None:
    replace_once(
        IDE_DEV_H,
        "typedef enum { IDE_HD, IDE_CD, IDE_CFATA } IDEDriveKind;\n",
        "typedef enum { IDE_HD, IDE_CD, IDE_CFATA, IDE_ATAPI_DISK } IDEDriveKind;\n\n"
        "static inline bool ide_drive_kind_is_atapi(IDEDriveKind kind)\n"
        "{\n"
        "    return kind == IDE_CD || kind == IDE_ATAPI_DISK;\n"
        "}\n",
    )

    replace_once(
        IDE_DEV_C,
        "    if (!dev->conf.blk) {\n"
        "        if (kind != IDE_CD) {\n"
        "            error_setg(errp, \"No drive specified\");\n"
        "            return;\n"
        "        } else {\n"
        "            /* Anonymous BlockBackend for an empty drive */\n"
        "            dev->conf.blk = blk_new(qemu_get_aio_context(), 0, BLK_PERM_ALL);\n"
        "            ret = blk_attach_dev(dev->conf.blk, &dev->qdev);\n"
        "            assert(ret == 0);\n"
        "        }\n"
        "    }\n",
        "    if (!dev->conf.blk) {\n"
        "        if (!ide_drive_kind_is_atapi(kind)) {\n"
        "            error_setg(errp, \"No drive specified\");\n"
        "            return;\n"
        "        } else {\n"
        "            /* Anonymous BlockBackend for an empty removable drive */\n"
        "            dev->conf.blk = blk_new(qemu_get_aio_context(), 0, BLK_PERM_ALL);\n"
        "            ret = blk_attach_dev(dev->conf.blk, &dev->qdev);\n"
        "            assert(ret == 0);\n"
        "        }\n"
        "    }\n",
    )
    replace_once(
        IDE_DEV_C,
        "    if (kind != IDE_CD) {\n"
        "        if (!blkconf_geometry(&dev->conf, &dev->chs_trans, 65535, 16, 255,\n"
        "                              errp)) {\n"
        "            return;\n"
        "        }\n"
        "    }\n"
        "    if (!blkconf_apply_backend_options(&dev->conf, kind == IDE_CD,\n"
        "                                       kind != IDE_CD, errp)) {\n",
        "    if (!ide_drive_kind_is_atapi(kind)) {\n"
        "        if (!blkconf_geometry(&dev->conf, &dev->chs_trans, 65535, 16, 255,\n"
        "                              errp)) {\n"
        "            return;\n"
        "        }\n"
        "    }\n"
        "    if (!blkconf_apply_backend_options(&dev->conf, kind == IDE_CD,\n"
        "                                       !ide_drive_kind_is_atapi(kind), errp)) {\n",
    )
    replace_once(
        IDE_DEV_C,
        "static void ide_cd_realize(IDEDevice *dev, Error **errp)\n"
        "{\n"
        "    ide_dev_initfn(dev, IDE_CD, errp);\n"
        "}\n",
        "static void ide_cd_realize(IDEDevice *dev, Error **errp)\n"
        "{\n"
        "    ide_dev_initfn(dev, IDE_CD, errp);\n"
        "}\n\n"
        "static void ide_superdisk_realize(IDEDevice *dev, Error **errp)\n"
        "{\n"
        "    ide_dev_initfn(dev, IDE_ATAPI_DISK, errp);\n"
        "}\n",
    )
    replace_once(
        IDE_DEV_C,
        "static const TypeInfo ide_cd_info = {\n"
        "    .name          = \"ide-cd\",\n"
        "    .parent        = TYPE_IDE_DEVICE,\n"
        "    .instance_size = sizeof(IDEDrive),\n"
        "    .class_init    = ide_cd_class_init,\n"
        "};\n",
        "static const TypeInfo ide_cd_info = {\n"
        "    .name          = \"ide-cd\",\n"
        "    .parent        = TYPE_IDE_DEVICE,\n"
        "    .instance_size = sizeof(IDEDrive),\n"
        "    .class_init    = ide_cd_class_init,\n"
        "};\n\n"
        "static void ide_superdisk_class_init(ObjectClass *klass, const void *data)\n"
        "{\n"
        "    DeviceClass *dc = DEVICE_CLASS(klass);\n"
        "    IDEDeviceClass *k = IDE_DEVICE_CLASS(klass);\n\n"
        "    k->realize  = ide_superdisk_realize;\n"
        "    dc->fw_name = \"drive\";\n"
        "    dc->desc    = \"virtual IDE SuperDisk\";\n"
        "    device_class_set_props(dc, ide_cd_properties);\n"
        "}\n\n"
        "static const TypeInfo ide_superdisk_info = {\n"
        "    .name          = \"ide-superdisk\",\n"
        "    .parent        = TYPE_IDE_DEVICE,\n"
        "    .instance_size = sizeof(IDEDrive),\n"
        "    .class_init    = ide_superdisk_class_init,\n"
        "};\n",
    )
    replace_once(
        IDE_DEV_C,
        "    type_register_static(&ide_hd_info);\n"
        "    type_register_static(&ide_cd_info);\n"
        "    type_register_static(&ide_device_type_info);\n",
        "    type_register_static(&ide_hd_info);\n"
        "    type_register_static(&ide_cd_info);\n"
        "    type_register_static(&ide_superdisk_info);\n"
        "    type_register_static(&ide_device_type_info);\n",
    )

    replace_once(
        IDE_CORE,
        "    /* Removable CDROM, 50us response, 12 byte packets */\n"
        "    put_le16(p + 0, (2 << 14) | (5 << 8) | (1 << 7) | (2 << 5) | (0 << 0));\n",
        "    /* Removable packet device, 50us response, 12 byte packets. */\n"
        "    put_le16(p + 0, (2 << 14) |\n"
        "             ((s->drive_kind == IDE_ATAPI_DISK ? 0 : 5) << 8) |\n"
        "             (1 << 7) | (2 << 5) | (0 << 0));\n",
    )
    replace_once(
        IDE_CORE,
        "#ifdef USE_DMA_CDROM\n"
        "    put_le16(p + 49, 1 << 9 | 1 << 8); /* DMA and LBA supported */\n"
        "    put_le16(p + 53, 7); /* words 64-70, 54-58, 88 valid */\n"
        "    put_le16(p + 62, 7);  /* single word dma0-2 supported */\n"
        "    put_le16(p + 63, 7);  /* mdma0-2 supported */\n"
        "#else\n"
        "    put_le16(p + 49, 1 << 9); /* LBA supported, no DMA */\n"
        "    put_le16(p + 53, 3); /* words 64-70, 54-58 valid */\n"
        "    put_le16(p + 63, 0x103); /* DMA modes XXX: may be incorrect */\n"
        "#endif\n",
        "#ifdef USE_DMA_CDROM\n"
        "    if (s->drive_kind == IDE_CD) {\n"
        "        put_le16(p + 49, 1 << 9 | 1 << 8); /* DMA and LBA supported */\n"
        "        put_le16(p + 53, 7); /* words 64-70, 54-58, 88 valid */\n"
        "        put_le16(p + 62, 7);  /* single word dma0-2 supported */\n"
        "        put_le16(p + 63, 7);  /* mdma0-2 supported */\n"
        "    } else {\n"
        "        put_le16(p + 49, 1 << 9); /* LBA supported, no DMA */\n"
        "        put_le16(p + 53, 3); /* words 64-70, 54-58 valid */\n"
        "    }\n"
        "#else\n"
        "    put_le16(p + 49, 1 << 9); /* LBA supported, no DMA */\n"
        "    put_le16(p + 53, 3); /* words 64-70, 54-58 valid */\n"
        "    put_le16(p + 63, 0x103); /* DMA modes XXX: may be incorrect */\n"
        "#endif\n",
    )
    replace_once(
        IDE_CORE,
        "#ifdef USE_DMA_CDROM\n"
        "    put_le16(p + 88, 0x3f | (1 << 13)); /* udma5 set and supported */\n"
        "#endif\n",
        "#ifdef USE_DMA_CDROM\n"
        "    if (s->drive_kind == IDE_CD) {\n"
        "        put_le16(p + 88, 0x3f | (1 << 13)); /* udma5 set and supported */\n"
        "    }\n"
        "#endif\n",
    )
    replace_once(IDE_CORE, "    if (s->drive_kind == IDE_CD) {\n        s->lcyl = 0x14;\n", "    if (ide_drive_kind_is_atapi(s->drive_kind)) {\n        s->lcyl = 0x14;\n")
    replace_once(IDE_CORE, "    if (s->blk && s->drive_kind != IDE_CD) {\n", "    if (s->blk && !ide_drive_kind_is_atapi(s->drive_kind)) {\n")
    replace_once(IDE_CORE, "        if (s->drive_kind == IDE_CD) {\n            ide_set_signature(s);\n", "        if (ide_drive_kind_is_atapi(s->drive_kind)) {\n            ide_set_signature(s);\n")
    replace_once(IDE_CORE, "    if (s->drive_kind == IDE_CD) {\n        ide_set_signature(s); /* odd, but ATA4 8.27.5.2 requires it */\n", "    if (ide_drive_kind_is_atapi(s->drive_kind)) {\n        ide_set_signature(s); /* odd, but ATA4 8.27.5.2 requires it */\n")
    replace_once(IDE_CORE, "    if (s->blk && s->drive_kind != IDE_CD) {\n        s->heads = (s->select & (ATA_DEV_HS)) + 1;\n", "    if (s->blk && !ide_drive_kind_is_atapi(s->drive_kind)) {\n        s->heads = (s->select & (ATA_DEV_HS)) + 1;\n")
    replace_once(IDE_CORE, "    if (s->drive_kind == IDE_CD) {\n        s->status = 0; /* ATAPI spec (v6) section 9.10 defines packet\n", "    if (ide_drive_kind_is_atapi(s->drive_kind)) {\n        s->status = 0; /* ATAPI spec (v6) section 9.10 defines packet\n")
    replace_once(
        IDE_CORE,
        "    s->status = READY_STAT | SEEK_STAT;\n"
        "    s->atapi_dma = s->feature & 1;\n",
        "    if (s->drive_kind == IDE_ATAPI_DISK && (s->feature & 1)) {\n"
        "        ide_abort_command(s);\n"
        "        return true;\n"
        "    }\n\n"
        "    s->status = READY_STAT | SEEK_STAT;\n"
        "    s->atapi_dma = s->feature & 1;\n",
    )
    replace_once(
        IDE_CORE,
        "#define HD_OK (1u << IDE_HD)\n"
        "#define CD_OK (1u << IDE_CD)\n"
        "#define CFA_OK (1u << IDE_CFATA)\n"
        "#define HD_CFA_OK (HD_OK | CFA_OK)\n"
        "#define ALL_OK (HD_OK | CD_OK | CFA_OK)\n",
        "#define HD_OK (1u << IDE_HD)\n"
        "#define CD_OK (1u << IDE_CD)\n"
        "#define CFA_OK (1u << IDE_CFATA)\n"
        "#define ATAPI_DISK_OK (1u << IDE_ATAPI_DISK)\n"
        "#define HD_CFA_OK (HD_OK | CFA_OK)\n"
        "#define ATAPI_OK (CD_OK | ATAPI_DISK_OK)\n"
        "#define ALL_OK (HD_OK | CD_OK | CFA_OK | ATAPI_DISK_OK)\n",
    )
    replace_once(IDE_CORE, "    [WIN_DEVICE_RESET]            = { cmd_device_reset, CD_OK },\n", "    [WIN_DEVICE_RESET]            = { cmd_device_reset, ATAPI_OK },\n")
    replace_once(IDE_CORE, "    [WIN_PACKETCMD]               = { cmd_packet, CD_OK },\n    [WIN_PIDENTIFY]               = { cmd_identify_packet, CD_OK },\n", "    [WIN_PACKETCMD]               = { cmd_packet, ATAPI_OK },\n    [WIN_PIDENTIFY]               = { cmd_identify_packet, ATAPI_OK },\n")
    replace_once(IDE_CORE, "        if (val != WIN_DEVICE_RESET || s->drive_kind != IDE_CD) {\n", "        if (val != WIN_DEVICE_RESET ||\n            !ide_drive_kind_is_atapi(s->drive_kind)) {\n")
    replace_once(
        IDE_CORE,
        "        /* IDE_CD uses a different set of callbacks entirely. */\n"
        "        assert(s->drive_kind != IDE_CD);\n",
        "        /* Packet devices use removable-media callbacks instead. */\n"
        "        assert(!ide_drive_kind_is_atapi(s->drive_kind));\n",
    )
    replace_once(IDE_CORE, "    if (kind == IDE_CD) {\n        blk_set_dev_ops(s->blk, &ide_cd_block_ops, s);\n", "    if (ide_drive_kind_is_atapi(kind)) {\n        blk_set_dev_ops(s->blk, &ide_cd_block_ops, s);\n")
    replace_once(
        IDE_CORE,
        "        case IDE_CD:\n"
        "            strcpy(s->drive_model_str, \"QEMU DVD-ROM\");\n"
        "            break;\n"
        "        case IDE_CFATA:\n",
        "        case IDE_CD:\n"
        "            strcpy(s->drive_model_str, \"QEMU DVD-ROM\");\n"
        "            break;\n"
        "        case IDE_ATAPI_DISK:\n"
        "            strcpy(s->drive_model_str, \"QEMU LS-120\");\n"
        "            break;\n"
        "        case IDE_CFATA:\n",
    )

    replace_once(AHCI, "    if (ide_state->drive_kind == IDE_CD) {\n", "    if (ide_drive_kind_is_atapi(ide_state->drive_kind)) {\n")

    insert_before(
        ATAPI,
        "static inline int media_present(IDEState *s)\n",
        "static inline uint8_t atapi_peripheral_device_type(IDEState *s)\n"
        "{\n"
        "    return s->drive_kind == IDE_ATAPI_DISK ? TYPE_DISK : TYPE_ROM;\n"
        "}\n\n",
    )
    replace_once(ATAPI, "        buf[idx++] = 0x05;      /* CD-ROM */\n", "        buf[idx++] = atapi_peripheral_device_type(s);\n")
    replace_once(ATAPI, "        buf[0] = 0x05; /* CD-ROM */\n", "        buf[0] = atapi_peripheral_device_type(s);\n")
    replace_once(
        ATAPI,
        "        padstr8(buf + 16, 16, \"QEMU DVD-ROM\");\n",
        "        padstr8(buf + 16, 16,\n"
        "                s->drive_kind == IDE_ATAPI_DISK ?\n"
        "                s->drive_model_str : \"QEMU DVD-ROM\");\n",
    )
    replace_once(
        ATAPI,
        "static const struct AtapiCmd {\n"
        "    void (*handler)(IDEState *s, uint8_t *buf);\n"
        "    int flags;\n"
        "} atapi_cmd_table[0x100] = {\n",
        "struct AtapiCmd {\n"
        "    void (*handler)(IDEState *s, uint8_t *buf);\n"
        "    int flags;\n"
        "};\n\n"
        "static const struct AtapiCmd atapi_cmd_table[0x100] = {\n",
    )
    insert_before(
        ATAPI,
        "void ide_atapi_cmd(IDEState *s)\n",
        "static const struct AtapiCmd superdisk_cmd_table[0x100] = {\n"
        "    [ 0x00 ] = { cmd_test_unit_ready,              CHECK_READY | NONDATA },\n"
        "    [ 0x03 ] = { cmd_request_sense,                ALLOW_UA },\n"
        "    [ 0x12 ] = { cmd_inquiry,                      ALLOW_UA },\n"
        "    [ 0x1b ] = { cmd_start_stop_unit,              NONDATA },\n"
        "    [ 0x1e ] = { cmd_prevent_allow_medium_removal, NONDATA },\n"
        "};\n\n",
    )
    replace_once(
        ATAPI,
        "    const struct AtapiCmd *cmd = &atapi_cmd_table[s->io_buffer[0]];\n",
        "    const struct AtapiCmd *table = s->drive_kind == IDE_ATAPI_DISK ?\n"
        "        superdisk_cmd_table : atapi_cmd_table;\n"
        "    const struct AtapiCmd *cmd = &table[s->io_buffer[0]];\n",
    )


def apply_stage2_test() -> None:
    block = r'''
static void test_superdisk_read_capacity(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t reply[8] = { 0 };
    uint8_t cdb[ATAPI_PACKET_SIZE] = { 0 };

    qts = ide_test_start(
        "-blockdev driver=file,node-name=sd0,filename=%s "
        "-device ide-superdisk,drive=sd0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    cdb[0] = 0x25;
    atapi_pio_send_cdb(qts, dev, ide_bar, cdb, sizeof(reply));
    g_assert_cmpuint(atapi_pio_read_reply(qts, dev, ide_bar,
                                          reply, sizeof(reply)),
                     ==, sizeof(reply));
    g_assert_cmpuint(ldl_be_p(reply), ==, TEST_IMAGE_SIZE / 512 - 1);
    g_assert_cmpuint(ldl_be_p(reply + 4), ==, SUPERDISK_BLOCK_SIZE);

    free_pci_device(dev);
    ide_test_quit(qts);
}

'''
    insert_before(TEST, "static void cdrom_pio_impl(int nblocks)\n", block)
    replace_once(
        TEST,
        "    qtest_add_func(\"/ide/superdisk/identify\", test_superdisk_identify);\n",
        "    qtest_add_func(\"/ide/superdisk/identify\", test_superdisk_identify);\n"
        "    qtest_add_func(\"/ide/superdisk/read_capacity\",\n"
        "                   test_superdisk_read_capacity);\n",
    )


def apply_stage2_production() -> None:
    replace_once(
        ATAPI,
        "static void cmd_read_cdvd_capacity(IDEState *s, uint8_t* buf)\n"
        "{\n"
        "    uint64_t total_sectors = s->nb_sectors >> 2;\n\n"
        "    /* NOTE: it is really the number of sectors minus 1 */\n"
        "    stl_be_p(buf, total_sectors - 1);\n"
        "    stl_be_p(buf + 4, 2048);\n"
        "    ide_atapi_cmd_reply(s, 8, 8);\n"
        "}\n",
        "static void cmd_read_cdvd_capacity(IDEState *s, uint8_t* buf)\n"
        "{\n"
        "    uint32_t block_size = s->drive_kind == IDE_ATAPI_DISK ? 512 : 2048;\n"
        "    uint64_t total_sectors = s->drive_kind == IDE_ATAPI_DISK ?\n"
        "        s->nb_sectors : s->nb_sectors >> 2;\n\n"
        "    /* NOTE: it is really the number of sectors minus 1 */\n"
        "    stl_be_p(buf, total_sectors - 1);\n"
        "    stl_be_p(buf + 4, block_size);\n"
        "    ide_atapi_cmd_reply(s, 8, 8);\n"
        "}\n",
    )
    replace_once(
        ATAPI,
        "    [ 0x1e ] = { cmd_prevent_allow_medium_removal, NONDATA },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
        "    [ 0x1e ] = { cmd_prevent_allow_medium_removal, NONDATA },\n"
        "    [ 0x25 ] = { cmd_read_cdvd_capacity,           CHECK_READY },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
    )


def apply_stage3_test() -> None:
    block = r'''
static void test_superdisk_read(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t pattern[SUPERDISK_BLOCK_SIZE];
    uint8_t reply[SUPERDISK_BLOCK_SIZE] = { 0 };
    uint8_t cdb[ATAPI_PACKET_SIZE] = { 0 };
    FILE *fh;
    size_t ret;
    int i;

    for (i = 0; i < sizeof(pattern); i++) {
        pattern[i] = (i * 29 + 7) & 0xff;
    }
    fh = fopen(tmp_path[0], "rb+");
    g_assert_nonnull(fh);
    g_assert_cmpint(fseek(fh, 7 * SUPERDISK_BLOCK_SIZE, SEEK_SET), ==, 0);
    ret = fwrite(pattern, 1, sizeof(pattern), fh);
    g_assert_cmpuint(ret, ==, sizeof(pattern));
    fclose(fh);

    qts = ide_test_start(
        "-blockdev driver=file,node-name=sd0,filename=%s "
        "-device ide-superdisk,drive=sd0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    cdb[0] = 0x28;
    stl_be_p(cdb + 2, 7);
    stw_be_p(cdb + 7, 1);
    atapi_pio_send_cdb(qts, dev, ide_bar, cdb, SUPERDISK_BLOCK_SIZE);
    g_assert_cmpuint(atapi_pio_read_reply(qts, dev, ide_bar,
                                          reply, sizeof(reply)),
                     ==, sizeof(reply));
    g_assert_cmpint(memcmp(pattern, reply, sizeof(pattern)), ==, 0);

    free_pci_device(dev);
    ide_test_quit(qts);
}

'''
    insert_before(TEST, "static void cdrom_pio_impl(int nblocks)\n", block)
    replace_once(
        TEST,
        "    qtest_add_func(\"/ide/superdisk/read_capacity\",\n"
        "                   test_superdisk_read_capacity);\n",
        "    qtest_add_func(\"/ide/superdisk/read_capacity\",\n"
        "                   test_superdisk_read_capacity);\n"
        "    qtest_add_func(\"/ide/superdisk/read\", test_superdisk_read);\n",
    )


def apply_stage3_production() -> None:
    replace_once(
        ATAPI,
        "static int cd_read_sector(IDEState *s)\n"
        "{\n"
        "    int et = s->elementary_transfer_size;\n"
        "    int skip = s->io_buffer_index;\n"
        "    int nsec = DIV_ROUND_UP(skip + et, s->cd_sector_size);\n\n"
        "    if (s->cd_sector_size != 2048 && s->cd_sector_size != 2352) {\n"
        "        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_READ);\n"
        "        return -EINVAL;\n"
        "    }\n\n"
        "    /* a burst is bounded by the byte count limit, so it fits io_buffer */\n"
        "    assert(nsec * s->cd_sector_size <= s->io_buffer_total_len);\n\n"
        "    /*\n"
        "     * Read the payload packed at the front of io_buffer; the 2352 raw case is\n"
        "     * unpacked into place on completion.\n"
        "     */\n"
        "    qemu_iovec_init_buf(&s->qiov, s->io_buffer, nsec * ATAPI_SECTOR_SIZE);\n\n"
        "    trace_cd_read_sector(s->lba);\n\n"
        "    block_acct_start(blk_get_stats(s->blk), &s->acct,\n"
        "                     nsec * ATAPI_SECTOR_SIZE, BLOCK_ACCT_READ);\n\n"
        "    ide_buffered_readv(s, (int64_t)s->lba << 2, &s->qiov, nsec * 4,\n"
        "                       cd_read_sector_cb, s);\n\n"
        "    s->status |= BUSY_STAT;\n"
        "    return 0;\n"
        "}\n",
        "static int cd_read_sector(IDEState *s)\n"
        "{\n"
        "    int et = s->elementary_transfer_size;\n"
        "    int skip = s->io_buffer_index;\n"
        "    int nsec = DIV_ROUND_UP(skip + et, s->cd_sector_size);\n"
        "    int backend_sector_size;\n"
        "    int backend_sectors_per_block;\n\n"
        "    if (s->cd_sector_size != 512 && s->cd_sector_size != 2048 &&\n"
        "        s->cd_sector_size != 2352) {\n"
        "        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_READ);\n"
        "        return -EINVAL;\n"
        "    }\n\n"
        "    backend_sector_size = s->cd_sector_size == 2352 ?\n"
        "        ATAPI_SECTOR_SIZE : s->cd_sector_size;\n"
        "    backend_sectors_per_block = backend_sector_size >> BDRV_SECTOR_BITS;\n\n"
        "    /* a burst is bounded by the byte count limit, so it fits io_buffer */\n"
        "    assert(nsec * s->cd_sector_size <= s->io_buffer_total_len);\n\n"
        "    /*\n"
        "     * Read the payload packed at the front of io_buffer; the 2352 raw case is\n"
        "     * unpacked into place on completion.\n"
        "     */\n"
        "    qemu_iovec_init_buf(&s->qiov, s->io_buffer,\n"
        "                        nsec * backend_sector_size);\n\n"
        "    trace_cd_read_sector(s->lba);\n\n"
        "    block_acct_start(blk_get_stats(s->blk), &s->acct,\n"
        "                     nsec * backend_sector_size, BLOCK_ACCT_READ);\n\n"
        "    ide_buffered_readv(s, (int64_t)s->lba * backend_sectors_per_block,\n"
        "                       &s->qiov, nsec * backend_sectors_per_block,\n"
        "                       cd_read_sector_cb, s);\n\n"
        "    s->status |= BUSY_STAT;\n"
        "    return 0;\n"
        "}\n",
    )
    replace_once(
        ATAPI,
        "static void ide_atapi_cmd_read_pio(IDEState *s, int lba, int nb_sectors,\n"
        "                                   int sector_size)\n"
        "{\n"
        "    assert(0 <= lba && lba < (s->nb_sectors >> 2));\n",
        "static void ide_atapi_cmd_read_pio(IDEState *s, int lba, int nb_sectors,\n"
        "                                   int sector_size)\n"
        "{\n"
        "    int backend_sector_size = sector_size == 2352 ? 2048 : sector_size;\n"
        "    int backend_sectors_per_block = backend_sector_size >> BDRV_SECTOR_BITS;\n\n"
        "    assert(0 <= lba &&\n"
        "           lba < s->nb_sectors / backend_sectors_per_block);\n",
    )
    replace_once(
        ATAPI,
        "static void cmd_read(IDEState *s, uint8_t* buf)\n"
        "{\n"
        "    unsigned int nb_sectors, lba;\n\n"
        "    /* Total logical sectors of ATAPI_SECTOR_SIZE(=2048) bytes */\n"
        "    uint64_t total_sectors = s->nb_sectors >> 2;\n",
        "static void cmd_read(IDEState *s, uint8_t* buf)\n"
        "{\n"
        "    unsigned int nb_sectors, lba;\n"
        "    int sector_size = s->drive_kind == IDE_ATAPI_DISK ? 512 : 2048;\n"
        "    uint64_t total_sectors = s->drive_kind == IDE_ATAPI_DISK ?\n"
        "        s->nb_sectors : s->nb_sectors >> 2;\n",
    )
    replace_once(ATAPI, "    ide_atapi_cmd_read(s, lba, nb_sectors, 2048);\n}\n\nstatic void cmd_read_cd", "    ide_atapi_cmd_read(s, lba, nb_sectors, sector_size);\n}\n\nstatic void cmd_read_cd")
    replace_once(
        ATAPI,
        "    [ 0x25 ] = { cmd_read_cdvd_capacity,           CHECK_READY },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
        "    [ 0x25 ] = { cmd_read_cdvd_capacity,           CHECK_READY },\n"
        "    [ 0x28 ] = { cmd_read,                         CHECK_READY },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
    )


def apply_stage4_test() -> None:
    block = r'''
static void test_superdisk_write(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t pattern[SUPERDISK_BLOCK_SIZE];
    uint8_t verify[SUPERDISK_BLOCK_SIZE] = { 0 };
    uint8_t cdb[ATAPI_PACKET_SIZE] = { 0 };
    uint8_t data;
    uint16_t transfer;
    FILE *fh;
    size_t ret;
    int i;

    for (i = 0; i < sizeof(pattern); i++) {
        pattern[i] = (i * 17 + 0x5a) & 0xff;
    }

    qts = ide_test_start(
        "-blockdev driver=file,node-name=sd0,filename=%s "
        "-device ide-superdisk,drive=sd0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    cdb[0] = 0x2a;
    stl_be_p(cdb + 2, 8);
    stw_be_p(cdb + 7, 1);
    atapi_pio_send_cdb(qts, dev, ide_bar, cdb, SUPERDISK_BLOCK_SIZE);

    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    data = ide_wait_clear(qts, BSY);
    assert_bit_set(data, DRQ | DRDY);
    assert_bit_clear(data, ERR | DF | BSY);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_nsectors), 0x02);

    transfer = qpci_io_readb(dev, ide_bar, reg_lba_middle);
    transfer |= (uint16_t)qpci_io_readb(dev, ide_bar, reg_lba_high) << 8;
    g_assert_cmpuint(transfer, ==, SUPERDISK_BLOCK_SIZE);

    for (i = 0; i < transfer; i += 2) {
        uint16_t word;
        memcpy(&word, pattern + i, sizeof(word));
        qpci_io_writew(dev, ide_bar, reg_data, le16_to_cpu(word));
    }

    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    data = ide_wait_clear(qts, BSY | DRQ);
    assert_bit_set(data, DRDY);
    assert_bit_clear(data, ERR | DF | BSY | DRQ);

    free_pci_device(dev);
    ide_test_quit(qts);

    fh = fopen(tmp_path[0], "rb");
    g_assert_nonnull(fh);
    g_assert_cmpint(fseek(fh, 8 * SUPERDISK_BLOCK_SIZE, SEEK_SET), ==, 0);
    ret = fread(verify, 1, sizeof(verify), fh);
    g_assert_cmpuint(ret, ==, sizeof(verify));
    fclose(fh);
    g_assert_cmpint(memcmp(pattern, verify, sizeof(pattern)), ==, 0);
}

'''
    insert_before(TEST, "static void cdrom_pio_impl(int nblocks)\n", block)
    replace_once(
        TEST,
        "    qtest_add_func(\"/ide/superdisk/read\", test_superdisk_read);\n",
        "    qtest_add_func(\"/ide/superdisk/read\", test_superdisk_read);\n"
        "    qtest_add_func(\"/ide/superdisk/write\", test_superdisk_write);\n",
    )


def apply_stage4_production() -> None:
    replace_once(
        IDE_INTERNAL,
        "#define ASC_INV_FIELD_IN_CMD_PACKET          0x24\n",
        "#define ASC_INV_FIELD_IN_CMD_PACKET          0x24\n"
        "#define ASC_WRITE_PROTECTED                  0x27\n",
    )
    insert_before(
        IDE_INTERNAL,
        "void ide_atapi_cmd(IDEState *s);\n",
        "void ide_atapi_cmd_write_end(IDEState *s);\n",
    )

    replace_once(
        IDE_CORE,
        "    if (s->end_transfer_func == ide_sector_write ||\n"
        "        s->end_transfer_func == ide_atapi_cmd) {\n",
        "    if (s->end_transfer_func == ide_sector_write ||\n"
        "        s->end_transfer_func == ide_atapi_cmd ||\n"
        "        s->end_transfer_func == ide_atapi_cmd_write_end) {\n",
    )
    replace_once(
        IDE_CORE,
        "        ide_atapi_cmd,\n"
        "        ide_dummy_transfer_stop,\n"
        "};\n",
        "        ide_atapi_cmd,\n"
        "        ide_dummy_transfer_stop,\n"
        "        ide_atapi_cmd_write_end,\n"
        "};\n",
    )

    block = r'''
static void ide_atapi_cmd_write_pio_next(IDEState *s);

static void ide_atapi_cmd_write_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int transferred = s->elementary_transfer_size;

    s->pio_aiocb = NULL;
    s->status &= ~BUSY_STAT;

    if (ret < 0) {
        block_acct_failed(blk_get_stats(s->blk), &s->acct);
        ide_atapi_io_error(s, ret);
        return;
    }

    block_acct_done(blk_get_stats(s->blk), &s->acct);
    s->lba += transferred >> BDRV_SECTOR_BITS;
    s->packet_transfer_size -= transferred;
    s->elementary_transfer_size = 0;

    if (s->packet_transfer_size == 0) {
        ide_atapi_cmd_ok(s);
        return;
    }

    ide_atapi_cmd_write_pio_next(s);
}

void ide_atapi_cmd_write_end(IDEState *s)
{
    int size = s->elementary_transfer_size;

    assert(size > 0);
    assert(QEMU_IS_ALIGNED(size, BDRV_SECTOR_SIZE));

    qemu_iovec_init_buf(&s->qiov, s->io_buffer, size);
    block_acct_start(blk_get_stats(s->blk), &s->acct,
                     size, BLOCK_ACCT_WRITE);
    s->status |= BUSY_STAT;
    s->pio_aiocb = blk_aio_pwritev(s->blk,
                                   (int64_t)s->lba << BDRV_SECTOR_BITS,
                                   &s->qiov, 0, ide_atapi_cmd_write_cb, s);
}

static void ide_atapi_cmd_write_pio_next(IDEState *s)
{
    int byte_count_limit = atapi_byte_count_limit(s);
    int size = MIN(s->packet_transfer_size, byte_count_limit);

    size = MIN(size, s->io_buffer_total_len);
    size &= ~(BDRV_SECTOR_SIZE - 1);
    if (!size) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_DATA_PHASE_ERROR);
        return;
    }

    s->elementary_transfer_size = size;
    s->nsector &= ~7;
    s->lcyl = size & 0xff;
    s->hcyl = size >> 8;
    s->status = READY_STAT | SEEK_STAT;
    ide_transfer_start(s, s->io_buffer, size, ide_atapi_cmd_write_end);
    ide_bus_set_irq(s->bus);
}

static void cmd_write(IDEState *s, uint8_t *buf)
{
    uint32_t lba = ldl_be_p(buf + 2);
    uint32_t nb_sectors = lduw_be_p(buf + 7);

    if (nb_sectors == 0) {
        ide_atapi_cmd_ok(s);
        return;
    }

    if (!blk_is_writable(s->blk)) {
        ide_atapi_cmd_error(s, DATA_PROTECT, ASC_WRITE_PROTECTED);
        return;
    }

    if (lba >= s->nb_sectors || nb_sectors > s->nb_sectors - lba) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_LOGICAL_BLOCK_OOR);
        return;
    }

    s->lba = lba;
    s->packet_transfer_size = nb_sectors << BDRV_SECTOR_BITS;
    s->elementary_transfer_size = 0;
    s->io_buffer_index = 0;
    s->cd_sector_size = BDRV_SECTOR_SIZE;
    ide_atapi_cmd_write_pio_next(s);
}

'''
    insert_before(ATAPI, "static void cmd_read_cd(IDEState *s, uint8_t* buf)\n", block)
    replace_once(
        ATAPI,
        "    [ 0x28 ] = { cmd_read,                         CHECK_READY },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
        "    [ 0x28 ] = { cmd_read,                         CHECK_READY },\n"
        "    [ 0x2a ] = { cmd_write,                        CHECK_READY },\n"
        "};\n\n"
        "void ide_atapi_cmd(IDEState *s)\n",
    )


def main() -> int:
    os.chdir(ROOT)
    if BUILD.exists():
        shutil.rmtree(BUILD)

    print("=== Stage 1 RED: removable ATAPI identity ===", flush=True)
    apply_stage1_test()
    run([
        "./configure",
        f"--prefix={ROOT / 'ls120-prefix'}",
        "--target-list=i386-softmmu",
        "--disable-docs",
        "--disable-werror",
        f"--meson=meson",
    ])
    # configure chooses its default build directory only when run there; use
    # the supported out-of-tree invocation instead.
    if not BUILD.exists():
        raise RuntimeError("configure did not create build directory")

    build()
    run_ide_test("/ide/superdisk/identify", should_pass=False)

    print("=== Stage 1 GREEN: device and direct-access identity ===", flush=True)
    apply_stage1_production()
    build()
    run_ide_test("/ide/superdisk/identify", should_pass=True)

    print("=== Stage 2 RED: 512-byte READ CAPACITY ===", flush=True)
    apply_stage2_test()
    build()
    run_ide_test("/ide/superdisk/read_capacity", should_pass=False)

    print("=== Stage 2 GREEN: 512-byte READ CAPACITY ===", flush=True)
    apply_stage2_production()
    build()
    run_ide_test("/ide/superdisk/read_capacity", should_pass=True)

    print("=== Stage 3 RED: 512-byte READ(10) ===", flush=True)
    apply_stage3_test()
    build()
    run_ide_test("/ide/superdisk/read", should_pass=False)

    print("=== Stage 3 GREEN: 512-byte READ(10) ===", flush=True)
    apply_stage3_production()
    build()
    run_ide_test("/ide/superdisk/read", should_pass=True)

    print("=== Stage 4 RED: 512-byte WRITE(10) ===", flush=True)
    apply_stage4_test()
    build()
    run_ide_test("/ide/superdisk/write", should_pass=False)

    print("=== Stage 4 GREEN: 512-byte WRITE(10) ===", flush=True)
    apply_stage4_production()
    build()
    run_ide_test("/ide/superdisk/write", should_pass=True)

    print("=== Regression verification ===", flush=True)
    run(["git", "diff", "--check"])
    run_ide_test("/ide/cdrom/pio", should_pass=True)
    run_ide_test(None, should_pass=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ls120-tdd: {exc}", file=sys.stderr)
        raise
