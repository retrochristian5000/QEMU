/*
 * QEMU SDL3 2D renderer
 *
 * Rendering-only slice. Input and OpenGL remain separate migrations.
 */

#include <string.h>

#include "ui/sdl3-2d.h"

static bool qemu_sdl3_2d_main_thread(void)
{
    if (SDL_IsMainThread()) {
        return true;
    }

    SDL_SetError("QEMU SDL3 2D renderer must run on the main thread");
    return false;
}

bool qemu_sdl3_2d_init(QemuSDL3Display2D *display, SDL_Window *window)
{
    if (!display || !window) {
        SDL_SetError("QEMU SDL3 2D renderer requires a display and window");
        return false;
    }
    if (!qemu_sdl3_2d_main_thread()) {
        return false;
    }

    memset(display, 0, sizeof(*display));
    display->renderer = SDL_CreateRenderer(window, NULL);
    if (!display->renderer) {
        return false;
    }

    if (!SDL_SetRenderDrawColor(display->renderer, 0, 0, 0, 255)) {
        SDL_DestroyRenderer(display->renderer);
        display->renderer = NULL;
        return false;
    }

    return true;
}

bool qemu_sdl3_2d_configure(QemuSDL3Display2D *display,
                            SDL_PixelFormat format,
                            int width,
                            int height)
{
    SDL_Texture *texture;

    if (!display || !display->renderer || width <= 0 || height <= 0) {
        SDL_SetError("QEMU SDL3 2D renderer has invalid configuration");
        return false;
    }
    if (!qemu_sdl3_2d_main_thread()) {
        return false;
    }

    texture = SDL_CreateTexture(display->renderer, format,
                                SDL_TEXTUREACCESS_STREAMING,
                                width, height);
    if (!texture) {
        return false;
    }

    if (!SDL_SetTextureScaleMode(texture, SDL_SCALEMODE_NEAREST) ||
        !SDL_SetRenderLogicalPresentation(display->renderer,
                                          width, height,
                                          SDL_LOGICAL_PRESENTATION_LETTERBOX)) {
        SDL_DestroyTexture(texture);
        return false;
    }

    if (display->texture) {
        SDL_DestroyTexture(display->texture);
    }
    display->texture = texture;
    display->format = format;
    display->width = width;
    display->height = height;
    return true;
}

bool qemu_sdl3_2d_update(QemuSDL3Display2D *display,
                         const SDL_Rect *rect,
                         const void *pixels,
                         int pitch)
{
    if (!display || !display->renderer || !display->texture ||
        !pixels || pitch <= 0) {
        SDL_SetError("QEMU SDL3 2D renderer has invalid update data");
        return false;
    }
    if (!qemu_sdl3_2d_main_thread()) {
        return false;
    }

    if (!SDL_UpdateTexture(display->texture, rect, pixels, pitch) ||
        !SDL_RenderClear(display->renderer) ||
        !SDL_RenderTexture(display->renderer, display->texture, NULL, NULL) ||
        !SDL_RenderPresent(display->renderer)) {
        return false;
    }

    return true;
}

void qemu_sdl3_2d_destroy(QemuSDL3Display2D *display)
{
    if (!display || !qemu_sdl3_2d_main_thread()) {
        return;
    }

    if (display->texture) {
        SDL_DestroyTexture(display->texture);
    }
    if (display->renderer) {
        SDL_DestroyRenderer(display->renderer);
    }
    memset(display, 0, sizeof(*display));
}
