#ifndef QEMU_UI_SDL3_2D_H
#define QEMU_UI_SDL3_2D_H

#include <stdbool.h>
#include <SDL3/SDL.h>

typedef struct QemuSDL3Display2D {
    SDL_Renderer *renderer;
    SDL_Texture *texture;
    SDL_PixelFormat format;
    int width;
    int height;
} QemuSDL3Display2D;

bool qemu_sdl3_2d_init(QemuSDL3Display2D *display, SDL_Window *window);
bool qemu_sdl3_2d_configure(QemuSDL3Display2D *display,
                            SDL_PixelFormat format,
                            int width,
                            int height);
bool qemu_sdl3_2d_update(QemuSDL3Display2D *display,
                         const SDL_Rect *rect,
                         const void *pixels,
                         int pitch);
void qemu_sdl3_2d_destroy(QemuSDL3Display2D *display);

#endif /* QEMU_UI_SDL3_2D_H */
