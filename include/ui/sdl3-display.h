#ifndef QEMU_UI_SDL3_DISPLAY_H
#define QEMU_UI_SDL3_DISPLAY_H

#include "ui/console.h"
#include "ui/sdl3-2d.h"
#include "ui/sdl3-core.h"

typedef struct QemuSDL3Console {
    DisplayChangeListener dcl;
    DisplaySurface *surface;
    SDL_Window *window;
    QemuSDL3Display2D display2d;
} QemuSDL3Console;

SDL_PixelFormat qemu_sdl3_pixman_format(pixman_format_code_t format);
bool qemu_sdl3_display_2d_init(QemuSDL3Console *scon,
                               QemuConsole *con,
                               SDL_Window *window);
void qemu_sdl3_display_2d_destroy(QemuSDL3Console *scon);

#endif /* QEMU_UI_SDL3_DISPLAY_H */
