/*
 * QEMU graphical console presentation policy
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "ui/console-presentation.h"
#include "console-priv.h"

bool qemu_console_get_window_autoresize(const QemuConsole *con)
{
    return !con || !con->window_autoresize_disabled;
}

void qemu_console_set_window_autoresize(QemuConsole *con, bool enabled)
{
    if (!con) {
        return;
    }

    con->window_autoresize_disabled = !enabled;
}

bool qemu_console_has_fixed_display_face(const QemuConsole *con)
{
    return con && con->display_face_width > 0 && con->display_face_height > 0;
}

static void qemu_console_recreate_display_surface(QemuConsole *con)
{
    g_clear_pointer(&con->display_surface, qemu_free_displaysurface);

    if (!qemu_console_has_fixed_display_face(con)) {
        return;
    }

    con->display_surface = qemu_create_displaysurface(con->display_face_width,
                                                      con->display_face_height);
}

void qemu_console_update_display_surface(QemuConsole *con)
{
    pixman_transform_t transform;
    pixman_image_t *src;
    pixman_image_t *dst;
    int sw, sh, dw, dh;

    if (!qemu_console_has_fixed_display_face(con) || !con->surface) {
        return;
    }

    if (!con->display_surface ||
        surface_width(con->display_surface) != con->display_face_width ||
        surface_height(con->display_surface) != con->display_face_height) {
        qemu_console_recreate_display_surface(con);
    }

    src = con->surface->image;
    dst = con->display_surface->image;
    sw = surface_width(con->surface);
    sh = surface_height(con->surface);
    dw = surface_width(con->display_surface);
    dh = surface_height(con->display_surface);

    if (sw <= 0 || sh <= 0 || dw <= 0 || dh <= 0) {
        return;
    }

    /*
     * Pixman transforms map destination coordinates back into the source.
     * Independent X/Y scale is intentional: CRT timing can produce
     * non-square pixels while still filling a fixed physical screen face.
     */
    pixman_transform_init_scale(&transform,
        pixman_double_to_fixed((double)sw / dw),
        pixman_double_to_fixed((double)sh / dh));
    pixman_image_set_transform(src, &transform);
    pixman_image_set_filter(src, PIXMAN_FILTER_BILINEAR, NULL, 0);
    pixman_image_composite32(PIXMAN_OP_SRC, src, NULL, dst,
                             0, 0, 0, 0, 0, 0, dw, dh);

    /* Do not leave presentation-only sampling state on the guest surface. */
    pixman_image_set_transform(src, NULL);
    pixman_image_set_filter(src, PIXMAN_FILTER_NEAREST, NULL, 0);
}

DisplaySurface *qemu_console_get_display_surface(QemuConsole *con)
{
    if (!con) {
        return NULL;
    }

    if (qemu_console_has_fixed_display_face(con) &&
        con->scanout.kind == SCANOUT_SURFACE) {
        return con->display_surface;
    }

    return con->surface;
}

void qemu_console_set_fixed_display_face(QemuConsole *con,
                                         int width, int height)
{
    if (!con) {
        return;
    }

    assert(width > 0);
    assert(height > 0);

    con->display_face_width = width;
    con->display_face_height = height;
    con->window_autoresize_disabled = true;
    qemu_console_recreate_display_surface(con);
    qemu_console_update_display_surface(con);
}

void qemu_console_free_display_surface(QemuConsole *con)
{
    if (!con) {
        return;
    }

    g_clear_pointer(&con->display_surface, qemu_free_displaysurface);
}
