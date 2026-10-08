/*
 * Creative Music System / Game Blaster (CT1300) ISA audio.
 *
 * Dual Philips SAA1099 PSGs, not a Sound Blaster DSP or an OPL2/3 device.
 * The CT1302's undocumented serial identification pattern is not emulated.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "qemu/audio.h"
#include "hw/isa/isa.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "qom/object.h"

#define TYPE_GAMEBLASTER "gameblaster"
OBJECT_DECLARE_SIMPLE_TYPE(GameBlasterState, GAMEBLASTER)

#define CMS_CLOCK 7159090U
#define CMS_RATE 44100U
#define CMS_SAMPLES 256

typedef struct CMSChip {
    uint8_t regs[32];
    uint8_t selected;
    uint8_t tone_level[6];
    uint8_t envelope_step[2];
    uint64_t tone_phase[6];
    uint64_t noise_phase[2];
    uint32_t noise_lfsr[2];
} CMSChip;

struct GameBlasterState {
    ISADevice parent_obj;
    AudioBackend *audio_be;
    SWVoiceOut *voice;
    PortioList ports;
    uint32_t iobase;
    uint8_t detect_latch;
    CMSChip chip[2];
    int16_t pending[CMS_SAMPLES * 2];
    unsigned pending_pos;
    unsigned pending_len;
};

/*
 * The SAA1099 oscillator divides its input clock by a programmable
 * half-period.  Keep phase in integer clock cycles so host audio callbacks
 * do not determine the oscillator frequency.
 */
static uint32_t cms_half_period(const CMSChip *c, unsigned voice)
{
    uint8_t packed = c->regs[0x10 + voice / 2];
    unsigned octave = (voice & 1) ? (packed >> 4) & 7 : packed & 7;

    return (511U - c->regs[0x08 + voice]) << (8 - octave);
}

static unsigned cms_envelope_level(unsigned mode, unsigned step)
{
    unsigned p = step & 63;

    switch (mode & 7) {
    case 0:
        return 0;
    case 1:
        return 15;
    case 2:
        return p < 16 ? 15 - p : 0;
    case 3:
        return 15 - (p & 15);
    case 4:
        return p < 16 ? p : p < 32 ? 31 - p : 0;
    case 5:
        return (p & 31) < 16 ? p & 15 : 31 - (p & 31);
    case 6:
        return p < 16 ? p : 0;
    default:
        return p & 15;
    }
}

static void cms_envelope_clock(CMSChip *c, unsigned group)
{
    uint8_t r = c->regs[0x18 + group];

    if (r & 0x80) {
        uint8_t step = c->envelope_step[group];

        c->envelope_step[group] = ((step + 1) & 63) | (step & 32);
    }
}

static void cms_chip_select(CMSChip *c, uint8_t value)
{
    c->selected = value & 31;
    /* Selecting an envelope register clocks externally clocked envelopes. */
    if (c->selected == 0x18 || c->selected == 0x19) {
        for (unsigned i = 0; i < 2; i++) {
            if (c->regs[0x18 + i] & 0x20) {
                cms_envelope_clock(c, i);
            }
        }
    }
}

static void cms_chip_write(CMSChip *c, uint8_t value)
{
    unsigned r = c->selected;

    if (r > 0x1c) {
        return;
    }
    c->regs[r] = value;
    if (r == 0x18 || r == 0x19) {
        c->envelope_step[r - 0x18] = 0;
    } else if (r == 0x1c && (value & 2)) {
        for (unsigned i = 0; i < 6; i++) {
            c->tone_phase[i] = 0;
            c->tone_level[i] = 0;
        }
        for (unsigned i = 0; i < 2; i++) {
            c->noise_phase[i] = 0;
        }
    }
}

