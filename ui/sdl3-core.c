/*
 * QEMU SDL3 display core
 *
 * Core video/window lifecycle only. Rendering, input and OpenGL
 * remain in the SDL2 frontend until their dedicated SDL3 ports.
 */

#include "ui/sdl3-core.h"

static bool qemu_sdl3_video_main_thread(void)
{
    if (SDL_IsMainThread()) {
        return true;
    }

    SDL_SetError("QEMU SDL3 video core must run on the main thread");
    return false;
}

bool qemu_sdl3_video_init(void)
{
    if (!qemu_sdl3_video_main_thread()) {
        return false;
    }

    return SDL_InitSubSystem(SDL_INIT_VIDEO);
}

void qemu_sdl3_video_quit(void)
{
    if (!qemu_sdl3_video_main_thread()) {
        return;
    }

    SDL_QuitSubSystem(SDL_INIT_VIDEO);
}

SDL_Window *qemu_sdl3_window_create(const char *title,
                                     int width,
                                     int height,
                                     SDL_WindowFlags flags)
{
    if (!qemu_sdl3_video_main_thread()) {
        return NULL;
    }

    return SDL_CreateWindow(title, width, height, flags);
}

bool qemu_sdl3_window_set_title(SDL_Window *window,
                                const char *title)
{
    if (!qemu_sdl3_video_main_thread()) {
        return false;
    }

    return SDL_SetWindowTitle(window, title);
}

bool qemu_sdl3_window_resize(SDL_Window *window,
                             int width,
                             int height)
{
    if (!qemu_sdl3_video_main_thread()) {
        return false;
    }

    return SDL_SetWindowSize(window, width, height);
}

bool qemu_sdl3_window_set_visible(SDL_Window *window, bool visible)
{
    if (!qemu_sdl3_video_main_thread()) {
        return false;
    }

    return visible ? SDL_ShowWindow(window) : SDL_HideWindow(window);
}

bool qemu_sdl3_window_set_fullscreen(SDL_Window *window,
                                     bool fullscreen)
{
    if (!qemu_sdl3_video_main_thread()) {
        return false;
    }

    if (fullscreen && !SDL_SetWindowFullscreenMode(window, NULL)) {
        return false;
    }

    return SDL_SetWindowFullscreen(window, fullscreen);
}

void qemu_sdl3_window_destroy(SDL_Window *window)
{
    if (!window || !qemu_sdl3_video_main_thread()) {
        return;
    }

    SDL_DestroyWindow(window);
}
