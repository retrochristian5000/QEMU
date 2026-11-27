/*
 * Creative Sound Blaster 16 fixed-jumper ISA board profiles.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The CT17xx audio jumpers select the same resource set. Storage
 * controllers and optional CSP are not implemented by these profiles.
 * References: docs/system/devices/sb16.rst.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "migration/vmstate.h"
#include "sb16-legacy.h"

typedef struct SB16LegacyBoard {
    const char *type;
    const char *model;
    const char *desc;
    const char *fw_name;
    uint32_t versions[3]; /* First entry is the default DSP revision. */
    VMStateDescription vmstate;
} SB16LegacyBoard;

static const SB16LegacyBoard boards[] = {
    {
        .type = TYPE_CREATIVE_SB16,
        .model = "CT1740",
        .desc = "Creative Sound Blaster 16 CT1740 (experimental PCM and MIDI)",
        .fw_name = "creative-ct1740",
        .versions = { 0x0405 },
        .vmstate = { .name = "creative-ct1740", .unmigratable = true },
    }, {
        .type = "sb16-ct1730",
        .model = "CT1730",
        .desc = "Creative Sound Blaster 16 CT1730 (experimental PCM and MIDI)",
        .fw_name = "creative-ct1730",
        .versions = { 0x0404, 0x0405 },
        .vmstate = { .name = "creative-ct1730", .unmigratable = true },
    }, {
        .type = "sb16-ct1750",
        .model = "CT1750",
        .desc = "Creative Sound Blaster 16 MultiCD CT1750 (PCM and MIDI only)",
        .fw_name = "creative-ct1750",
        .versions = { 0x0405, 0x040b, 0x040c },
        .vmstate = { .name = "creative-ct1750", .unmigratable = true },
    }, {
        .type = "sb16-ct1770",
        .model = "CT1770",
        .desc = "Creative Sound Blaster 16 SCSI-2 CT1770 (PCM and MIDI only)",
        .fw_name = "creative-ct1770",
        .versions = { 0x0405, 0x040b, 0x040c },
        .vmstate = { .name = "creative-ct1770", .unmigratable = true },
    }, {
        .type = "sb16-ct1790",
        .model = "CT1790",
        .desc = "Creative Sound Blaster 16 Sony CT1790 (PCM and MIDI only)",
        .fw_name = "creative-ct1790",
        .versions = { 0x040b },
        .vmstate = { .name = "creative-ct1790", .unmigratable = true },
    },
};

static const SB16LegacyBoard *sb16_legacy_board(Object *obj)
{
    const char *type = object_get_typename(obj);

    for (size_t i = 0; i < ARRAY_SIZE(boards); i++) {
        if (!strcmp(type, boards[i].type)) {
            return &boards[i];
        }
    }
    return NULL;
}

const char *sb16_legacy_model(Object *obj)
{
    const SB16LegacyBoard *board = sb16_legacy_board(obj);

    return board ? board->model : NULL;
}

bool sb16_legacy_validate(Object *obj, uint32_t base, uint32_t irq,
                          uint32_t dma, uint32_t hdma, uint32_t version,
                          uint32_t mpu_base, Error **errp)
{
    const SB16LegacyBoard *board = sb16_legacy_board(obj);

    assert(board);
    if (base != 0x220 && base != 0x240 &&
        base != 0x260 && base != 0x280) {
        error_setg(errp, "sb16: %s I/O base must be 0x220, 0x240, "
                   "0x260 or 0x280", board->model);
        return false;
    }
    if (irq != 5 && irq != 7 && irq != 9 && irq != 10) {
        error_setg(errp, "sb16: %s IRQ must be 5, 7, 9 (IRQ2) or 10",
                   board->model);
        return false;
    }
    if (dma != 0 && dma != 1 && dma != 3) {
        error_setg(errp, "sb16: %s 8-bit DMA channel must be 0, 1 or 3",
                   board->model);
        return false;
    }
    if (hdma < 5 || hdma > 7) {
        error_setg(errp, "sb16: %s 16-bit DMA channel must be 5, 6 or 7",
                   board->model);
        return false;
    }
    if (mpu_base != 0x300 && mpu_base != 0x330) {
        error_setg(errp, "sb16: %s MIDI base must be 0x300 or 0x330",
                   board->model);
        return false;
    }
    for (size_t i = 0; i < ARRAY_SIZE(board->versions); i++) {
        if (board->versions[i] && board->versions[i] == version) {
            return true;
        }
    }
    error_setg(errp, "sb16: %s does not support DSP version 0x%04x",
               board->model, version);
    return false;
}

static void sb16_legacy_init(Object *obj)
{
    const SB16LegacyBoard *board = sb16_legacy_board(obj);

    assert(board);
    sb16_legacy_midi_init(obj);
    object_property_set_uint(obj, "version", board->versions[0], &error_abort);
}

static void sb16_legacy_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    const SB16LegacyBoard *board = data;

    dc->desc = board->desc;
    dc->fw_name = board->fw_name;
    dc->hotpluggable = false;
    dc->vmsd = &board->vmstate;
    sb16_legacy_add_midi_properties(dc);
}

static void sb16_legacy_register_types(void)
{
    for (size_t i = 0; i < ARRAY_SIZE(boards); i++) {
        const TypeInfo info = {
            .name = boards[i].type,
            .parent = TYPE_SB16_GENERIC,
            .instance_init = sb16_legacy_init,
            .class_init = sb16_legacy_class_init,
            .class_data = &boards[i],
        };

        type_register_static(&info);
    }
}

type_init(sb16_legacy_register_types)
