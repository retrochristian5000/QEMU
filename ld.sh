#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Native linker seed adapter for the WHP QEMU bootstrap graph.
#
# Keep this separate from the QEMU artifact linker (LD): Clang owns final
# host links and target firmware owns its cross-linker. No ABI/flag rewriting.

set -eu

WHP_LD_ADAPTER_MARKER=whp-qemu-ld-seed-adapter

if [ "${1:-}" = --whp-ld-adapter-probe ]; then
    printf '%s\n' "$WHP_LD_ADAPTER_MARKER"
    exit 0
fi

# Resolve the physical adapter path; a PATH symlink must still pair the
# native linker object probe with this checkout's cc.sh, not an unrelated CC.
whp_ld_entry=$0
case "$whp_ld_entry" in
    */*) ;;
    *) whp_ld_entry=$(command -v "$whp_ld_entry" 2>/dev/null || true) ;;
esac
[ -n "$whp_ld_entry" ] || exit 1
whp_ld_depth=0
while [ -L "$whp_ld_entry" ]; do
    whp_ld_depth=$((whp_ld_depth + 1))
    [ "$whp_ld_depth" -le 16 ] || {
        printf '%s\n' 'error: linker adapter symlink loop' >&2
        exit 1
    }
    whp_ld_link=$(readlink "$whp_ld_entry") || exit 1
    case "$whp_ld_link" in
        /*) whp_ld_entry=$whp_ld_link ;;
        *) whp_ld_entry=${whp_ld_entry%/*}/$whp_ld_link ;;
    esac
done
whp_ld_root=$(CDPATH= cd -P -- "${whp_ld_entry%/*}" && pwd -P) || exit 1

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-ld-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_LD_ADAPTER_MARKER" ]
}

resolve_executable()
{
    value=$1
    [ -n "$value" ] || return 1
    if [ -x "$value" ]; then
        candidate=$value
    else
        case "$value" in
            */*|*[[:space:]]*) return 1 ;;
        esac
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 3
    printf '%s\n' "$candidate"
}

# A relocatable native link exercises object-format compatibility without
# forcing crt objects, system libraries, an SDK deployment target, or QEMU
# artifact flags into this pre-LLVM dependency. This is deliberately not a
# test of final executable, ASan, LTO, or ARM64e linking.
linker_links_native_object()
(
    candidate=$1
    if [ -x "$whp_ld_root/cc.sh" ]; then
        compiler=$("$whp_ld_root/cc.sh" --print-cc 2>/dev/null) || exit 1
    elif [ -n "${CC_FOR_BUILD:-}" ]; then
        compiler=$CC_FOR_BUILD
    else
        # A standalone adapter can still use a native CC, but never QEMU's
        # target compiler. Symlinks into this checkout resolve above.
        compiler=$(command -v cc 2>/dev/null || true)
    fi
    [ -n "$compiler" ] || exit 1
    tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/whp-ld-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp_dir"' 0
    printf '%s\n' 'int whp_ld_seed_probe(void) { return 0; }' > "$tmp_dir/probe.c"
    "$compiler" -c "$tmp_dir/probe.c" -o "$tmp_dir/probe.o" \
        >/dev/null 2>&1 || exit 1
    "$candidate" -r -o "$tmp_dir/reloc.o" "$tmp_dir/probe.o" \
        >/dev/null 2>&1 || exit 1
    [ -s "$tmp_dir/reloc.o" ]
)

try_candidate()
{
    value=$1
    candidate=$(resolve_executable "$value") || return $?
    if [ "$probe_required" = yes ]; then
        linker_links_native_object "$candidate" || return 1
    fi
    printf '%s\n' "$candidate"
}

select_seed()
{
    # Empty explicit values mean 'unspecified'. Nonempty invalid overrides
    # fail closed rather than silently choosing another ABI/linker.
    for setting in WHP_LD_SEED LD_FOR_BUILD; do
        case "$setting" in
            WHP_LD_SEED) value=${WHP_LD_SEED:-} ;;
            LD_FOR_BUILD) value=${LD_FOR_BUILD:-} ;;
        esac
        [ -n "$value" ] || continue
        if seed=$(try_candidate "$value"); then
            printf '%s\n' "$seed"
            return 0
        fi
        printf 'error: %s is not a usable native relocatable linker: %s\n' \
            "$setting" "$value" >&2
        return 1
    done

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        # Never auto-select ld64.lld here: QEMU's ASan/arm64e policy is
        # checked separately before artifact linker promotion.
        # xcrun --sdk macosx --find ld selects the Apple developer linker.
        # Its /usr/bin/ld shim is valid, but a failed Xcode/CLT lookup must
        # never silently fall back to a different linker from PATH.
        . "$whp_ld_root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool ld system) || return 1
        if seed=$(try_candidate "$value"); then
            printf '%s\n' "$seed"
            return 0
        fi
        printf 'error: selected Apple linker cannot link native objects: %s\n' "$value" >&2
        return 1
    else
        candidates='ld ld.lld /usr/bin/ld'
    fi
    for value in $candidates; do
        if seed=$(try_candidate "$value"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' 'error: no native linker passed the WHP QEMU linker seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-ld|--print-seed)
        probe_required=yes
        select_seed
        ;;
    --check)
        probe_required=yes
        seed=$(select_seed)
        printf 'WHP native linker seed: %s\n' "$seed"
        ;;
    *)
        # Do not compile a fresh probe for each link invocation.
        probe_required=no
        seed=$(select_seed)
        exec "$seed" "$@"
        ;;
esac
