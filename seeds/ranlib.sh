#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select a native ranlib capable of indexing the current host's ar archives.
# This is a root tool: never bootstrap ranlib from an unbuilt compiler fork.
set -eu

archive_verbose=${WHP_ARCHIVE_VERBOSE:-0}
case "$archive_verbose" in
    0|1) ;;
    *) printf 'error: WHP_ARCHIVE_VERBOSE must be 0 or 1: %s\n' "$archive_verbose" >&2; exit 2 ;;
esac

# Report the executable's actual implementation, not the invoked name.
# In particular llvm-ranlib can be an argv[0]-sensitive llvm-ar symlink,
# while GNU gcc-ranlib is a wrapper around plugin-capable GNU binutils.
# Version signatures are diagnostic only; the real archive probe admits tools.
whp_archive_family()
(
    whp_tool=$1
    whp_version=$("$whp_tool" --version 2>&1) || {
        printf '%s\n' unknown
        exit 0
    }
    case "$whp_version" in
        *'LLVM version '*|*'LLVM (http'*) printf '%s\n' llvm ;;
        *'GNU ranlib'*|*'GNU ar'*|*'GNU Binutils'*) printf '%s\n' gnu ;;
        *) printf '%s\n' unknown ;;
    esac
)

whp_ranlib_report()
{
    [ "$archive_verbose" = 1 ] || return 0
    whp_family=$(whp_archive_family "$1")
    printf 'WHP ranlib selection: provider=%s; executable=%s; native-probe=%s; family=%s\n' \
        "$2" "$1" "${probe:-yes}" "$whp_family" >&2
}

# Report the actual failed native operation and a bounded stderr excerpt.
# A successful --print-seed must still print only the selected path.
whp_ranlib_probe_step()
{
    whp_stage=$1
    shift
    if "$@" >/dev/null 2>"$dir/probe-step.err"; then
        return 0
    else
        whp_status=$?
    fi
    printf 'error: WHP ranlib native probe failed: stage=%s; executable=%s; ar=%s; exit-status=%s\n' \
        "$whp_stage" "$ranlib" "$ar" "$whp_status" >&2
    printf '  command=%s\n' "$1" >&2
    if [ -s "$dir/probe-step.err" ]; then
        printf '%s\n' '  tool stderr (last 20 lines):' >&2
        tail -n 20 "$dir/probe-step.err" >&2
    fi
    return 1
}

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
    ar=$(/bin/sh "$root/seeds/ar.sh" --print-seed) || {
        printf '%s\n' 'error: ranlib probe cannot select a native ar seed' >&2
        exit 1
    }
    # Use the compiler adapter for both compilation and linking. On macOS
    # it carries the validated SDKROOT/-isysroot used by real native builds.
    cc_seed="$root/seeds/cc.sh"
    dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ranlib.XXXXXX") || exit 1
    trap 'rm -rf -- "$dir"' 0
    printf '%s\n' 'int whp_ranlib_probe(void) { return 1; }' > "$dir/probe.c"
    whp_ranlib_probe_step compile-member /bin/sh "$cc_seed" \
        -c "$dir/probe.c" -o "$dir/probe.o" || exit 1
    # GNU, Apple and LLVM archivers may index even a plain 'rc' archive.
    # Explicit S is required here: otherwise a no-op ranlib can pass its
    # link probe using a symbol table already written by the archiver.
    whp_ranlib_probe_step create-unindexed-archive "$ar" rcS \
        "$dir/libprobe.a" "$dir/probe.o" || exit 1
    # On Darwin, the linker can consume some archives without an index, so
    # link success is insufficient to prove that ranlib did anything. The
    # deliberately unindexed archive must actually change after indexing.
    before_index=$(cksum "$dir/libprobe.a") || exit 1
    whp_ranlib_probe_step index-archive "$ranlib" "$dir/libprobe.a" || exit 1
    after_index=$(cksum "$dir/libprobe.a") || exit 1
    if [ "$before_index" = "$after_index" ]; then
        printf 'error: WHP ranlib native probe failed: stage=index-unchanged; executable=%s; ar=%s\n' \
            "$ranlib" "$ar" >&2
        exit 1
    fi
    [ -s "$dir/libprobe.a" ] || {
        printf 'error: WHP ranlib probe produced an empty archive: ar=%s; ranlib=%s\n' \
            "$ar" "$ranlib" >&2
        exit 1
    }
    # A successful native link verifies the indexed archive is consumable.
    printf '%s\n' 'int whp_ranlib_probe(void); int main(void) { return whp_ranlib_probe() != 1; }' > "$dir/main.c"
    whp_ranlib_probe_step link-native-executable /bin/sh "$cc_seed" \
        "$dir/main.c" "$dir/libprobe.a" -o "$dir/probe" || exit 1
    # Linking alone cannot prove the archive can produce a usable host
    # executable. Verify that the indexed member was actually resolved.
    whp_ranlib_probe_step run-linked-executable "$dir/probe" || exit 1
    # An ordinary native-object archive may work with a GNU/LLVM mixed pair.
    # That does not verify GCC LTO plugin indexing or LLVM bitcode support.
    whp_ar_family=$(whp_archive_family "$ar")
    whp_ranlib_family=$(whp_archive_family "$ranlib")
    if [ "$whp_ar_family" != unknown ] &&
       [ "$whp_ranlib_family" != unknown ] &&
       [ "$whp_ar_family" != "$whp_ranlib_family" ]; then
        printf 'warning: native ar/ranlib families differ: ar=%s (%s); ranlib=%s (%s); ordinary objects passed, LTO indexing unverified\n' \
            "$ar" "$whp_ar_family" "$ranlib" "$whp_ranlib_family" >&2
    fi
)

