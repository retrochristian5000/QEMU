/*
 * QEMU Sun serial keyboard and mouse protocols for ESCC
 *
 * Copyright (c) 2003-2005 Fabrice Bellard
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
#include "qemu/cutils.h"
#include "standard-headers/linux/input-event-codes.h"
#include "ui/console.h"
#include "escc-internal.h"
#include "trace.h"

/*
 * Sun keyboard commands and Mouse Systems packets use the ESCC channel
 * transport, not PS/2 or the generic UART's register implementation.
 */

static void sunkbd_handle_event(DeviceState *dev, QemuConsole *src,
                                QemuInputEvent *evt)
{
    ESCCChannelState *s = (ESCCChannelState *)dev;
    int qcode, keycode;

    assert(evt->type == INPUT_EVENT_KIND_KEY);
    qcode = qemu_input_linux_to_qcode(evt->key.key);
    trace_escc_sunkbd_event_in(qcode, QKeyCode_str(qcode),
                               evt->key.down);

    if (evt->key.key == KEY_CAPSLOCK) {
        if (evt->key.down) {
            s->caps_lock_mode ^= 1;
            if (s->caps_lock_mode == 2) {
                return; /* Drop second press */
            }
        } else {
            s->caps_lock_mode ^= 2;
            if (s->caps_lock_mode == 3) {
                return; /* Drop first release */
            }
        }
    }

    if (evt->key.key == KEY_NUMLOCK) {
        if (evt->key.down) {
            s->num_lock_mode ^= 1;
            if (s->num_lock_mode == 2) {
                return; /* Drop second press */
            }
        } else {
            s->num_lock_mode ^= 2;
            if (s->num_lock_mode == 3) {
                return; /* Drop first release */
            }
        }
    }

    if (evt->key.key >= qemu_input_map_linux_to_sun_len) {
        return;
    }

    keycode = qemu_input_map_linux_to_sun[evt->key.key];
    if (!evt->key.down) {
        keycode |= 0x80;
    }
    trace_escc_sunkbd_event_out(keycode);
    escc_queue_put(s, keycode);
}

const QemuInputHandler escc_sunkbd_handler = {
    .name  = "sun keyboard",
    .mask  = INPUT_EVENT_MASK_KEY,
    .event = sunkbd_handle_event,
};

static uint8_t sunkbd_layout_dip_switch(const char *kbd_layout)
{
    /* Return the value of the dip-switches in a SUN Type 5 keyboard */
    static uint8_t ret = 0xff;

    if ((ret == 0xff) && kbd_layout) {
        int i;
        struct layout_values {
            const char *lang;
            uint8_t dip;
        } languages[] =
            /*
             * Dip values from table 3-16 Layouts for Type 4, 5 and 5c Keyboards
             */
            {
                {"en-us", 0x21}, /* U.S.A. (US5.kt) */
                                 /* 0x22 is some other US (US_UNIX5.kt) */
                {"fr",    0x23}, /* France (France5.kt) */
                {"da",    0x24}, /* Denmark (Denmark5.kt) */
                {"de",    0x25}, /* Germany (Germany5.kt) */
                {"it",    0x26}, /* Italy (Italy5.kt) */
                {"nl",    0x27}, /* The Netherlands (Netherland5.kt) */
                {"no",    0x28}, /* Norway (Norway.kt) */
                {"pt",    0x29}, /* Portugal (Portugal5.kt) */
                {"es",    0x2a}, /* Spain (Spain5.kt) */
                {"sv",    0x2b}, /* Sweden (Sweden5.kt) */
                {"fr-ch", 0x2c}, /* Switzerland/French (Switzer_Fr5.kt) */
                {"de-ch", 0x2d}, /* Switzerland/German (Switzer_Ge5.kt) */
                {"en-gb", 0x2e}, /* Great Britain (UK5.kt) */
                {"ko",    0x2f}, /* Korea (Korea5.kt) */
                {"tw",    0x30}, /* Taiwan (Taiwan5.kt) */
                {"ja",    0x31}, /* Japan (Japan5.kt) */
                {"fr-ca", 0x32}, /* Canada/French (Canada_Fr5.kt) */
                {"hu",    0x33}, /* Hungary (Hungary5.kt) */
                {"pl",    0x34}, /* Poland (Poland5.kt) */
                {"cz",    0x35}, /* Czech (Czech5.kt) */
                {"ru",    0x36}, /* Russia (Russia5.kt) */
                {"lv",    0x37}, /* Latvia (Latvia5.kt) */
                {"tr",    0x38}, /* Turkey-Q5 (TurkeyQ5.kt) */
                {"gr",    0x39}, /* Greece (Greece5.kt) */
                {"ar",    0x3a}, /* Arabic (Arabic5.kt) */
                {"lt",    0x3b}, /* Lithuania (Lithuania5.kt) */
                {"nl-be", 0x3c}, /* Belgium (Belgian5.kt) */
                {"be",    0x3c}, /* Belgium (Belgian5.kt) */
            };

        for (i = 0;
             i < sizeof(languages) / sizeof(struct layout_values);
             i++) {
            if (!strcmp(kbd_layout, languages[i].lang)) {
                ret = languages[i].dip;
                return ret;
            }
        }

        /* Found no known language code */
        if ((kbd_layout[0] >= '0') && (kbd_layout[0] <= '9')) {
            unsigned int tmp;

            /* As a fallback we also accept numeric dip switch value */
            if (!qemu_strtoui(kbd_layout, NULL, 0, &tmp)) {
                ret = tmp;
            }
        }
    }

    if (ret == 0xff) {
        /* Final fallback if keyboard_layout was not set or recognized */
        ret = 0x21; /* en-us layout */
    }
    return ret;
}

