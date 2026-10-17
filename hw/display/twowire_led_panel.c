/*
 * 2Wire 2701HG-B front panel: observable LED output, not an Ares GPIO model.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "hw/core/sysbus.h"
#include "hw/misc/led.h"
#include "hw/display/twowire-led-panel.h"
#include "ui/console.h"
#include "ui/pixel_ops.h"
#include "qom/object.h"

#define PANEL_WIDTH 260
#define PANEL_HEIGHT 180
#define PANEL_ROWS 5
#define PANEL_COLS 18
OBJECT_DECLARE_SIMPLE_TYPE(TwoWirePanelState, TWOWIRE_PANEL)

typedef struct PanelWatch {
    Notifier notifier;
    TwoWirePanelState *panel;
} PanelWatch;

struct TwoWirePanelState {
    SysBusDevice parent_obj;
    LEDState *lamp[TWOWIRE_LAMP_COUNT];
    PanelWatch watch[TWOWIRE_LAMP_COUNT];
    QemuConsole *console;
    bool dirty;
};

static const struct {
    const char *name;
    LEDColor color;
} lamp_desc[TWOWIRE_LAMP_COUNT] = {
    { "power-green", LED_COLOR_GREEN },
    { "power-orange", LED_COLOR_ORANGE },
    { "power-red", LED_COLOR_RED },
    { "ethernet-green", LED_COLOR_GREEN },
    { "wireless-green", LED_COLOR_GREEN },
    { "dsl-green", LED_COLOR_GREEN },
    { "internet-green", LED_COLOR_GREEN },
    { "internet-red", LED_COLOR_RED },
};
static const char *const names[PANEL_ROWS] = {
    "POWER", "ETHERNET", "WIRELESS", "DSL", "INTERNET",
};

/* Pure output priority for simultaneous logical colours; not GPIO polarity. */
static char panel_colour(TwoWirePanelState *s, int index)
{
    switch (index) {
    case 0:
        if (led_is_emitting(s->lamp[TWOWIRE_POWER_RED])) {
            return 'R';
        }
        if (led_is_emitting(s->lamp[TWOWIRE_POWER_ORANGE])) {
            return 'O';
        }
        return led_is_emitting(s->lamp[TWOWIRE_POWER_GREEN]) ? 'G' : '-';
    case 1:
        return led_is_emitting(s->lamp[TWOWIRE_ETHERNET_GREEN]) ? 'G' : '-';
    case 2:
        return led_is_emitting(s->lamp[TWOWIRE_WIRELESS_GREEN]) ? 'G' : '-';
    case 3:
        return led_is_emitting(s->lamp[TWOWIRE_DSL_GREEN]) ? 'G' : '-';
    case 4:
        if (led_is_emitting(s->lamp[TWOWIRE_INTERNET_RED])) {
            return 'R';
        }
        return led_is_emitting(s->lamp[TWOWIRE_INTERNET_GREEN]) ? 'G' : '-';
    default:
        g_assert_not_reached();
    }
}

/* Seven-row labels, drawn on the panel without a host UI or font dependency. */
typedef struct PanelLetter {
    char letter;
    uint8_t dots[7];
} PanelLetter;
static const PanelLetter letters[] = {
    { 'D', {30,17,17,17,17,17,30} },
    { 'E', {31,16,16,30,16,16,31} },
    { 'H', {17,17,17,31,17,17,17} },
    { 'I', {31,4,4,4,4,4,31} },
    { 'L', {16,16,16,16,16,16,31} },
    { 'N', {17,25,25,21,19,19,17} },
    { 'O', {14,17,17,17,17,17,14} },
    { 'P', {30,17,17,30,16,16,16} },
    { 'R', {30,17,17,30,20,18,17} },
    { 'S', {15,16,16,14,1,1,30} },
    { 'T', {31,4,4,4,4,4,4} },
    { 'W', {17,17,17,21,21,21,10} },
};

static void panel_rect(DisplaySurface *surface, int x, int y, int w, int h,
                       uint32_t pixel)
{
    for (int row = y; row < y + h; row++) {
        uint32_t *dst = (uint32_t *)(surface_data(surface) +
                                     row * surface_stride(surface));
        for (int col = x; col < x + w; col++) {
            dst[col] = pixel;
        }
    }
}

