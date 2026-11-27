/* SPDX-License-Identifier: GPL-2.0-or-later */
/* CT1741 experimental firmware transport. No PCM engine is connected yet. */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/datadir.h"
#include "qemu/timer.h"
#include "hw/cpu/mcs51.h"
#include "ct1741-firmware.h"

#define CT1741_BATCH 64
#define CT1741_PERIOD_NS (64 * 1000)

struct CT1741Firmware {
    MCS51State cpu;
    uint8_t rom[8192];
    QEMUTimer *timer;
    bool reset;
    bool fault;
    bool input_ready;
    bool output_full;
    uint8_t input;
    uint8_t output;
};

static uint8_t port_read(void *opaque, unsigned int port)
{
    CT1741Firmware *s = opaque;

    return port == 1 ? (s->output_full ? 1 : 0) |
                       (s->input_ready ? 2 : 0) : 0xff;
}

static uint8_t xread(void *opaque, uint16_t addr)
{
    CT1741Firmware *s = opaque;

    if ((addr & 0xff) == 0 && s->input_ready) {
        s->input_ready = false;
        return s->input;
    }
    return 0xff;
}

static void xwrite(void *opaque, uint16_t addr, uint8_t value)
{
    CT1741Firmware *s = opaque;

    if ((addr & 0xff) == 0 && !s->output_full) {
        s->output = value;
        s->output_full = true;
    }
}

static void tick(void *opaque)
{
    CT1741Firmware *s = opaque;

    if (s->reset || s->fault) {
        return;
    }
    for (unsigned int i = 0; i < CT1741_BATCH; i++) {
        uint16_t pc = s->cpu.pc;
        if (!mcs51_step(&s->cpu)) {
            s->fault = true;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "ct1741: unsupported MCU execution at PC=0x%04x\n",
                          pc);
            return;
        }
    }
    timer_mod(s->timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              CT1741_PERIOD_NS);
}

CT1741Firmware *ct1741_fw_new(const char *filename, const char *model,
                              Error **errp)
{
    const MCS51Model *profile = mcs51_model_find(model ? model : "intel-80c52");
    g_autofree CT1741Firmware *s = NULL;
    g_autofree char *provider_rom = NULL;
    FILE *fp;
    size_t size;
    int extra;
    bool failed;

    if (!profile || profile->rom_size != 8192) {
        error_setg(errp, "ct1741: dsp-cpu must be intel-8052 or intel-80c52");
        return NULL;
    }
    /* Explicit opt-in to the default provider image. Existing explicit
     * filenames remain literal paths, and no firmware is embedded here. */
    if (!strcmp(filename, "auto")) {
        provider_rom = qemu_find_file(QEMU_FILE_TYPE_BIOS,
                                      "seabios-ct1741.bin");
        if (!provider_rom) {
            error_setg(errp, "ct1741: SeaBIOS provider ROM seabios-ct1741.bin "
                       "not found; build whp-seabios-ct1741 or supply a ROM path");
            return NULL;
        }
        filename = provider_rom;
    }
    fp = fopen(filename, "rb");
    if (!fp) {
        error_setg_errno(errp, errno, "ct1741: cannot open DSP firmware");
        return NULL;
    }
    s = g_new0(CT1741Firmware, 1);
    size = fread(s->rom, 1, sizeof(s->rom), fp);
    extra = fgetc(fp);
    failed = ferror(fp);
    fclose(fp);
    if (failed || size != sizeof(s->rom) || extra != EOF) {
        error_setg(errp, "ct1741: DSP firmware must be exactly 8192 bytes");
        return NULL;
    }
    s->cpu.model = profile;
    s->cpu.rom = s->rom;
    s->cpu.opaque = s;
    s->cpu.port_read = port_read;
    s->cpu.xread = xread;
    s->cpu.xwrite = xwrite;
    s->timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, tick, s);
    ct1741_fw_reset(s, true);
    return g_steal_pointer(&s);
}

void ct1741_fw_free(CT1741Firmware *s)
{
    if (s) {
        timer_free(s->timer);
        g_free(s);
    }
}

void ct1741_fw_reset(CT1741Firmware *s, bool asserted)
{
    if (asserted) {
        timer_del(s->timer);
        mcs51_reset(&s->cpu);
        s->input_ready = false;
        s->output_full = false;
        s->input = 0;
        s->output = 0xff;
        s->fault = false;
    } else if (s->reset) {
        timer_mod(s->timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  CT1741_PERIOD_NS);
    }
    s->reset = asserted;
}

void ct1741_fw_write(CT1741Firmware *s, uint8_t value)
{
    if (!ct1741_fw_busy(s)) {
        s->input = value;
        s->input_ready = true;
    }
}

uint8_t ct1741_fw_read(CT1741Firmware *s)
{
    if (!ct1741_fw_ready(s)) {
        return 0xff;
    }
    s->output_full = false;
    return s->output;
}

bool ct1741_fw_busy(CT1741Firmware *s)
{
    return s->reset || s->fault || s->input_ready;
}

bool ct1741_fw_ready(CT1741Firmware *s)
{
    return !s->reset && !s->fault && s->output_full;
}
