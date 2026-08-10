/*
 * QEMU Microsoft serial mouse emulation
 *
 * Copyright (c) 2008 Lubomir Rintel
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
#include "qemu/module.h"
#include "qemu/fifo8.h"
#include "chardev/char.h"
#include "chardev/char-serial.h"
#include "ui/console.h"
#include "ui/input.h"
#include "qom/object.h"

#define MSMOUSE_LO6(n)  ((n) & 0x3f)
#define MSMOUSE_HI2(n)  (((n) & 0xc0) >> 6)
#define MSMOUSE_PWR(cm) (cm & (CHR_TIOCM_RTS | CHR_TIOCM_DTR))

/* Serial PnP for 6 bit devices/mice sends all ASCII chars - 0x20 */
#define M(c) (c - 0x20)
/* Serial fifo size. */
#define MSMOUSE_BUF_SZ 64

/* Existing QEMU mouse ID: three-button Logitech-compatible extension. */
static const uint8_t msmouse_id[] = {'M', '3'};
/* Microsoft EasyBall uses the base Microsoft serial-mouse identification. */
static const uint8_t easyball_id[] = {'M'};

/*
 * PnP start "(", PnP version (1.0), vendor ID, product ID, '\\',
 * serial ID (omitted), '\\', MS class name, '\\', driver ID (omitted), '\\',
 * product description, checksum, ")"
 * Missing parts are inserted later.
 */
static const uint8_t msmouse_pnp_data[] = {
    M('('), 1, '$', M('Q'), M('M'), M('U'),
    M('0'), M('0'), M('0'), M('1'),
    M('\\'), M('\\'),
    M('M'), M('O'), M('U'), M('S'), M('E'),
    M('\\'), M('\\')
};

/* PNP0F1E is the Microsoft Kids Trackball / Serial EasyBall identifier. */
static const uint8_t easyball_pnp_data[] = {
    M('('), 1, '$', M('P'), M('N'), M('P'),
    M('0'), M('F'), M('1'), M('E'),
    M('\\'), M('\\'),
    M('M'), M('O'), M('U'), M('S'), M('E'),
    M('\\'), M('\\')
};

typedef struct MouseProfile {
    const uint8_t *mouse_id;
    size_t mouse_id_len;
    const uint8_t *pnp_data;
    size_t pnp_data_len;
    const char *description;
    bool right_button;
    bool middle_button;
} MouseProfile;

static const MouseProfile msmouse_profile = {
    .mouse_id = msmouse_id,
    .mouse_id_len = sizeof(msmouse_id),
    .pnp_data = msmouse_pnp_data,
    .pnp_data_len = sizeof(msmouse_pnp_data),
    .description = "QEMU Microsoft Mouse",
    .right_button = true,
    .middle_button = true,
};

static const MouseProfile easyball_profile = {
    .mouse_id = easyball_id,
    .mouse_id_len = sizeof(easyball_id),
    .pnp_data = easyball_pnp_data,
    .pnp_data_len = sizeof(easyball_pnp_data),
    .description = "Microsoft Serial EasyBall",
    .right_button = false,
    .middle_button = false,
};

struct MouseChardev {
    Chardev parent;

    const MouseProfile *profile;
    QemuInputHandlerState *hs;
    int tiocm;
    int axis[INPUT_AXIS__MAX];
    bool btns[INPUT_BUTTON__MAX];
    bool btnc[INPUT_BUTTON__MAX];
    Fifo8 outbuf;
};
typedef struct MouseChardev MouseChardev;

#define TYPE_CHARDEV_MSMOUSE "chardev-msmouse"
#define TYPE_CHARDEV_EASYBALL "chardev-easyball"
DECLARE_INSTANCE_CHECKER(MouseChardev, MOUSE_CHARDEV,
                         TYPE_CHARDEV_MSMOUSE)

static void msmouse_chr_accept_input(Chardev *chr)
{
    MouseChardev *mouse = MOUSE_CHARDEV(chr);
    uint32_t len, avail;

    len = qemu_chr_be_can_write(chr);
    avail = fifo8_num_used(&mouse->outbuf);
    while (len > 0 && avail > 0) {
        const uint8_t *buf;
        uint32_t size;

        buf = fifo8_pop_bufptr(&mouse->outbuf, MIN(len, avail), &size);
        qemu_chr_be_write(chr, buf, size);
        len = qemu_chr_be_can_write(chr);
        avail -= size;
    }
}

