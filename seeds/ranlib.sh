#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select a native ranlib capable of indexing the current host's ar archives.
# This is a root tool: never bootstrap ranlib from an unbuilt compiler fork.
set -eu

marker=whp-qemu-ranlib-seed-adapter
if [ "${1:-}" = --whp-ranlib-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
# Like cc.sh/ar.sh, follow symlinked launchers to this checkout before
# searching for sibling seeds. Reject loops rather than using the caller's
# unrelated directory as the dependency root.
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: ranlib seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1

resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-ranlib-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

native_probe()
(
    ranlib=$1
    # Use the same validated native archiver selected for Perl; never
    # silently pair ranlib with an unrelated target-format archive tool.
    ar=$(/bin/sh "$root/seeds/ar.sh" --print-seed) || exit 1
    # Use the compiler adapter for both compilation and linking. On macOS
    # it carries the validated SDKROOT/-isysroot used by real native builds.
    cc_seed="$root/seeds/cc.sh"
    dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ranlib.XXXXXX") || exit 1
    trap 'rm -rf -- "$dir"' 0
    printf '%s\n' 'int whp_ranlib_probe(void) { return 1; }' > "$dir/probe.c"
    /bin/sh "$cc_seed" -c "$dir/probe.c" -o "$dir/probe.o" >/dev/null 2>&1 || exit 1
    # Do not ask ar to create the symbol index: that is the operation
    # ranlib must supply. Using rcs here could mask a no-op indexer.
    "$ar" rc "$dir/libprobe.a" "$dir/probe.o" >/dev/null 2>&1 || exit 1
    "$ranlib" "$dir/libprobe.a" >/dev/null 2>&1 || exit 1
    [ -s "$dir/libprobe.a" ] || exit 1
    # A successful native link verifies the indexed archive is consumable.
    printf '%s\n' 'int whp_ranlib_probe(void); int main(void) { return whp_ranlib_probe() != 1; }' > "$dir/main.c"
    /bin/sh "$cc_seed" "$dir/main.c" "$dir/libprobe.a" -o "$dir/probe" >/dev/null 2>&1 || exit 1
    # Linking alone cannot prove the archive can produce a usable host
    # executable. Verify that the indexed member was actually resolved.
    "$dir/probe" >/dev/null 2>&1 || exit 1
)

select_seed()
{
    for setting in WHP_RANLIB_SEED RANLIB_FOR_BUILD; do
        case "$setting" in
            WHP_RANLIB_SEED) value=${WHP_RANLIB_SEED:-} ;;
            RANLIB_FOR_BUILD) value=${RANLIB_FOR_BUILD:-} ;;
        esac
        [ -n "$value" ] || continue
        candidate=$(resolve "$value") || {
            printf 'error: invalid %s: %s\n' "$setting" "$value" >&2
            return 1
        }
        if [ "${probe:-yes}" = yes ]; then
            native_probe "$candidate" || return 1
        fi
        printf '%s\n' "$candidate"
        return 0
    done
    if [ "$(uname -s)" = Darwin ]; then
        . "$root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool ranlib system) || return 1
        candidate=$(resolve "$value") || return 1
        if [ "${probe:-yes}" = yes ]; then native_probe "$candidate" || return 1; fi
        printf '%s\n' "$candidate"
        return 0
    fi
    for value in ranlib /usr/bin/ranlib; do
        candidate=$(resolve "$value") || continue
        if [ "${probe:-yes}" = yes ]; then native_probe "$candidate" || continue; fi
        printf '%s\n' "$candidate"
        return 0
    done
    printf '%s\n' 'error: no native ranlib passed the archive probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-ranlib) probe=yes; select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP native ranlib seed: %s\n' "$selected"
        ;;
    *)
        # Regular invocations must not compile a new probe for each archive.
        probe=no
        selected=$(select_seed) || exit 1
        exec "$selected" "$@"
        ;;
esac
