#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional installed LLVM archiver seed; never bootstrap LLVM to find llvm-ar.
# Not a replacement for the native ar/ranlib pair or the target LLVM toolchain.
set -eu

# The same opt-in trace contract as seeds/ar.sh, without requiring a fresh
# compiler/link test on each forwarded invocation.
archive_verbose=${WHP_ARCHIVE_VERBOSE:-0}
case "$archive_verbose" in
    0|1) ;;
    *) printf 'error: WHP_ARCHIVE_VERBOSE must be 0 or 1: %s\n' "$archive_verbose" >&2; exit 2 ;;
esac

whp_llvm_ar_report()
{
    [ "$archive_verbose" = 1 ] || return 0
    printf 'WHP llvm-ar selection: provider=%s; executable=%s; native-probe=%s\n' \
        "$2" "$1" "${probe:-yes}" >&2
}

whp_llvm_ar_invoke()
{
    [ "$archive_verbose" = 1 ] || return 0
    operation=${1:-<none>}
    archive=${2:-<none>}
    printf 'WHP llvm-ar invocation: executable=%s; operation=%s; archive=%s; argument-count=%s; admission=not-repeated\n' \
        "$selected" "$operation" "$archive" "$#" >&2
}

marker=whp-qemu-llvm-ar-seed-adapter
if [ "${1:-}" = --whp-llvm-ar-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: llvm-ar seed symlink loop' >&2
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
    # Do not follow the leaf symlink: LLVM tools can use argv[0] to select
    # multicall behavior (llvm-ar vs llvm-ranlib).
    identity=$("$candidate" --whp-llvm-ar-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    version=$("$candidate" --version 2>/dev/null) || exit 1
    case "$version" in
        *'LLVM version '*|*'LLVM (http'*) ;;
        *) exit 1 ;;
    esac
    printf '%s\n' "$candidate"
)

native_probe()
(
    archiver=$1
    cc_seed="$root/seeds/cc.sh"
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-llvm-ar-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    printf '%s\n' 'int whp_llvm_ar_first(void) { return 3; }' > "$tmp/first.c"
    printf '%s\n' 'int whp_llvm_ar_second(void) { return 5; }' > "$tmp/second.c"
    /bin/sh "$cc_seed" -c "$tmp/first.c" -o "$tmp/first.o" >/dev/null 2>&1 || exit 1
    /bin/sh "$cc_seed" -c "$tmp/second.c" -o "$tmp/second.o" >/dev/null 2>&1 || exit 1
    "$archiver" rcs "$tmp/libprobe.a" "$tmp/first.o" "$tmp/second.o" >/dev/null 2>&1 || exit 1
    listing=$("$archiver" t "$tmp/libprobe.a") || exit 1
    [ "$listing" = "$(printf 'first.o\nsecond.o')" ] || exit 1
    "$archiver" p "$tmp/libprobe.a" first.o > "$tmp/extracted.o" || exit 1
    cmp -s "$tmp/first.o" "$tmp/extracted.o" || exit 1
    # A stale or no-op replacement must not pass incremental admission.
    printf '%s\n' 'int whp_llvm_ar_first(void) { return 7; }' > "$tmp/first.c"
    /bin/sh "$cc_seed" -c "$tmp/first.c" -o "$tmp/first.o" >/dev/null 2>&1 || exit 1
    "$archiver" rcs "$tmp/libprobe.a" "$tmp/first.o" >/dev/null 2>&1 || exit 1
    listing=$("$archiver" t "$tmp/libprobe.a") || exit 1
    [ "$listing" = "$(printf 'first.o\nsecond.o')" ] || exit 1
    "$archiver" p "$tmp/libprobe.a" first.o > "$tmp/replaced.o" || exit 1
    cmp -s "$tmp/first.o" "$tmp/replaced.o" || exit 1
    # Test the archive's native symbol index without an unrelated ranlib.
    printf '%s\n' \
        'int whp_llvm_ar_first(void); int whp_llvm_ar_second(void);' \
        'int main(void) { return whp_llvm_ar_first() + whp_llvm_ar_second() != 12; }' \
        > "$tmp/main.c"
    /bin/sh "$cc_seed" "$tmp/main.c" "$tmp/libprobe.a" -o "$tmp/probe" >/dev/null 2>&1 || exit 1
    "$tmp/probe" >/dev/null 2>&1 || exit 1
)

select_seed()
{
    if [ -n "${WHP_LLVM_AR_SEED:-}" ]; then
        candidate=$(resolve "$WHP_LLVM_AR_SEED") || {
            printf 'error: invalid WHP_LLVM_AR_SEED: %s\n' "$WHP_LLVM_AR_SEED" >&2
            return 1
        }
        if [ "${probe:-yes}" = yes ]; then
            native_probe "$candidate" || {
                printf 'error: selected llvm-ar fails native archive/link probe: %s\n' "$candidate" >&2
                return 1
            }
        fi
        whp_llvm_ar_report "$candidate" WHP_LLVM_AR_SEED
        printf '%s\n' "$candidate"
        return 0
    fi
    # Prefer a sibling of the validated native C compiler, not an unrelated
    # LLVM from PATH. A failed compiler seed must not trigger LLVM bootstrap.
    compiler=$(/bin/sh "$root/seeds/cc.sh" --print-seed) || return 1
    for value in "${compiler%/*}/llvm-ar" llvm-ar \
        /opt/homebrew/opt/llvm/bin/llvm-ar /usr/local/opt/llvm/bin/llvm-ar \
        llvm-ar-22 llvm-ar-21 llvm-ar-20 llvm-ar-19 llvm-ar-18 llvm-ar-17 llvm-ar-16; do
        candidate=$(resolve "$value") || continue
        if [ "${probe:-yes}" = yes ]; then native_probe "$candidate" || continue; fi
        case "$value" in
            "${compiler%/*}/llvm-ar") origin=compiler-sibling ;;
            *) origin="installed:$value" ;;
        esac
        whp_llvm_ar_report "$candidate" "$origin"
        printf '%s\n' "$candidate"
        return 0
    done
    printf '%s\n' 'error: no installed native llvm-ar passed validation (optional seed)' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-ar) probe=yes; select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP installed llvm-ar seed: %s\n' "$selected"
        if [ "$archive_verbose" = 1 ]; then
            compiler=$(/bin/sh "$root/seeds/cc.sh" --print-seed) || exit 1
            printf 'WHP llvm-ar validation: compiler=%s; host=%s/%s; compile, archive, replace, index, link and execute passed\n' \
                "$compiler" "$(uname -s)" "$(uname -m)"
        fi
        ;;
    *)
        probe=no
        selected=$(select_seed) || exit 1
        whp_llvm_ar_invoke "$@"
        exec "$selected" "$@"
        ;;
esac
