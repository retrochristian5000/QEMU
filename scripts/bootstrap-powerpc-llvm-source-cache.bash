#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SUBMODULE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
LLVM_CACHE_DIR="${POWERPC_LLVM_SOURCE_DIR:-$TOOLCHAIN_WORK_DIR/llvm-source-from-submodule}"

case "$TOOLCHAIN_TARGET" in
    powerpc-elf) ;;
    *)
        printf 'error: the LLVM source-cache stage supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

for required in git mkdir rm; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: LLVM source-cache dependency not found: %s\n' "$required" >&2
        exit 1
    fi
done

if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ]]; then
    printf 'error: LLVM submodule is not initialized: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi

expected_revision="$(git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}')"
submodule_revision="$(git -C "$LLVM_SUBMODULE_DIR" rev-parse HEAD)"
if [[ -z "$expected_revision" || "$submodule_revision" != "$expected_revision" ]]; then
    printf '%s\n' \
        'error: LLVM submodule does not match the QEMU gitlink.' \
        "checked out: ${submodule_revision:-missing}" \
        "QEMU expects: ${expected_revision:-missing}" >&2
    exit 1
fi

cache_is_reusable=0
if [[ -d "$LLVM_CACHE_DIR/.git" ]] &&
   git -C "$LLVM_CACHE_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    # The old --filter local-clone path can leave a promisor cache that asks a
    # local repository for unsupported partial-clone filtering, producing a
    # warning/fetch storm.  Never reuse that cache.
    if [[ "$(git -C "$LLVM_CACHE_DIR" config --get remote.origin.promisor || true)" != true ]]; then
        cache_is_reusable=1
    fi
fi

if [[ "$cache_is_reusable" == 0 ]]; then
    rm -rf "$LLVM_CACHE_DIR"
    mkdir -p "$(dirname "$LLVM_CACHE_DIR")"
    # The LLVM submodule is already the pinned source cache.  A normal local
    # clone reuses its object store via Git's local hard-link optimization and
    # deliberately does not request partial-clone filtering from a local repo.
    git clone --local --no-checkout "$LLVM_SUBMODULE_DIR" "$LLVM_CACHE_DIR"
    git -C "$LLVM_CACHE_DIR" sparse-checkout init --cone
fi

# The base bootstrap remains authoritative for selecting the sparse paths,
# fetching/verifying the exact commit, checking out, cleaning and building.
git -C "$LLVM_CACHE_DIR" remote set-url origin "$LLVM_SUBMODULE_DIR"
printf 'LLVM compiler source cache: %s (%s)\n' \
    "$LLVM_CACHE_DIR" "$submodule_revision"