static void msmouse_queue_event(MouseChardev *mouse)
{
    unsigned char bytes[4] = { 0x40, 0x00, 0x00, 0x00 };
    int dx, dy, count = 3;

    dx = mouse->axis[INPUT_AXIS_X];
    mouse->axis[INPUT_AXIS_X] = 0;

    dy = mouse->axis[INPUT_AXIS_Y];
    mouse->axis[INPUT_AXIS_Y] = 0;

    /* Movement deltas */
    bytes[0] |= (MSMOUSE_HI2(dy) << 2) | MSMOUSE_HI2(dx);
    bytes[1] |= MSMOUSE_LO6(dx);
    bytes[2] |= MSMOUSE_LO6(dy);

    /* Buttons */
    bytes[0] |= (mouse->btns[INPUT_BUTTON_LEFT] ? 0x20 : 0x00);
    if (mouse->profile->right_button) {
        bytes[0] |= (mouse->btns[INPUT_BUTTON_RIGHT] ? 0x10 : 0x00);
    }
    if (mouse->profile->middle_button &&
        (mouse->btns[INPUT_BUTTON_MIDDLE] ||
         mouse->btnc[INPUT_BUTTON_MIDDLE])) {
        bytes[3] |= (mouse->btns[INPUT_BUTTON_MIDDLE] ? 0x20 : 0x00);
        mouse->btnc[INPUT_BUTTON_MIDDLE] = false;
        count++;
    }

    if (fifo8_num_free(&mouse->outbuf) >= count) {
        fifo8_push_all(&mouse->outbuf, bytes, count);
    } else {
        /* queue full -> drop event */
    }
}

static void msmouse_input_event(DeviceState *dev, QemuConsole *src,
                                QemuInputEvent *evt)
{
    MouseChardev *mouse = MOUSE_CHARDEV(dev);

    /* Ignore events if serial mouse powered down. */
    if (!MSMOUSE_PWR(mouse->tiocm)) {
        return;
    }

    switch (evt->type) {
    case INPUT_EVENT_KIND_REL:
        mouse->axis[evt->rel.axis] += evt->rel.value;
        break;

    case INPUT_EVENT_KIND_BTN:
        if ((!mouse->profile->right_button &&
             evt->btn.button == INPUT_BUTTON_RIGHT) ||
            (!mouse->profile->middle_button &&
             evt->btn.button == INPUT_BUTTON_MIDDLE)) {
            return;
        }
        mouse->btns[evt->btn.button] = evt->btn.down;
        mouse->btnc[evt->btn.button] = true;
        break;

    default:
        /* keep gcc happy */
        break;
    }
}

static void msmouse_input_sync(DeviceState *dev)
{
    MouseChardev *mouse = MOUSE_CHARDEV(dev);
    Chardev *chr = CHARDEV(dev);

    /* Ignore events if serial mouse powered down. */
    if (!MSMOUSE_PWR(mouse->tiocm)) {
        return;
    }

    msmouse_queue_event(mouse);
    msmouse_chr_accept_input(chr);
}

static int msmouse_chr_write(struct Chardev *s, const uint8_t *buf, int len)
{
    /* Ignore writes to mouse port */
    return len;
}

static const QemuInputHandler msmouse_handler = {
    .name  = "QEMU Microsoft Mouse",
    .mask  = INPUT_EVENT_MASK_BTN | INPUT_EVENT_MASK_REL,
    .event = msmouse_input_event,
    .sync  = msmouse_input_sync,
};

static void msmouse_queue_identification(MouseChardev *mouse)
{
    const MouseProfile *profile = mouse->profile;
    int c, i, j;
    uint8_t bytes[MSMOUSE_BUF_SZ / 2];
    const uint8_t hexchr[16] = {
        M('0'), M('1'), M('2'), M('3'), M('4'), M('5'), M('6'), M('7'),
        M('8'), M('9'), M('A'), M('B'), M('C'), M('D'), M('E'), M('F')
    };

    g_assert(strlen(profile->description) + 3 <= sizeof(bytes));
    g_assert(profile->mouse_id_len + profile->pnp_data_len +
             strlen(profile->description) + 3 <= MSMOUSE_BUF_SZ);

    fifo8_push_all(&mouse->outbuf, profile->mouse_id, profile->mouse_id_len);
    fifo8_push_all(&mouse->outbuf, profile->pnp_data, profile->pnp_data_len);

    c = M(')');
    for (i = 0; profile->description[i]; i++) {
        bytes[i] = M(profile->description[i]);
        c += bytes[i];
    }
    for (j = 0; j < profile->pnp_data_len; j++) {
        c += profile->pnp_data[j];
    }
    c &= 0xff;
    bytes[i++] = hexchr[c >> 4];
    bytes[i++] = hexchr[c & 0x0f];
    bytes[i++] = M(')');
    fifo8_push_all(&mouse->outbuf, bytes, i);
}

