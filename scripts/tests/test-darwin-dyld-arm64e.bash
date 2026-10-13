#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

# Test native dyld binds, rebases, @rpath and ARM64e indirect calls.
if [[ "$(uname -s)" != Darwin || $# -lt 1 || $# -gt 2 ]]; then
    printf 'usage (macOS): %s arm64|arm64e [apple|lld]\n' "$0" >&2
    exit 2
fi
arch="$1"
linker_kind="${2:-apple}"
case "$arch" in arm64|arm64e) ;; *) exit 2 ;; esac
case "$linker_kind" in apple|lld) ;; *) exit 2 ;; esac

cc="${WHP_DYLD_CC:-$(xcrun --find clang)}"
sdkroot="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
deployment="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | cut -d. -f1,2)}"
otool="$(xcrun --find otool)"
flags=(-arch "$arch" -isysroot "$sdkroot"
       "-mmacosx-version-min=$deployment")
if [[ "$linker_kind" == lld ]]; then
    # No silent fallback to Apple ld while reporting LLVM LLD success.
    : "${WHP_DYLD_LLD_DIR:?WHP_DYLD_LLD_DIR must contain ld64.lld}"
    [[ -x "$WHP_DYLD_LLD_DIR/ld64.lld" ]] || exit 1
    export PATH="$WHP_DYLD_LLD_DIR:$PATH"
    flags+=(-fuse-ld=lld)
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/whp-dyld-arm64e.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/app/lib" "$work/app/modules" "$work/app/plugin-private/lib"
cat > "$work/library.c" <<'C'
__attribute__((visibility("default"), noinline))
int whp_dyld_answer(int value) { return value + 41; }
/* The stored pointer requires a rebase; imported pointers/direct calls
   in the client require binds against a separate Mach-O image. */
__attribute__((visibility("default")))
int (*whp_dyld_callback)(int) = whp_dyld_answer;
C
cat > "$work/plugin-support.c" <<'C'
/* Never imported by the executable. The module's own LC_RPATH is required. */
__attribute__((visibility("default"), noinline))
int whp_dyld_support(int value) { return value + 40; }
C
cat > "$work/plugin.c" <<'C'
/* Mimic a late-loaded QEMU module with a distinct private dependency. */
extern int whp_dyld_support(int);
/* QEMU modules can resolve exports from their loading executable. Store an
   imported function pointer as well, to exercise an arm64e authenticated bind. */
extern int whp_dyld_host(int);
__attribute__((used))
static int (*volatile whp_dyld_host_callback)(int) = whp_dyld_host;
__attribute__((visibility("default")))
int whp_dyld_plugin(int value) {
    return whp_dyld_support(value) + whp_dyld_host_callback(0) + 1;
}
C
cat > "$work/main.c" <<'C'
#include <dlfcn.h>
#include <stdio.h>
extern int whp_dyld_answer(int);
extern int (*whp_dyld_callback)(int);
/* Export a host function, as QEMU does for late-loaded modules. */
__attribute__((visibility("default"), noinline))
int whp_dyld_host(int value) { return value; }
int main(void) {
    if (whp_dyld_answer(1) != 42 || whp_dyld_callback(1) != 42)
        return 11;
    void *handle = dlopen("@rpath/libwhp-dyld-test.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr, "dyld dlopen: %s\n", dlerror());
        return 12;
    }
    int (*callback)(int) = (int (*)(int))dlsym(handle, "whp_dyld_answer");
    if (!callback || callback(1) != 42) {
        fprintf(stderr, "dyld dlsym/authenticated call failed: %s\n", dlerror());
        return 13;
    }
    if (dlclose(handle) != 0)
        return 14;
    /* A real late-loaded module with its own LC_RPATH, like QEMU modules. */
    void *module = dlopen("@loader_path/modules/libwhp-dyld-plugin.dylib",
                          RTLD_NOW | RTLD_LOCAL);
    if (!module) {
        fprintf(stderr, "dyld module dlopen: %s\n", dlerror());
        return 15;
    }
    int (*plug)(int) = (int (*)(int))dlsym(module, "whp_dyld_plugin");
    if (!plug || plug(1) != 42)
        return 16;
    if (dlclose(module) != 0)
        return 17;
    puts("dyld relocatable bind/rebase and module load: passed");
    return 0;
}
C

"$cc" "${flags[@]}" -dynamiclib "$work/library.c" \
    -Wl,-install_name,@rpath/libwhp-dyld-test.dylib \
    -o "$work/app/lib/libwhp-dyld-test.dylib"
"$cc" "${flags[@]}" -dynamiclib "$work/plugin-support.c" \
    -Wl,-install_name,@rpath/libwhp-module-support.dylib \
    -o "$work/app/plugin-private/lib/libwhp-module-support.dylib"
