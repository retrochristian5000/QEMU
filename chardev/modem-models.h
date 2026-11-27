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

#ifndef QEMU_CHARDEV_MODEM_MODELS_H
#define QEMU_CHARDEV_MODEM_MODELS_H

#define MODEM_DEFAULT_MODEL "hayes-accura-2400"

typedef struct ModemModel {
    const char *name;
    int connect_speed;
    int max_fax_rate; /* Separate from the data DCE rate. */
    bool supports_voice;
    bool paradyne_commands;
    bool dataport_3740_line;
    int max_reliable_mode;
    const char *identification[11];
    const char *unknown_ati_response;
    const char *percent_version;
} ModemModel;

/* Immutable model identity and capabilities, independent of AT parsing. */
const ModemModel *modem_model_find(const char *name);

#endif
