/*
 * QEMU SDL3 DisplaySurface bridge
 *
 * 2D surface integration only. Input and OpenGL remain separate migrations.
 */

#include "qemu/osdep.h"
#include "qemu/error-report.h"
#include "ui/sdl3-display.h"

SDL_PixelFormat qemu_sdl3_pixman_format(pixman_format_code_t format)
{
    switch (format) {
    case PIXMAN_x1r5g5b5:
        return SDL_PIXELFORMAT_ARGB1555;
    case PIXMAN_r5g6b5:
        return SDL_PIXELFORMAT_RGB565;
    case PIXMAN_a8r8g8b8:
    case PIXMAN_x8r8g8b8:
        return SDL_PIXELFORMAT_ARGB8888;
    case PIXMAN_a8b8g8r8:
    case PIXMAN_x8b8g8r8:
        return SDL_PIXELFORMAT_ABGR8888;
    case PIXMAN_r8g8b8a8:
    case PIXMAN_r8g8b8x8:
        return SDL_PIXELFORMAT_RGBA8888;
    case PIXMAN_b8g8r8x8:
        return SDL_PIXELFORMAT_BGRX8888;
    case PIXMAN_b8g8r8a8:
        return SDL_PIXELFORMAT_BGRA8888;
    default:
        return SDL_PIXELFORMAT_UNKNOWN;
    }
}

static bool sdl3_2d_check_format(DisplayChangeListener *dcl,
                                 pixman_format_code_t format)
{
    return qemu_sdl3_pixman_format(format) != SDL_PIXELFORMAT_UNKNOWN;
}

static void sdl3_2d_update(DisplayChangeListener *dcl,
                           int x, int y, int w, int h)
{
    QemuSDL3Console *scon = container_of(dcl, QemuSDL3Console, dcl);
    DisplaySurface *surf = scon->surface;
    SDL_Rect rect = { x, y, w, h };
    size_t surface_data_offset;
    uint8_t *pixels;

    if (!surf || w <= 0 || h <= 0) {
        return;
    }

    surface_data_offset = surface_bytes_per_pixel(surf) * x +
                          surface_stride(surf) * y;
    pixels = (uint8_t *)surface_data(surf) + surface_data_offset;

    if (!qemu_sdl3_2d_update(&scon->display2d, &rect, pixels,
                             surface_stride(surf))) {
        error_report("SDL3 2D surface update failed: %s", SDL_GetError());
    }
}

static void sdl3_2d_redraw(QemuSDL3Console *scon)
{
    if (!scon->surface) {
        return;
    }

    sdl3_2d_update(&scon->dcl, 0, 0,
                   surface_width(scon->surface),
                   surface_height(scon->surface));
}

static void sdl3_2d_switch(DisplayChangeListener *dcl,
                           DisplaySurface *new_surface)
{
    QemuSDL3Console *scon = container_of(dcl, QemuSDL3Console, dcl);
    SDL_PixelFormat format;
    int width;
    int height;

    scon->surface = new_surface;
    if (!new_surface) {
        return;
    }

    width = surface_width(new_surface);
    height = surface_height(new_surface);
    format = qemu_sdl3_pixman_format(surface_format(new_surface));
    if (format == SDL_PIXELFORMAT_UNKNOWN) {
        error_report("SDL3 2D does not support pixman format 0x%x",
                     surface_format(new_surface));
        return;
    }

    if (!qemu_sdl3_window_resize(scon->window, width, height)) {
        error_report("SDL3 window resize failed: %s", SDL_GetError());
        return;
    }

    if (!qemu_sdl3_2d_configure(&scon->display2d, format, width, height)) {
        error_report("SDL3 2D surface configure failed: %s", SDL_GetError());
        return;
    }

    sdl3_2d_redraw(scon);
}

static void sdl3_2d_refresh(DisplayChangeListener *dcl)
{
    qemu_console_hw_update(dcl->con);
}

static const DisplayChangeListenerOps sdl3_2d_ops = {
    .dpy_name = "sdl3-2d",
    .dpy_refresh = sdl3_2d_refresh,
    .dpy_gfx_update = sdl3_2d_update,
    .dpy_gfx_switch = sdl3_2d_switch,
    .dpy_gfx_check_format = sdl3_2d_check_format,
};

bool qemu_sdl3_display_2d_init(QemuSDL3Console *scon,
                               QemuConsole *con,
                               SDL_Window *window)
{
    if (!scon || !con || !window) {
        SDL_SetError("QEMU SDL3 display bridge requires console and window");
        return false;
    }

    memset(scon, 0, sizeof(*scon));
    scon->window = window;

    if (!qemu_sdl3_2d_init(&scon->display2d, window)) {
        return false;
    }

    qemu_console_register_listener(con, &scon->dcl, &sdl3_2d_ops);
    return true;
}

void qemu_sdl3_display_2d_destroy(QemuSDL3Console *scon)
{
    if (!scon) {
        return;
    }

    if (scon->dcl.ds) {
        qemu_console_unregister_listener(&scon->dcl);
    }
    qemu_sdl3_2d_destroy(&scon->display2d);
    scon->surface = NULL;
    scon->window = NULL;
}