static void panel_label(DisplaySurface *surface, int x, int y,
                        const char *name)
{
    uint32_t ink = rgb_to_pixel32(212, 220, 226);

    for (int i = 0; name[i]; i++) {
        for (size_t j = 0; j < ARRAY_SIZE(letters); j++) {
            if (letters[j].letter != name[i]) {
                continue;
            }
            for (int row = 0; row < 7; row++) {
                for (int col = 0; col < 5; col++) {
                    if (letters[j].dots[row] & (1U << (4 - col))) {
                        panel_rect(surface, x + i * 12 + col * 2,
                                   y + row * 2, 2, 2, ink);
                    }
                }
            }
            break;
        }
    }
}

static void panel_invalidate(void *opaque)
{
    TwoWirePanelState *s = opaque;

    s->dirty = true;
}

static bool panel_update(void *opaque)
{
    TwoWirePanelState *s = opaque;
    DisplaySurface *surface = qemu_console_surface(s->console);

    if (!s->dirty || !surface || surface_bits_per_pixel(surface) != 32) {
        return false;
    }
    panel_rect(surface, 0, 0, PANEL_WIDTH, PANEL_HEIGHT,
               rgb_to_pixel32(20, 26, 30));
    for (int row = 0; row < PANEL_ROWS; row++) {
        int y = 8 + row * 34;
        uint32_t color;
        char state = panel_colour(s, row);

        switch (state) {
        case 'G':
            color = rgb_to_pixel32(40, 215, 98);
            break;
        case 'R':
            color = rgb_to_pixel32(232, 56, 69);
            break;
        case 'O':
            color = rgb_to_pixel32(245, 148, 28);
            break;
        default:
            color = rgb_to_pixel32(46, 53, 58);
            break;
        }
        panel_rect(surface, 7, y, PANEL_WIDTH - 14, 29,
                   rgb_to_pixel32(30, 38, 43));
        panel_label(surface, 17, y + 8, names[row]);
        panel_rect(surface, 172, y + 6, 70, 17, color);
    }

    s->dirty = false;
    qemu_console_update_full(s->console);
    return true;
}

static const GraphicHwOps panel_ops = {
    .invalidate = panel_invalidate,
    .gfx_update = panel_update,
};

static void panel_changed(Notifier *notifier, void *data)
{
    PanelWatch *watch = container_of(notifier, PanelWatch, notifier);

    watch->panel->dirty = true;
}

/* The eight inputs mean visible light emission, NOT physical Ares pins. */
static void panel_set_emission(void *opaque, int channel, int level)
{
    TwoWirePanelState *s = TWOWIRE_PANEL(opaque);

    g_assert(channel >= 0 && channel < TWOWIRE_LAMP_COUNT);
    if (s->lamp[channel]) {
        qemu_set_irq(qdev_get_gpio_in(DEVICE(s->lamp[channel]), 0), !!level);
    }
}

static void panel_init(Object *obj)
{
    qdev_init_gpio_in_named(DEVICE(obj), panel_set_emission,
                           "emission", TWOWIRE_LAMP_COUNT);
}

static void panel_realize(DeviceState *dev, Error **errp)
{
    TwoWirePanelState *s = TWOWIRE_PANEL(dev);

    for (int i = 0; i < TWOWIRE_LAMP_COUNT; i++) {
        s->lamp[i] = led_create_simple_with_reset(
            OBJECT(dev), GPIO_POLARITY_ACTIVE_HIGH, false,
            lamp_desc[i].color, lamp_desc[i].name);
        s->watch[i].panel = s;
        s->watch[i].notifier.notify = panel_changed;
        led_add_change_notifier(s->lamp[i], &s->watch[i].notifier);
    }
    s->console = qemu_graphic_console_create(dev, 0, &panel_ops, s);
    qemu_console_resize(s->console, PANEL_WIDTH, PANEL_HEIGHT);
    s->dirty = true;
}

static void panel_unrealize(DeviceState *dev)
{
    TwoWirePanelState *s = TWOWIRE_PANEL(dev);

    for (int i = 0; i < TWOWIRE_LAMP_COUNT; i++) {
        if (s->lamp[i]) {
            led_remove_change_notifier(s->lamp[i], &s->watch[i].notifier);
        }
    }
}

static void panel_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "AT&T 2Wire 2701HG-B indicator output";
    dc->realize = panel_realize;
    dc->unrealize = panel_unrealize;
}

static const TypeInfo panel_type = {
    .name = TYPE_TWOWIRE_PANEL,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(TwoWirePanelState),
    .instance_init = panel_init,
    .class_init = panel_class_init,
};

static void panel_register(void)
{
    type_register_static(&panel_type);
}
type_init(panel_register);
