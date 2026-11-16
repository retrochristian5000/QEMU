#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native LLVM archive indexer; never bootstrap LLVM to discover it.
# Keep this distinct from Apple/GNU ranlib and from the generic ranlib.sh seed.
set -eu

archive_verbose=${WHP_ARCHIVE_VERBOSE:-0}
case "$archive_verbose" in
    0|1) ;;
    *) printf 'error: WHP_ARCHIVE_VERBOSE must be 0 or 1: %s\n' "$archive_verbose" >&2; exit 2 ;;
esac

marker=whp-qemu-llvm-ranlib-seed-adapter
if [ "${1:-}" = --whp-llvm-ranlib-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: llvm-ranlib seed symlink loop' >&2
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
    # LLVM's llvm-ar/llvm-ranlib multicall tool selects behavior by argv[0].
    # Preserve the leaf symlink rather than resolving to the shared binary.
    identity=$("$candidate" --whp-llvm-ranlib-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

llvm_major()
(
    tool=$1
    banner=$("$tool" --version 2>/dev/null) || exit 1
    case "$banner" in
        *'LLVM version '*|*'LLVM (http'*) ;;
        *) exit 1 ;;
    esac
    major=$(printf '%s\n' "$banner" | sed -n 's/.*LLVM version \([0-9][0-9]*\).*/\1/p' | sed -n '1p')
    [ -n "$major" ] || exit 1
    printf '%s\n' "$major"
)

probe_step()
{
    stage=$1
    shift
    if "$@" >/dev/null 2>"$tmp/probe-step.err"; then
        return 0
    else
        code=$?
    fi
    printf 'error: WHP llvm-ranlib native probe failed: stage=%s; ranlib=%s; ar=%s; exit-status=%s\n' \
        "$stage" "$ranlib" "$llvm_ar" "$code" >&2
    if [ -s "$tmp/probe-step.err" ]; then
        printf '%s\n' '  tool stderr (last 20 lines):' >&2
        tail -n 20 "$tmp/probe-step.err" >&2
    fi
    return 1
}

native_probe()
(
    ranlib=$1
    llvm_ar=$2
    cc_seed="$root/seeds/cc.sh"
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-llvm-ranlib.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    printf '%s\n' 'int whp_llvm_ranlib_member(void) { return 9; }' > "$tmp/member.c"
    probe_step compile-member /bin/sh "$cc_seed" -c "$tmp/member.c" -o "$tmp/member.o" || exit 1
    # rcS suppresses LLVM ar's default automatic index. The indexer must
    # materially change this archive, not merely return success.
    probe_step create-unindexed-archive "$llvm_ar" rcS "$tmp/libprobe.a" "$tmp/member.o" || exit 1
    before=$(cksum "$tmp/libprobe.a") || exit 1
    probe_step index-archive "$ranlib" "$tmp/libprobe.a" || exit 1
    after=$(cksum "$tmp/libprobe.a") || exit 1
    if [ "$before" = "$after" ]; then
        printf 'error: WHP llvm-ranlib native probe failed: stage=index-unchanged; ranlib=%s; ar=%s\n' \
            "$ranlib" "$llvm_ar" >&2
        exit 1
    fi
    printf '%s\n' 'int whp_llvm_ranlib_member(void); int main(void) { return whp_llvm_ranlib_member() != 9; }' > "$tmp/main.c"
    probe_step link-native-executable /bin/sh "$cc_seed" "$tmp/main.c" "$tmp/libprobe.a" -o "$tmp/probe" || exit 1
    probe_step run-linked-executable "$tmp/probe" || exit 1
)