/* Render one sample for a complete chip, including its two stereo outputs. */
static void cms_chip_sample(CMSChip *c, int32_t *left, int32_t *right)
{
    uint8_t noise_bit[2];

    for (unsigned i = 0; i < 6; i++) {
        uint64_t period = (uint64_t)cms_half_period(c, i) * CMS_RATE;

        c->tone_phase[i] += CMS_CLOCK;
        while (c->tone_phase[i] >= period) {
            c->tone_phase[i] -= period;
            c->tone_level[i] ^= 1;
            if ((i == 1 || i == 4) &&
                !(c->regs[0x18 + i / 3] & 0x20)) {
                cms_envelope_clock(c, i / 3);
            }
        }
    }

    for (unsigned group = 0; group < 2; group++) {
        unsigned mode = (c->regs[0x16] >> (4 * group)) & 3;
        uint32_t divider = mode == 3 ?
                           cms_half_period(c, 3 * group) : 256U << mode;
        uint64_t period = (uint64_t)divider * CMS_RATE;

        c->noise_phase[group] += CMS_CLOCK;
        while (c->noise_phase[group] >= period) {
            uint32_t bits = c->noise_lfsr[group];
            unsigned feedback = ((bits >> 17) ^ (bits >> 10)) & 1;

            c->noise_phase[group] -= period;
            c->noise_lfsr[group] = ((bits << 1) | feedback) & 0x3ffff;
        }
        noise_bit[group] = c->noise_lfsr[group] & 1;
    }

    if (!(c->regs[0x1c] & 1)) {
        return;
    }

    for (unsigned i = 0; i < 6; i++) {
        bool tone = c->regs[0x14] & (1U << i);
        bool noise = c->regs[0x15] & (1U << i);
        int level;
        uint8_t amp = c->regs[i];
        uint8_t env = c->regs[0x18 + i / 3];
        unsigned gain_l = amp & 15;
        unsigned gain_r = amp >> 4;

        if (!tone && !noise) {
            continue;
        }
        if (tone && noise) {
            level = c->tone_level[i] ? (noise_bit[i / 3] ? 2 : 1) : 0;
        } else {
            level = tone ? c->tone_level[i] * 2 : noise_bit[i / 3] * 2;
        }

        if (env & 0x80) {
            unsigned e = cms_envelope_level((env >> 1) & 7,
                                             c->envelope_step[i / 3]);

            if (env & 0x10) {
                e &= ~1U;
            }
            gain_l = (gain_l * e) / 15;
            gain_r = (gain_r * ((env & 1) ? 15 - e : e)) / 15;
        }

        /*
         * Center the unipolar chip waveform about zero for PCM output.
         * Limit each of 12 possible voices to keep the final mix in range.
         */
        *left += (level - 1) * (int)gain_l * 120;
        *right += (level - 1) * (int)gain_r * 120;
    }
}

static void cms_render(GameBlasterState *s, unsigned frames)
{
    for (unsigned n = 0; n < frames; n++) {
        int32_t left = 0;
        int32_t right = 0;

        for (unsigned chip = 0; chip < 2; chip++) {
            cms_chip_sample(&s->chip[chip], &left, &right);
        }
        s->pending[2 * n] = (int16_t)CLAMP(left, -32768, 32767);
        s->pending[2 * n + 1] = (int16_t)CLAMP(right, -32768, 32767);
    }
    s->pending_pos = 0;
    s->pending_len = frames;
}

static void cms_audio_callback(void *opaque, int free)
{
    GameBlasterState *s = opaque;

    while (free >= 4) {
        unsigned available;
        int written;

        if (s->pending_pos == s->pending_len) {
            cms_render(s, MIN((unsigned)free / 4, CMS_SAMPLES));
        }

        available = MIN(s->pending_len - s->pending_pos, (unsigned)free / 4);
        written = audio_be_write(s->audio_be, s->voice,
                                 s->pending + 2 * s->pending_pos,
                                 available * 4);
        if (written <= 0) {
            break;
        }
        s->pending_pos += written / 4;
        free -= written;
    }
}

static bool cms_enabled(const GameBlasterState *s)
{
    return (s->chip[0].regs[0x1c] | s->chip[1].regs[0x1c]) & 1;
}

static void cms_write_port(void *opaque, uint32_t addr, uint32_t value)
{
    GameBlasterState *s = opaque;
    unsigned offset = addr & 15;
    CMSChip *chip;

    switch (offset) {
    case 0:
    case 1:
    case 2:
    case 3:
        chip = &s->chip[offset >> 1];
        s->pending_pos = s->pending_len = 0;
        if (offset & 1) {
            cms_chip_select(chip, value);
        } else {
            cms_chip_write(chip, value);
        }
        audio_be_set_active_out(s->audio_be, s->voice, cms_enabled(s));
        break;
    case 6:
    case 7:
        s->detect_latch = value;
        break;
    default:
        break;
    }
}

static uint32_t cms_read_port(void *opaque, uint32_t addr)
{
    GameBlasterState *s = opaque;

    switch (addr & 15) {
    case 4:
        /* Common CMS presence byte, not full CT1302 serial-ID behavior. */
        return 0x7f;
    case 10:
    case 11:
        return s->detect_latch;
    default:
        /* The SAA1099 is write-only. */
        return 0xff;
    }
}

static const MemoryRegionPortio cms_portio[] = {
    { 0, 16, 1, .read = cms_read_port, .write = cms_write_port },
    PORTIO_END_OF_LIST(),
};

