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
mkdir -p "$work/app/lib" "$work/app/modules"
cat > "$work/library.c" <<'C'
__attribute__((visibility("default"), noinline))
int whp_dyld_answer(int value) { return value + 41; }
/* The stored pointer requires a rebase; imported pointers/direct calls
   in the client require binds against a separate Mach-O image. */
__attribute__((visibility("default")))
int (*whp_dyld_callback)(int) = whp_dyld_answer;
C
cat > "$work/plugin.c" <<'C'
/* Like a QEMU GModule .dylib: the module binds a private dependency and
   carries its own loader-relative search path to that dependency. */
extern int whp_dyld_answer(int);
__attribute__((visibility("default")))
int whp_dyld_plugin(int value) { return whp_dyld_answer(value); }
C
cat > "$work/main.c" <<'C'
#include <dlfcn.h>
#include <stdio.h>
extern int whp_dyld_answer(int);
extern int (*whp_dyld_callback)(int);
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
"$cc" "${flags[@]}" -dynamiclib "$work/plugin.c" \
    "$work/app/lib/libwhp-dyld-test.dylib" \
    -Wl,-install_name,@rpath/libwhp-dyld-plugin.dylib \
    -Wl,-rpath,@loader_path/../lib \
    -o "$work/app/modules/libwhp-dyld-plugin.dylib"
"$cc" "${flags[@]}" "$work/main.c" \
    "$work/app/lib/libwhp-dyld-test.dylib" \
    -Wl,-rpath,@loader_path/lib \
    -o "$work/app/whp-dyld-client"

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
grep -Fq '@rpath/libwhp-dyld-test.dylib' "$work/plugin-deps.txt"
grep -Fq 'path @loader_path/../lib (' "$work/plugin-loads.txt"

# Relocate the bundle to a path with spaces, and leave cwd unrelated to it.
mv "$work/app" "$work/moved bundle"
(
    unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_FRAMEWORK_PATH
    cd /
    "$work/moved bundle/whp-dyld-client"
)