select_seed()
{
    # Resolve the paired ar centrally. The fast candidate path checks LLVM
    # identity only; a full native archive probe runs on admission calls.
    if [ "${probe:-yes}" = yes ]; then
        llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed) || {
            printf '%s\n' 'error: llvm-ranlib requires a validated installed llvm-ar' >&2
            return 1
        }
    else
        llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-candidate) || return 1
    fi
    ar_major=$(llvm_major "$llvm_ar") || return 1
    ar_leaf=${llvm_ar##*/}
    case "$ar_leaf" in
        llvm-ar*) sibling="${llvm_ar%/*}/llvm-ranlib${ar_leaf#llvm-ar}" ;;
        *) sibling="${llvm_ar%/*}/llvm-ranlib" ;;
    esac

    if [ -n "${WHP_LLVM_RANLIB_SEED:-}" ]; then
        values=$WHP_LLVM_RANLIB_SEED
        explicit=yes
    else
        explicit=no
    fi

    if [ "$explicit" = yes ]; then
        candidate=$(resolve "$values") || {
            printf 'error: invalid WHP_LLVM_RANLIB_SEED: %s\n' "$values" >&2
            return 1
        }
        provider=WHP_LLVM_RANLIB_SEED
        admit_candidate "$candidate" "$provider" "$ar_major" || return 1
        return 0
    fi

    # Prefer the indexer sitting next to the admitted LLVM archiver. Avoid
    # selecting Apple/GNU ranlib by their generic name.
    for value in "$sibling" llvm-ranlib \
        /opt/homebrew/opt/llvm/bin/llvm-ranlib /usr/local/opt/llvm/bin/llvm-ranlib \
        llvm-ranlib-22 llvm-ranlib-21 llvm-ranlib-20 llvm-ranlib-19 \
        llvm-ranlib-18 llvm-ranlib-17 llvm-ranlib-16; do
        candidate=$(resolve "$value") || continue
        if admit_candidate "$candidate" "installed:$value" "$ar_major"; then
            return 0
        fi
    done
    printf 'error: no installed llvm-ranlib of LLVM major %s passed validation (optional seed)\n' \
        "$ar_major" >&2
    return 1
}

admit_candidate()
{
    candidate=$1
    provider=$2
    ar_major=$3
    case "${candidate##*/}" in
        llvm-ar|llvm-ar-[0-9]*)
            printf 'error: llvm-ar executable is not a ranlib alias: %s\n' "$candidate" >&2
            return 1 ;;
    esac
    candidate_major=$(llvm_major "$candidate") || {
        printf 'error: not an LLVM ranlib implementation: %s\n' "$candidate" >&2
        return 1
    }
    if [ "$candidate_major" != "$ar_major" ]; then
        printf 'error: LLVM ranlib/ar version mismatch: ranlib=%s (major %s); ar=%s (major %s)\n' \
            "$candidate" "$candidate_major" "$llvm_ar" "$ar_major" >&2
        return 1
    fi
    if [ "${probe:-yes}" = yes ]; then
        native_probe "$candidate" "$llvm_ar" || return 1
    fi
    if [ "$archive_verbose" = 1 ]; then
        printf 'WHP llvm-ranlib selection: provider=%s; executable=%s; ar=%s; llvm-major=%s; native-probe=%s\n' \
            "$provider" "$candidate" "$llvm_ar" "$candidate_major" "${probe:-yes}" >&2
    fi
    printf '%s\n' "$candidate"
}

reject_gnu_plugin()
{
    for option do
        case "$option" in
            --plugin|--plugin=*)
                printf '%s\n' 'error: GNU ranlib --plugin is not an LLVM ranlib option; use matching GNU binutils for GNU LTO plugins' >&2
                return 2 ;;
        esac
    done
}

case "${1:-}" in
    --print-seed|--print-ranlib)
        probe=yes
        select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP installed llvm-ranlib seed: %s\n' "$selected"
        if [ "$archive_verbose" = 1 ]; then
            printf '%s\n' 'WHP llvm-ranlib validation: LLVM ar pair, native archive index, link and execute passed'
        fi ;;
    *)
        reject_gnu_plugin "$@" || exit 2
        probe=no
        selected=$(select_seed) || exit 1
        if [ "$archive_verbose" = 1 ]; then
            printf 'WHP llvm-ranlib invocation: executable=%s; archive=%s; argument-count=%s; admission=not-repeated\n' \
                "$selected" "${1:-<none>}" "$#" >&2
        fi
        exec "$selected" "$@" ;;
esac
