/*
 * QEMU SDL3 keyboard/text input receiver.
 * No SDL2 dependencies or event-polling ownership here.
 */

#include "qemu/osdep.h"
#include "standard-headers/linux/input-event-codes.h"
#include "ui/sdl3-input.h"

bool qemu_sdl3_input_init(QemuSDL3Input *input,
                          QemuConsole *con, SDL_Window *window)
{
    SDL_WindowID id;

    if (!input || !con || !window || !SDL_IsMainThread()) {
        SDL_SetError("SDL3 input requires a main-thread window and console");
        return false;
    }

    id = SDL_GetWindowID(window);
    if (!id) {
        return false;
    }

    memset(input, 0, sizeof(*input));
    input->con = con;
    input->window = window;
    input->window_id = id;
    input->kbd = qkbd_state_init(con);

    /* SDL3 disables UTF-8 text input by default, on a per-window basis. */
    if (QEMU_IS_TEXT_CONSOLE(con)) {
        if (!SDL_StartTextInput(window)) {
            qkbd_state_free(input->kbd);
            memset(input, 0, sizeof(*input));
            return false;
        }
        input->text_input_active = true;
    }
    return true;
}

bool qemu_sdl3_input_event(QemuSDL3Input *input, const SDL_Event *event)
{
    unsigned int lnx;
    SDL_Scancode scancode;
    bool down;

    if (!input || !input->kbd || !event) {
        return false;
    }
    if (!SDL_IsMainThread()) {
        SDL_SetError("QEMU SDL3 input requires main-thread event dispatch");
        return false;
    }

    switch (event->type) {
    case SDL_EVENT_KEY_DOWN:
    case SDL_EVENT_KEY_UP:
        if (event->key.windowID != input->window_id) {
            return false;
        }
        scancode = event->key.scancode;
        if (scancode <= SDL_SCANCODE_UNKNOWN ||
            (unsigned int)scancode >= qemu_input_map_usb_to_linux_len) {
            return true;
        }
        lnx = qemu_input_map_usb_to_linux[scancode];
        if (lnx == KEY_RESERVED) {
            return true;
        }

        down = event->type == SDL_EVENT_KEY_DOWN;
        qkbd_state_key_event(input->kbd, lnx, down);
        if (down && QEMU_IS_TEXT_CONSOLE(input->con)) {
            QemuTextConsole *text = QEMU_TEXT_CONSOLE(input->con);
            bool ctrl = qkbd_state_modifier_get(input->kbd, QKBD_MOD_CTRL);

            if (lnx == KEY_ENTER) {
                qemu_text_console_put_keysym(text, '\n');
            } else {
                qemu_text_console_put_linux(text, lnx, ctrl);
            }
        }
        return true;

    case SDL_EVENT_TEXT_INPUT:
        if (event->text.windowID != input->window_id) {
            return false;
        }
        if (input->text_input_active && event->text.text &&
            QEMU_IS_TEXT_CONSOLE(input->con)) {
            qemu_text_console_put_string(QEMU_TEXT_CONSOLE(input->con),
                                         event->text.text,
                                         strlen(event->text.text));
        }
        return true;

    case SDL_EVENT_WINDOW_FOCUS_LOST:
        if (event->window.windowID != input->window_id) {
            return false;
        }
        qkbd_state_lift_all_keys(input->kbd);
        return true;

    default:
        return false;
    }
}

void qemu_sdl3_input_destroy(QemuSDL3Input *input)
{
    if (!input || !input->kbd) {
        return;
    }
    if (!SDL_IsMainThread()) {
        SDL_SetError("QEMU SDL3 input must be destroyed on the main thread");
        return;
    }

    qkbd_state_lift_all_keys(input->kbd);
    if (input->text_input_active) {
        SDL_StopTextInput(input->window);
    }
    qkbd_state_free(input->kbd);
    memset(input, 0, sizeof(*input));
}