void escc_sunkbd_command(ESCCChannelState *s, int val)
{
    trace_escc_kbd_command(val);
    if (s->led_mode) { /* Ignore led byte */
        s->led_mode = 0;
        return;
    }
    switch (val) {
    case 1: /* Reset, return type code */
        escc_queue_clear(s);
        escc_queue_put(s, 0xff);
        escc_queue_put(s, 4); /* Type 4 */
        escc_queue_put(s, 0x7f);
        break;
    case 0xe: /* Set leds */
        s->led_mode = 1;
        break;
    case 7: /* Query layout */
    case 0xf:
        escc_queue_clear(s);
        escc_queue_put(s, 0xfe);
        escc_queue_put(s, sunkbd_layout_dip_switch(s->sunkbd_layout));
        break;
    default:
        break;
    }
}

static void sunmouse_handle_event(DeviceState *dev, QemuConsole *src,
                                  QemuInputEvent *evt)
{
    ESCCChannelState *s = (ESCCChannelState *)dev;
    static const int bmap[INPUT_BUTTON__MAX] = {
        [INPUT_BUTTON_LEFT]   = 0x4,
        [INPUT_BUTTON_MIDDLE] = 0x2,
        [INPUT_BUTTON_RIGHT]  = 0x1,
    };

    switch (evt->type) {
    case INPUT_EVENT_KIND_REL:
        if (evt->rel.axis == INPUT_AXIS_X) {
            s->sunmouse_dx += evt->rel.value;
        } else if (evt->rel.axis == INPUT_AXIS_Y) {
            s->sunmouse_dy -= evt->rel.value;
        }
        break;

    case INPUT_EVENT_KIND_BTN:
        if (bmap[evt->btn.button]) {
            if (evt->btn.down) {
                s->sunmouse_buttons |= bmap[evt->btn.button];
            } else {
                s->sunmouse_buttons &= ~bmap[evt->btn.button];
            }
            /* Indicate we have a supported button event */
            s->sunmouse_buttons |= 0x80;
        }
        break;

    default:
        /* keep gcc happy */
        break;
    }
}

static void sunmouse_sync(DeviceState *dev)
{
    ESCCChannelState *s = (ESCCChannelState *)dev;
    int ch;

    if (s->sunmouse_dx == 0 && s->sunmouse_dy == 0 &&
        (s->sunmouse_buttons & 0x80) == 0) {
            /* Nothing to do after button event filter */
            return;
    }

    /* Clear our button event flag */
    s->sunmouse_buttons &= ~0x80;
    trace_escc_sunmouse_event(s->sunmouse_dx, s->sunmouse_dy,
                              s->sunmouse_buttons);
    ch = 0x80 | 0x7; /* protocol start byte, no buttons pressed */
    ch ^= s->sunmouse_buttons;
    escc_queue_put(s, ch);

    ch = s->sunmouse_dx;
    if (ch > 127) {
        ch = 127;
    } else if (ch < -127) {
        ch = -127;
    }
    escc_queue_put(s, ch & 0xff);
    s->sunmouse_dx -= ch;

    ch = s->sunmouse_dy;
    if (ch > 127) {
        ch = 127;
    } else if (ch < -127) {
        ch = -127;
    }
    escc_queue_put(s, ch & 0xff);
    s->sunmouse_dy -= ch;

    /* MSC protocol specifies two extra motion bytes */
    escc_queue_put(s, 0);
    escc_queue_put(s, 0);
}

const QemuInputHandler escc_sunmouse_handler = {
    .name  = "QEMU Sun Mouse",
    .mask  = INPUT_EVENT_MASK_BTN | INPUT_EVENT_MASK_REL,
    .event = sunmouse_handle_event,
    .sync  = sunmouse_sync,
};
