/*
 * QEMU SDL3 input receiver.
 * Window-scoped; the frontend owns polling the global SDL event queue.
 */
#ifndef QEMU_UI_SDL3_INPUT_H
#define QEMU_UI_SDL3_INPUT_H

#include <SDL3/SDL.h>

#include "ui/console.h"
#include "ui/kbd-state.h"

typedef struct QemuSDL3Input {
    QemuConsole *con;
    QKbdState *kbd;
    SDL_Window *window;
    SDL_WindowID window_id;
    bool text_input_active;
} QemuSDL3Input;

bool qemu_sdl3_input_init(QemuSDL3Input *input,
                          QemuConsole *con, SDL_Window *window);
bool qemu_sdl3_input_event(QemuSDL3Input *input, const SDL_Event *event);
void qemu_sdl3_input_destroy(QemuSDL3Input *input);

#endif /* QEMU_UI_SDL3_INPUT_H */
