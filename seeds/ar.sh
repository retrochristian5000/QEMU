#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native archive seed for QEMU host-tool bootstraps.
# Do not replace the host archiver with a target or unbuilt LLVM archiver.
set -eu

marker=whp-qemu-ar-seed-adapter
if [ "${1:-}" = --whp-ar-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || { printf '%s\n' 'error: ar seed symlink loop' >&2; exit 1; }
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
    identity=$("$candidate" --whp-ar-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

archive_probe()
(
    archiver=$1
    # Invoke the adapter rather than its printed compiler path. On macOS
    # cc.sh supplies the validated -isysroot/SDKROOT during real compilation;
    # a bare compiler invocation would probe a different environment.
    compiler_seed="$root/seeds/cc.sh"
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ar-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    printf '%s\n' 'int whp_ar_probe(void) { return 7; }' > "$tmp/probe.c"
    /bin/sh "$compiler_seed" -c "$tmp/probe.c" -o "$tmp/probe.o" >/dev/null 2>&1 || exit 1
    # 'rc' deliberately does not require ranlib, which depends on this seed.
    "$archiver" rc "$tmp/libprobe.a" "$tmp/probe.o" >/dev/null 2>&1 || exit 1
    [ -s "$tmp/libprobe.a" ] || exit 1
    listing=$("$archiver" t "$tmp/libprobe.a") || exit 1
    [ "$listing" = probe.o ] || exit 1
    mkdir "$tmp/extracted" || exit 1
    (cd "$tmp/extracted" && "$archiver" x "$tmp/libprobe.a" probe.o) >/dev/null 2>&1 || exit 1
    [ -s "$tmp/extracted/probe.o" ] || exit 1
    cmp -s "$tmp/probe.o" "$tmp/extracted/probe.o" || exit 1
    # Verify the streamed member against the original compiler output.
    "$archiver" p "$tmp/libprobe.a" probe.o > "$tmp/from-archive.o" || exit 1
    cmp -s "$tmp/probe.o" "$tmp/from-archive.o" || exit 1
)

select_seed()
{
    for setting in WHP_AR_SEED AR_FOR_BUILD; do
        case "$setting" in
            WHP_AR_SEED) value=${WHP_AR_SEED:-} ;;
            AR_FOR_BUILD) value=${AR_FOR_BUILD:-} ;;
        esac
        [ -n "$value" ] || continue
        candidate=$(resolve "$value") || {
            printf 'error: invalid %s for native ar: %s\n' "$setting" "$value" >&2
            return 1
        }
        if [ "${probe:-yes}" = yes ]; then
            archive_probe "$candidate" || {
                printf 'error: %s fails native archive probe: %s\n' "$setting" "$candidate" >&2
                return 1
            }
        fi
        printf '%s\n' "$candidate"
        return 0
    done

    if [ "$(uname -s)" = Darwin ]; then
        . "$root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool ar system) || return 1
        candidate=$(resolve "$value") || return 1
        if [ "${probe:-yes}" = yes ]; then archive_probe "$candidate" || return 1; fi
        printf '%s\n' "$candidate"
        return 0
    fi
    for value in ar /usr/bin/ar; do
        candidate=$(resolve "$value") || continue
        if [ "${probe:-yes}" = yes ]; then archive_probe "$candidate" || continue; fi
        printf '%s\n' "$candidate"
        return 0
    done
    printf '%s\n' 'error: no native ar passed the archive probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-ar) probe=yes; select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP native ar seed: %s\n' "$selected"
        ;;
    *)
        probe=no
        selected=$(select_seed) || exit 1
        exec "$selected" "$@"
        ;;
esac