static int msmouse_chr_ioctl(Chardev *chr, int cmd, void *arg)
{
    MouseChardev *mouse = MOUSE_CHARDEV(chr);
    int c;
    int *targ = (int *)arg;

    switch (cmd) {
    case CHR_IOCTL_SERIAL_SET_TIOCM:
        c = mouse->tiocm;
        mouse->tiocm = *(int *)arg;
        if (MSMOUSE_PWR(mouse->tiocm)) {
            if (!MSMOUSE_PWR(c)) {
                /*
                 * Power on after reset: Send ID and PnP data.
                 * The profile payload is guaranteed to fit in an empty FIFO.
                 */
                msmouse_queue_identification(mouse);
                /* Start sending data to serial. */
                msmouse_chr_accept_input(chr);
            }
            break;
        }
        /*
         * Reset mouse buffers on power down.
         * Mouse won't send anything without power.
         */
        fifo8_reset(&mouse->outbuf);
        memset(mouse->axis, 0, sizeof(mouse->axis));
        memset(mouse->btns, false, sizeof(mouse->btns));
        memset(mouse->btnc, false, sizeof(mouse->btns));
        break;
    case CHR_IOCTL_SERIAL_GET_TIOCM:
        /* Remember line control status. */
        *targ = mouse->tiocm;
        break;
    default:
        return -ENOTSUP;
    }
    return 0;
}

static void char_msmouse_finalize(Object *obj)
{
    MouseChardev *mouse = MOUSE_CHARDEV(obj);

    if (mouse->hs) {
        qemu_input_handler_unregister(mouse->hs);
    }
    fifo8_destroy(&mouse->outbuf);
}

static bool msmouse_chr_open(Chardev *chr,
                             ChardevBackend *backend,
                             Error **errp)
{
    MouseChardev *mouse = MOUSE_CHARDEV(chr);

    g_assert(mouse->profile != NULL);
    mouse->hs = qemu_input_handler_register((DeviceState *)mouse,
                                            &msmouse_handler);
    mouse->tiocm = 0;
    fifo8_create(&mouse->outbuf, MSMOUSE_BUF_SZ);

    /* Never send CHR_EVENT_OPENED */
    return true;
}

static void char_msmouse_init(Object *obj)
{
    MouseChardev *mouse = MOUSE_CHARDEV(obj);

    mouse->profile = &msmouse_profile;
}

static void char_easyball_init(Object *obj)
{
    MouseChardev *mouse = MOUSE_CHARDEV(obj);

    mouse->profile = &easyball_profile;
}

static void char_msmouse_class_init(ObjectClass *oc, const void *data)
{
    ChardevClass *cc = CHARDEV_CLASS(oc);

    cc->chr_open = msmouse_chr_open;
    cc->chr_write = msmouse_chr_write;
    cc->chr_accept_input = msmouse_chr_accept_input;
    cc->chr_ioctl = msmouse_chr_ioctl;
}

static const TypeInfo char_msmouse_type_info = {
    .name = TYPE_CHARDEV_MSMOUSE,
    .parent = TYPE_CHARDEV,
    .instance_size = sizeof(MouseChardev),
    .instance_init = char_msmouse_init,
    .instance_finalize = char_msmouse_finalize,
    .class_init = char_msmouse_class_init,
};

static const TypeInfo char_easyball_type_info = {
    .name = TYPE_CHARDEV_EASYBALL,
    .parent = TYPE_CHARDEV_MSMOUSE,
    .instance_init = char_easyball_init,
};

static void register_types(void)
{
    type_register_static(&char_msmouse_type_info);
    type_register_static(&char_easyball_type_info);
}

type_init(register_types);