select_seed()
{
    # Preserve the native seed override but expose competing selections.
    # The target archiver and QEMU's AR/RANLIB are deliberately independent.
    if [ -n "${WHP_RANLIB_SEED:-}" ] && [ -n "${RANLIB_FOR_BUILD:-}" ] &&
       [ "$WHP_RANLIB_SEED" != "$RANLIB_FOR_BUILD" ]; then
        printf 'warning: WHP_RANLIB_SEED overrides conflicting RANLIB_FOR_BUILD: %s != %s\n' \
            "$WHP_RANLIB_SEED" "$RANLIB_FOR_BUILD" >&2
    fi
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
        whp_ranlib_report "$candidate" "$setting"
        printf '%s\n' "$candidate"
        return 0
    done
    if [ "$(uname -s)" = Darwin ]; then
        . "$root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool ranlib system) || return 1
        candidate=$(resolve "$value") || return 1
        if [ "${probe:-yes}" = yes ]; then native_probe "$candidate" || return 1; fi
        whp_ranlib_report "$candidate" Apple-xcrun
        printf '%s\n' "$candidate"
        return 0
    fi
    for value in ranlib /usr/bin/ranlib; do
        candidate=$(resolve "$value") || continue
        if [ "${probe:-yes}" = yes ]; then native_probe "$candidate" || continue; fi
        whp_ranlib_report "$candidate" "host:$value"
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
        printf 'WHP native ranlib seed: %s (family: %s)\n' \
            "$selected" "$(whp_archive_family "$selected")"
        if [ "$archive_verbose" = 1 ]; then
            printf 'WHP ranlib validation: native archive create, index, link and execute passed\n'
        fi
        ;;
    *)
        # Regular invocations must not compile a new probe for each archive.
        probe=no
        selected=$(select_seed) || exit 1
        # GNU ranlib's --plugin is not a portable LLVM ranlib contract.
        # LLVM's indexer uses its own bitcode reader (llvm-ar s). Never
        # reinterpret or discard an explicit GNU LTO plugin request.
        for whp_option do
            case "$whp_option" in
                --plugin|--plugin=*)
                    if [ "$(whp_archive_family "$selected")" = llvm ]; then
                        printf 'error: GNU ranlib --plugin is unsupported by LLVM ranlib: %s; use a matching GNU LTO toolchain or omit the plugin flag\n' \
                            "$selected" >&2
                        exit 2
                    fi ;;
            esac
        done
        exec "$selected" "$@"
        ;;
esac
