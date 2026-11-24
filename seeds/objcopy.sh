#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Installed object-copy seed; never bootstrap LLVM or Binutils here.
set -eu

marker=whp-qemu-objcopy-seed-adapter
if [ "${1:-}" = --whp-objcopy-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

fail()
{
    printf 'error: objcopy seed: %s\n' "$1" >&2
    exit 1
}

resolve()
(
    case "$1" in
        */*) candidate=$1 ;;
        *[[:space:]]*|'') exit 1 ;;
        *) candidate=$(command -v "$1" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-objcopy-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    banner=$("$candidate" --version 2>/dev/null) || exit 1
    case "$banner" in
        *'GNU objcopy'*|*'LLVM version '*) ;;
        *) exit 1 ;;
    esac
    printf '%s\n' "$candidate"
)

native_probe()
(
    entry=$0
    case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
    depth=0
    while [ -L "$entry" ]; do
        depth=$((depth + 1))
        [ "$depth" -le 16 ] || exit 1
        link=$(readlink "$entry") || exit 1
        case "$link" in
            /*) entry=$link ;;
            *) entry=${entry%/*}/$link ;;
        esac
    done
    root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1
    printf '%s\n' 'int whp_objcopy_probe(void) { return 71; }' > "$tmp/input.c"
    printf '%s\n' 'int whp_objcopy_probe(void); int main(void) { return whp_objcopy_probe() != 71; }' > "$tmp/main.c"
    /bin/sh "$root/seeds/cc.sh" -g -c "$tmp/input.c" -o "$tmp/input.o" || exit 1
    "$1" --strip-debug "$tmp/input.o" "$tmp/output.o" || exit 1
    [ -s "$tmp/output.o" ] || exit 1
    if cmp -s "$tmp/input.o" "$tmp/output.o"; then
        exit 1
    else
        [ "$?" -eq 1 ] || exit 1
    fi
    /bin/sh "$root/seeds/cc.sh" "$tmp/main.c" "$tmp/output.o" -o "$tmp/probe" || exit 1
    "$tmp/probe"
)

probe()
(
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-objcopy-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    if [ "$role" = firmware ]; then
        # Copy the fixture first so a faulty provider cannot change the source.
        cp "$WHP_OBJCOPY_PROBE_OBJECT" "$tmp/input.o" || exit 1
        "$1" -O binary "$tmp/input.o" "$tmp/output.bin" || exit 1
        [ -s "$tmp/output.bin" ] || exit 1
        cmp -s "$WHP_OBJCOPY_PROBE_BINARY" "$tmp/output.bin"
    else
        native_probe "$1"
    fi
)

role=native
if [ -n "${WHP_OBJCOPY_PROBE_OBJECT:-}" ] || [ -n "${WHP_OBJCOPY_PROBE_BINARY:-}" ]; then
    role=firmware
    for fixture in "${WHP_OBJCOPY_PROBE_OBJECT:-}" "${WHP_OBJCOPY_PROBE_BINARY:-}"; do
        case "$fixture" in
            /*) ;;
            *) fail 'firmware probe requires two absolute fixture paths' ;;
        esac
        [ -f "$fixture" ] && [ -s "$fixture" ] && [ -r "$fixture" ] ||
            fail "missing, empty or unreadable firmware fixture: $fixture"
    done
fi

admit()
{
    selected=$(resolve "$1") || return 1
    if [ "$validate" = yes ]; then
        probe "$selected" >&2 || return 1
    fi
    printf '%s\n' "$selected"
}

select_seed()
{
    if [ -n "${WHP_OBJCOPY_SEED:-}" ]; then
        admit "$WHP_OBJCOPY_SEED" || fail "WHP_OBJCOPY_SEED failed $role admission: $WHP_OBJCOPY_SEED"
        return
    fi
    if [ "$role" = native ] && [ -n "${OBJCOPY_FOR_BUILD:-}" ]; then
        admit "$OBJCOPY_FOR_BUILD" || fail "OBJCOPY_FOR_BUILD failed native admission: $OBJCOPY_FOR_BUILD"
        return
    fi
    for value in llvm-objcopy gobjcopy objcopy; do
        if selected=$(admit "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    fail "no installed GNU or LLVM objcopy passed $role admission; set WHP_OBJCOPY_SEED"
}

case "${1:-}" in
    --print-seed|--print-objcopy|--check)
        [ "$#" -eq 1 ] || fail 'seed admission does not accept extra arguments'
        validate=yes
        selected=$(select_seed) || exit 1
        if [ "$1" = --check ]; then
            printf 'WHP objcopy seed: %s (%s probe passed)\n' "$selected" "$role"
        else
            printf '%s\n' "$selected"
        fi
        ;;
    *)
        # Forward only an explicitly selected executable. Reuse the path
        # from --print-seed; do not repeat probes on every firmware object.
        [ -n "${WHP_OBJCOPY_SEED:-}" ] || fail 'forwarding requires an admitted WHP_OBJCOPY_SEED path'
        validate=no
        selected=$(select_seed) || exit 1
        exec "$selected" "$@"
        ;;
esac
