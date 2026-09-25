#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src = (ROOT / "block/file-posix.c").read_text(encoding="utf-8")
meson = (ROOT / "meson.build").read_text(encoding="utf-8")
opts = (ROOT / "meson_options.txt").read_text(encoding="utf-8")
block_meson = (ROOT / "block/meson.build").read_text(encoding="utf-8")

for token in (
    "option('libisofs', type : 'feature', value : 'auto'",
    "dependency('libisofs-1'",
    "CONFIG_LIBISOFS",
    "libisofs support",
):
    assert token in opts + meson, f"missing libisofs build contract: {token}"

assert "file-posix.c'), coref, iokit, libisofs" in block_meson

for token in (
    "#include <libisofs.h>",
    "raw_isofs_metadata_read_ahead(",
    "raw_isofs_data_source_new_from_fd(",
    "qemu_dup(data->source_fd)",
    "pread(data->read_fd",
    "iso_image_import(",
    "iso_image_get_bootcat(",
    "iso_image_get_all_boot_imgs(",
    "iso_file_get_old_image_sections(",
    "fcntl(fd, F_RDADVISE, &ra)",
    "memcmp(id, \"CD001\"",
    "if (!(s->open_flags & O_RDWR))",
):
    assert token in src, f"missing libisofs metadata optimization: {token}"

assert "bdrv_flags & BDRV_O_NOCACHE" in src
assert "iso_read_opts_set_no_rockridge(read_opts, 1)" in src
assert "iso_read_opts_set_no_joliet(read_opts, 1)" in src
assert "iso_read_opts_set_no_iso1999(read_opts, 1)" in src
assert "ISO_READAHEAD_MAX (64 * MiB)" in src
assert "iso_data_source_new_from_file(" not in src
assert "raw_isofs_metadata_read_ahead(filename" not in src
assert "raw_isofs_metadata_read_ahead(s->fd, bdrv_flags)" in src
assert "IsoDataSource *src = calloc(1, sizeof(*src));" in src
assert "data = calloc(1, sizeof(*data));" in src
assert "free(data);" in src
assert "if (!src ||" in src

print("Darwin libisofs metadata read-ahead audit passed")