# Meson's shared_module() on macOS uses MH_BUNDLE, not MH_DYLIB.
# Keep the .dylib filename used by QEMU's GModule loader, but test the real
# link type and unresolved host-symbol behavior instead of -dynamiclib.
"$cc" "${flags[@]}" -bundle -Wl,-undefined,dynamic_lookup "$work/plugin.c" \
    "$work/app/plugin-private/lib/libwhp-module-support.dylib" \
    -Wl,-rpath,@loader_path/../plugin-private/lib \
    -o "$work/app/modules/libwhp-dyld-plugin.dylib"
"$cc" "${flags[@]}" "$work/main.c" \
    "$work/app/lib/libwhp-dyld-test.dylib" \
    -Wl,-export_dynamic -Wl,-rpath,@loader_path/lib \
    -o "$work/app/whp-dyld-client"

# Validate the Mach-O ABI independently of suffixes and successful linking.
# In particular, the QEMU plugin is MH_BUNDLE and must not have LC_ID_DYLIB.
python3 - "$arch" \
    "$work/app/lib/libwhp-dyld-test.dylib" \
    "$work/app/plugin-private/lib/libwhp-module-support.dylib" \
    "$work/app/modules/libwhp-dyld-plugin.dylib" \
    "$work/app/whp-dyld-client" <<'PY'
import pathlib
import struct
import sys

arch, *names = sys.argv[1:]
expected_subtype = 0x80000002 if arch == "arm64e" else 0
# MH_DYLIB, MH_DYLIB, MH_BUNDLE, MH_EXECUTE.
filetypes = (6, 6, 8, 2)
for name, expected_type in zip(names, filetypes):
    blob = pathlib.Path(name).read_bytes()
    if len(blob) < 32:
        raise SystemExit(f"short Mach-O header: {name}")
    magic, cpu, subtype, kind, count, commands_size, _, _ = (
        struct.unpack_from("<8I", blob))
    if (magic, cpu, subtype, kind) != (
            0xFEEDFACF, 0x0100000C, expected_subtype, expected_type):
        raise SystemExit(
            f"unexpected Mach-O architecture or file type: {name}: "
            f"{cpu:#x}/{subtype:#x}/{kind:#x}")
    pos, end = 32, 32 + commands_size
    if end > len(blob):
        raise SystemExit(f"invalid Mach-O load-command bounds: {name}")
    commands = []
    for _ in range(count):
        if pos + 8 > end:
            raise SystemExit(f"truncated Mach-O command: {name}")
        cmd, size = struct.unpack_from("<2I", blob, pos)
        if size < 8 or pos + size > end:
            raise SystemExit(f"invalid Mach-O command size: {name}")
        commands.append(cmd)
        pos += size
    if pos != end:
        raise SystemExit(f"Mach-O commands do not fill sizeofcmds: {name}")
    if 0x32 not in commands and 0x24 not in commands:
        raise SystemExit(f"missing macOS deployment command: {name}")
    if (0xD in commands) != (expected_type == 6):
        raise SystemExit(f"incorrect LC_ID_DYLIB for Mach-O type: {name}")
    if expected_type == 8 and (
            0x8000001C not in commands or 0xC not in commands):
        raise SystemExit(f"bundle lost LC_RPATH or LC_LOAD_DYLIB: {name}")
print("dyld Mach-O dylib/bundle ABI metadata: passed")
PY

# Verify the load-command contract separately from the execution test.
"$otool" -L "$work/app/whp-dyld-client" > "$work/deps.txt"
"$otool" -l "$work/app/whp-dyld-client" > "$work/commands.txt"
"$otool" -D "$work/app/lib/libwhp-dyld-test.dylib" > "$work/id.txt"
grep -Fq '@rpath/libwhp-dyld-test.dylib' "$work/deps.txt"
grep -Fq 'cmd LC_RPATH' "$work/commands.txt"
grep -Fq 'path @loader_path/lib (' "$work/commands.txt"
grep -Fq '@rpath/libwhp-dyld-test.dylib' "$work/id.txt"
"$otool" -L "$work/app/modules/libwhp-dyld-plugin.dylib" > "$work/plugin-deps.txt"
"$otool" -l "$work/app/modules/libwhp-dyld-plugin.dylib" > "$work/plugin-loads.txt"
grep -Fq '@rpath/libwhp-module-support.dylib' "$work/plugin-deps.txt"
grep -Fq 'path @loader_path/../plugin-private/lib (' "$work/plugin-loads.txt"

# Relocate the bundle to a path with spaces, and leave cwd unrelated to it.
mv "$work/app" "$work/moved bundle"
(
    unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_FRAMEWORK_PATH
    cd /
    "$work/moved bundle/whp-dyld-client"
)
