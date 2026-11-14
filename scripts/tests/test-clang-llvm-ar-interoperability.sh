#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Focused native Clang + installed llvm-ar interoperability audit.
# A working native-object archive does not prove the selected LTO toolchain.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
case "${WHP_CLANG_LLVM_AR_REQUIRE_LTO:-0}" in
    0|1) ;;
    *) printf '%s\n' 'error: WHP_CLANG_LLVM_AR_REQUIRE_LTO must be 0 or 1' >&2; exit 2 ;;
esac

# Pin the exact Clang driver for the llvm-ar admission probe, regardless of
# an inherited build-machine cc. The adapter supplies the macOS SDK on every
# real compile and link, not just when selecting the compiler.
clang=$(/bin/sh "$root/seeds/clang.sh" --print-clang) || exit 1
WHP_CLANG_SEED=$clang
WHP_CC_SEED=$clang
export WHP_CLANG_SEED WHP_CC_SEED
llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed) || {
    printf 'error: no installed llvm-ar passed native admission with Clang %s\n' "$clang" >&2
    exit 1
}

printf 'WHP Clang/llvm-ar: compiler=%s; archiver=%s; host=%s/%s\n' \
    "$clang" "$llvm_ar" "$(uname -s)" "$(uname -m)"

tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-clang-llvm-ar.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

printf '%s\n' \
    'int whp_clang_archive_value(void) { return 37; }' > "$tmp/member.c"
printf '%s\n' \
    'int whp_clang_archive_value(void);' \
    'int main(void) { return whp_clang_archive_value() != 37; }' > "$tmp/main.c"

# Keep the failing stage and stderr together; normal success is quiet.
probe_step()
{
    stage=$1
    shift
    if "$@" > "$tmp/step.out" 2> "$tmp/step.err"; then
        return 0
    else
        status=$?
    fi
    printf 'error: Clang/llvm-ar failure: stage=%s; exit=%s; tool=%s\n' \
        "$stage" "$status" "$1" >&2
    if [ -s "$tmp/step.err" ]; then
        cat "$tmp/step.err" >&2
    fi
    return 1
}

clang_run()
{
    /bin/sh "$root/seeds/clang.sh" "$@"
}

# Ordinary Mach-O/ELF native object: index, extract, link, and execute.
probe_step native-member clang_run -c "$tmp/member.c" -o "$tmp/member.o" || exit 1
probe_step native-main clang_run -c "$tmp/main.c" -o "$tmp/main.o" || exit 1
probe_step native-archive "$llvm_ar" rcs "$tmp/libnative.a" "$tmp/member.o" || exit 1
listing=$("$llvm_ar" t "$tmp/libnative.a") || {
    printf '%s\n' 'error: Clang/llvm-ar failure: stage=native-member-list' >&2
    exit 1
}
if [ "$listing" != member.o ]; then
    printf 'error: Clang/llvm-ar unexpected native members: %s\n' "$listing" >&2
    exit 1
fi
probe_step native-member-read "$llvm_ar" p "$tmp/libnative.a" member.o || exit 1
cmp -s "$tmp/member.o" "$tmp/step.out" || {
    printf '%s\n' 'error: llvm-ar returned different native object bytes' >&2
    exit 1
}
probe_step native-archive-link clang_run "$tmp/main.o" "$tmp/libnative.a" -o "$tmp/native" || exit 1
probe_step native-archive-execute "$tmp/native" || exit 1
printf '%s\n' 'WHP Clang/llvm-ar native objects: compile, archive, index, extract, link and execute passed'

# LTO direct-object links are the control group: if those fail before llvm-ar
# is used, we have a missing compiler/linker capability, not an archive bug.
# If direct linking succeeds, an archive failure is a genuine incompatibility.
for mode in thin full; do
    case "$mode" in
        thin) lto_flag=-flto=thin ;;
        full) lto_flag=-flto ;;
    esac
    if ! clang_run "$lto_flag" -c "$tmp/member.c" -o "$tmp/member-$mode.o" \
        > "$tmp/lto.out" 2> "$tmp/lto.err" ||
       ! clang_run "$lto_flag" -c "$tmp/main.c" -o "$tmp/main-$mode.o" \
        > "$tmp/lto.out" 2> "$tmp/lto.err" ||
       ! clang_run "$lto_flag" "$tmp/main-$mode.o" "$tmp/member-$mode.o" \
            -o "$tmp/direct-$mode" > "$tmp/lto.out" 2> "$tmp/lto.err" ||
       ! "$tmp/direct-$mode" > "$tmp/lto.out" 2> "$tmp/lto.err"; then
        printf 'warning: Clang %s LTO direct-object link unavailable; archive compatibility unverified\n' \
            "$mode" >&2
        if [ -s "$tmp/lto.err" ]; then
            cat "$tmp/lto.err" >&2
        fi
        if [ "${WHP_CLANG_LLVM_AR_REQUIRE_LTO:-0}" = 1 ]; then
            exit 1
        fi
        continue
    fi
    probe_step "$mode-lto-archive" "$llvm_ar" rcs "$tmp/lib-$mode.a" "$tmp/member-$mode.o" || exit 1
    listing=$("$llvm_ar" t "$tmp/lib-$mode.a") || {
        printf 'error: Clang/llvm-ar failure: stage=%s-lto-member-list\n' "$mode" >&2
        exit 1
    }
    if [ "$listing" != "member-$mode.o" ]; then
        printf 'error: Clang/llvm-ar unexpected %s LTO archive members: %s\n' "$mode" "$listing" >&2
        exit 1
    fi
    probe_step "$mode-lto-archive-link" clang_run "$lto_flag" \
        "$tmp/main-$mode.o" "$tmp/lib-$mode.a" -o "$tmp/linked-$mode" || exit 1
    probe_step "$mode-lto-archive-execute" "$tmp/linked-$mode" || exit 1
    printf 'WHP Clang/llvm-ar %s LTO: direct link, archived link and execution passed\n' "$mode"
done

printf '%s\n' 'WHP Clang/llvm-ar interoperability audit: complete'
