#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src = (ROOT / "block/file-posix.c").read_text(encoding="utf-8")

parse_start = src.index("static void raw_parse_flags(")
parse_end = src.index("static void raw_parse_filename", parse_start)
cache_logic = src[parse_start:parse_end]

for token in (
    "#ifndef CONFIG_DARWIN",
    "*open_flags |= O_DIRECT;",
    "static int raw_apply_nocache(",
    "fcntl(fd, F_NOCACHE, nocache)",
    "S_ISREG(st.st_mode)",
):
    assert token in cache_logic, f"missing Darwin cache-direct contract: {token}"

assert "raw_apply_nocache(s->fd, bdrv_flags, errp)" in src

reconfig_start = src.index("static int raw_reconfigure_getfd(")
reconfig_end = src.index("static int raw_reopen_prepare(", reconfig_start)
reconfig = src[reconfig_start:reconfig_end]

for token in (
    "bool nocache_changed = false;",
    "!!(flags & BDRV_O_NOCACHE)",
    "!!(bs->open_flags & BDRV_O_NOCACHE)",
    "&& !nocache_changed",
    "if (!nocache_changed &&",
    "raw_apply_nocache(fd, flags, errp)",
):
    assert token in reconfig, f"missing Darwin reopen cache contract: {token}"

assert "O_DIRECT for no caching" not in cache_logic
print("Darwin block F_NOCACHE audit passed")
