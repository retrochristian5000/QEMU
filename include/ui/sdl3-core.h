#ifndef QEMU_UI_SDL3_CORE_H
#define QEMU_UI_SDL3_CORE_H

#include <stdbool.h>
#include <SDL3/SDL.h>

bool qemu_sdl3_video_init(void);
void qemu_sdl3_video_quit(void);

SDL_Window *qemu_sdl3_window_create(const char *title,
                                     int width,
                                     int height,
                                     SDL_WindowFlags flags);
bool qemu_sdl3_window_set_title(SDL_Window *window,
                                const char *title);
bool qemu_sdl3_window_resize(SDL_Window *window,
                             int width,
                             int height);
bool qemu_sdl3_window_set_visible(SDL_Window *window, bool visible);
bool qemu_sdl3_window_set_fullscreen(SDL_Window *window,
                                     bool fullscreen);
void qemu_sdl3_window_destroy(SDL_Window *window);

#endif /* QEMU_UI_SDL3_CORE_H */