static void cms_reset(DeviceState *dev)
{
    GameBlasterState *s = GAMEBLASTER(dev);

    memset(s->chip, 0, sizeof(s->chip));
    for (unsigned i = 0; i < 2; i++) {
        s->chip[i].noise_lfsr[0] = 0x3ffff;
        s->chip[i].noise_lfsr[1] = 0x3ffff;
    }
    s->detect_latch = 0;
    s->pending_pos = s->pending_len = 0;
    if (s->voice) {
        audio_be_set_active_out(s->audio_be, s->voice, false);
    }
}

static const VMStateDescription vmstate_cms_chip = {
    .name = "gameblaster/chip",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8_ARRAY(regs, CMSChip, 32),
        VMSTATE_UINT8(selected, CMSChip),
        VMSTATE_UINT8_ARRAY(tone_level, CMSChip, 6),
        VMSTATE_UINT8_ARRAY(envelope_step, CMSChip, 2),
        VMSTATE_UINT64_ARRAY(tone_phase, CMSChip, 6),
        VMSTATE_UINT64_ARRAY(noise_phase, CMSChip, 2),
        VMSTATE_UINT32_ARRAY(noise_lfsr, CMSChip, 2),
        VMSTATE_END_OF_LIST()
    },
};

static int cms_post_load(void *opaque, int version_id)
{
    GameBlasterState *s = opaque;

    /* Never let invalid oscillator counters from a stream drive unbounded
     * catch-up loops, even when the saved registers changed period. */
    for (unsigned n = 0; n < 2; n++) {
        CMSChip *chip = &s->chip[n];

        chip->selected &= 31;
        for (unsigned i = 0; i < 6; i++) {
            uint64_t period = (uint64_t)cms_half_period(chip, i) * CMS_RATE;

            chip->tone_phase[i] %= period;
            chip->tone_level[i] &= 1;
        }
        for (unsigned i = 0; i < 2; i++) {
            unsigned mode = (chip->regs[0x16] >> (4 * i)) & 3;
            uint32_t divider = mode == 3 ?
                               cms_half_period(chip, 3 * i) : 256U << mode;

            chip->noise_phase[i] %= (uint64_t)divider * CMS_RATE;
            chip->noise_lfsr[i] &= 0x3ffff;
            chip->envelope_step[i] &= 63;
        }
    }

    s->pending_pos = s->pending_len = 0;
    audio_be_set_active_out(s->audio_be, s->voice, cms_enabled(s));
    return 0;
}

static const VMStateDescription vmstate_gameblaster = {
    .name = "gameblaster",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = cms_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(detect_latch, GameBlasterState),
        VMSTATE_STRUCT_ARRAY(chip, GameBlasterState, 2, 1,
                             vmstate_cms_chip, CMSChip),
        VMSTATE_END_OF_LIST()
    },
};

static void cms_realize(DeviceState *dev, Error **errp)
{
    GameBlasterState *s = GAMEBLASTER(dev);
    struct audsettings as = {
        .freq = CMS_RATE,
        .nchannels = 2,
        .fmt = AUDIO_FORMAT_S16,
        .big_endian = HOST_BIG_ENDIAN,
    };

    switch (s->iobase) {
    case 0x210:
    case 0x220:
    case 0x230:
    case 0x240:
    case 0x250:
    case 0x260:
        break;
    default:
        error_setg(errp, "Game Blaster I/O base must be 210, 220, 230, 240, 250 or 260 hex");
        return;
    }

    if (!audio_be_check(&s->audio_be, errp)) {
        return;
    }
    s->voice = audio_be_open_out(s->audio_be, s->voice, "gameblaster",
                                 s, cms_audio_callback, &as);
    if (!s->voice) {
        error_setg(errp, "Failed to create Game Blaster audio voice");
        return;
    }

    cms_reset(dev);
    portio_list_init(&s->ports, OBJECT(s), cms_portio, s, "gameblaster");
    portio_list_add(&s->ports, isa_address_space_io(ISA_DEVICE(dev)),
                    s->iobase);
}

static const Property cms_properties[] = {
    DEFINE_AUDIO_PROPERTIES(GameBlasterState, audio_be),
    DEFINE_PROP_UINT32("iobase", GameBlasterState, iobase, 0x220),
};

static void cms_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = cms_realize;
    device_class_set_legacy_reset(dc, cms_reset);
    dc->vmsd = &vmstate_gameblaster;
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
    dc->desc = "Creative Music System / Game Blaster (dual SAA1099)";
    device_class_set_props(dc, cms_properties);
}

static const TypeInfo cms_info = {
    .name = TYPE_GAMEBLASTER,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(GameBlasterState),
    .class_init = cms_class_init,
};

static void cms_register_types(void)
{
    type_register_static(&cms_info);
}

type_init(cms_register_types)
