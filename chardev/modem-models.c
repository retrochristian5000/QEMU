/*
 * QEMU serial modem model definitions
 *
 * Copyright 2026
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "modem-models.h"

#define MODEM_VOICE_MODEL "rockwell-voice-14400"
#define MODEM_PARADYNE_3711 "att-paradyne-dataport-3711"
#define MODEM_PARADYNE_3740 "att-paradyne-3740"

static const ModemModel modem_models[] = {
    {
        .name = "modem-generic",
        .connect_speed = 2400,
        .data_only = true,
        .identification = {
            [0] = "2400",
            [2] = "ROM NOT EMULATED",
            [3] = "QEMU generic AT-compatible data modem",
        },
        .percent_version = "QEMU generic modem",
    }, {
        .name = MODEM_DEFAULT_MODEL,
        .connect_speed = 2400,
        .supports_voice = false,
        .identification = {
            "240",
            "000",
            "ROM CHECKSUM OK",
            "Hayes Accura 2400",
            "QEMU Hayes-compatible modem",
            "V1.0",
            "RCV2400",
            "Hayes-compatible error correcting modem",
            "2400",
            "QEMU",
            "SERIAL MODEM",
        },
        .unknown_ati_response = "QEMU Hayes-compatible modem",
        .percent_version = "QEMU Hayes modem V1.0",
    },
    {
        .name = MODEM_VOICE_MODEL,
        .connect_speed = 14400,
        .supports_voice = true,
        .identification = {
            "144",
            "000",
            "ROM CHECKSUM OK",
            "Rockwell-compatible 14.4 Voice",
            "QEMU Rockwell-compatible voice modem",
            "V1.0",
            "VOICE14400",
            "Rockwell-compatible voice/fax/data modem",
            "14400",
            "QEMU",
            "VOICE MODEM",
        },
        .unknown_ati_response = "QEMU Rockwell-compatible voice modem",
        .percent_version = "QEMU Rockwell-compatible voice modem",
    },
    {
        .name = MODEM_PARADYNE_3711,
        .connect_speed = 14400,
        .paradyne_commands = true,
        .max_reliable_mode = 7,
        .identification = {
            "144",
            "000",
            "ROM NOT EMULATED",
            "Paradyne DataPort Express 3711 (QEMU emulation)",
            "QEMU Paradyne-compatible serial modem",
            "V1.0",
            "DATAPORT3711",
            "Paradyne-compatible data modem",
            "14400",
            "QEMU",
            "SERIAL MODEM",
        },
        .unknown_ati_response = "QEMU DataPort Express 3711 profile",
        .percent_version = "QEMU DataPort Express 3711 profile",
    },
    {
        .name = MODEM_PARADYNE_3740,
        .connect_speed = 28800,
        .max_fax_rate = 14400,
        .paradyne_commands = true,
        .dataport_3740_line = true,
        /* The archived DataPort Express V.34 driver requests \N7. */
        .max_reliable_mode = 7,
        /*
         * Rockwell reference product code, corroborated by HylaFAX.
         * Exact OEM firmware replies are not recovered. NULL means
         * unavailable, not a known original firmware response.
         */
        .identification = {
            [0] = "28800",
            [3] = "AT&T DataPort Express 3740 V.34 V.FC (QEMU emulation)",
        },
        .percent_version = "QEMU DataPort Express 3740 profile",
    },
};

const ModemModel *modem_model_find(const char *name)
{
    size_t i;

    /* Preserve the original command-line model spelling. */
    if (strcmp(name, "att-paradyne-dataport-3740") == 0) {
        name = MODEM_PARADYNE_3740;
    }

    for (i = 0; i < ARRAY_SIZE(modem_models); i++) {
        if (strcmp(name, modem_models[i].name) == 0) {
            return &modem_models[i];
        }
    }

    return NULL;
}
