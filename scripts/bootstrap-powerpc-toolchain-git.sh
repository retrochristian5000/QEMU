#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-toolchain.sh"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_DOWNLOAD_DIR="${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$SOURCE_DIR/build/toolchain-downloads}"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET}"
GIT_CACHE_DIR="${POWERPC_TOOLCHAIN_GIT_CACHE_DIR:-$TOOLCHAIN_DOWNLOAD_DIR/git}"
GIT_EXPORT_DIR="${POWERPC_TOOLCHAIN_GIT_EXPORT_DIR:-$TOOLCHAIN_WORK_DIR/git-exports}"
GIT_OFFLINE="${POWERPC_TOOLCHAIN_GIT_OFFLINE:-0}"

BINUTILS_GIT_URL="${POWERPC_BINUTILS_GIT_URL:-https://sourceware.org/git/binutils-gdb.git}"
BINUTILS_GIT_REF="${POWERPC_BINUTILS_GIT_REF:-binutils-2_46-branch}"
BINUTILS_GIT_COMMIT="${POWERPC_BINUTILS_GIT_COMMIT:-}"
GCC_GIT_URL="${POWERPC_GCC_GIT_URL:-https://gcc.gnu.org/git/gcc.git}"
GCC_GIT_REF="${POWERPC_GCC_GIT_REF:-releases/gcc-16}"
GCC_GIT_COMMIT="${POWERPC_GCC_GIT_COMMIT:-}"

case "$GIT_OFFLINE" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_GIT_OFFLINE must be 0 or 1\n' >&2
        exit 1
        ;;
esac

if [[ ! -x "$CORE_BOOTSTRAP" ]]; then
    printf 'error: core PowerPC bootstrap is missing: %s\n' "$CORE_BOOTSTRAP" >&2
    exit 1
fi

for required in git tar xz shasum awk sed cut rm mkdir mv; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: official-Git bootstrap dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

for path in "$GIT_CACHE_DIR" "$GIT_EXPORT_DIR"; do
    case "$path" in
        *[' ':]*)
            printf 'error: Git cache and export paths cannot contain spaces or colons: %s\n' \
                "$path" >&2
            exit 1
            ;;
    esac
done
mkdir -p "$GIT_CACHE_DIR" "$GIT_EXPORT_DIR" "$TOOLCHAIN_DOWNLOAD_DIR"

prepare_mirror()
{
    local name="$1"
    local url="$2"
    local mirror="$GIT_CACHE_DIR/$name.git"

    if [[ ! -d "$mirror" ]]; then
        if [[ "$GIT_OFFLINE" == 1 ]]; then
            printf 'error: offline mode has no cached %s repository: %s\n' \
                "$name" "$mirror" >&2
            return 1
        fi
        git clone --mirror "$url" "$mirror"
    else
        git --git-dir="$mirror" remote set-url origin "$url"
        if [[ "$GIT_OFFLINE" != 1 ]]; then
            git --git-dir="$mirror" fetch --prune --tags origin \
                '+refs/heads/*:refs/heads/*'
        fi
    fi
    printf '%s\n' "$mirror"
}

resolve_commit()
{
    local mirror="$1"
    local ref="$2"
    local pinned="$3"
    local revision

    if [[ -n "$pinned" ]]; then
        revision="$pinned"
    else
        revision="$ref"
    fi
    git --git-dir="$mirror" rev-parse --verify "${revision}^{commit}"
}

export_repository()
{
    local mirror="$1"
    local commit="$2"
    local root_name="$3"
    local output_dir="$GIT_EXPORT_DIR/$root_name"

    rm -rf "$output_dir"
    mkdir -p "$output_dir"
    git --git-dir="$mirror" archive "$commit" |
        tar -xf - -C "$output_dir"
    printf '%s\n' "$output_dir"
}

make_source_archive()
{
    local source_dir="$1"
    local root_name="$2"
    local archive="$TOOLCHAIN_DOWNLOAD_DIR/$root_name.tar.xz"
    local temporary="$archive.tmp.$$"

    rm -f "$temporary"
    (
        cd "$(dirname "$source_dir")"
        tar -cf - "$(basename "$source_dir")" | xz -T0 -c > "$temporary"
    )
    mv -f "$temporary" "$archive"
    printf '%s\n' "$archive"
}

binutils_mirror="$(prepare_mirror binutils-gdb "$BINUTILS_GIT_URL")"
gcc_mirror="$(prepare_mirror gcc "$GCC_GIT_URL")"

binutils_commit="$(resolve_commit "$binutils_mirror" "$BINUTILS_GIT_REF" "$BINUTILS_GIT_COMMIT")"
gcc_commit="$(resolve_commit "$gcc_mirror" "$GCC_GIT_REF" "$GCC_GIT_COMMIT")"
binutils_short="$(printf '%s' "$binutils_commit" | cut -c1-12)"
gcc_short="$(printf '%s' "$gcc_commit" | cut -c1-12)"
binutils_version="git-$binutils_short"
gcc_version="git-$gcc_short"

binutils_export="$(export_repository "$binutils_mirror" "$binutils_commit" "binutils-$binutils_version")"
gcc_export="$(export_repository "$gcc_mirror" "$gcc_commit" "gcc-$gcc_version")"

if [[ ! -x "$gcc_export/contrib/gcc_update" ]]; then
    printf 'error: GCC Git export lacks contrib/gcc_update\n' >&2
    exit 1
fi
(
    cd "$gcc_export"
    ./contrib/gcc_update --touch
)

# The official binutils-gdb repository contains debugger-only components that
# are outside this firmware bootstrap. Keep the source tree intact; the core
# configure policy disables GDB, gdbserver, gprofng, gold, and the simulator.

binutils_archive="$(make_source_archive "$binutils_export" "binutils-$binutils_version")"
gcc_archive="$(make_source_archive "$gcc_export" "gcc-$gcc_version")"
binutils_sha="$(shasum -a 256 "$binutils_archive" | awk '{print $1}')"
gcc_sha="$(shasum -a 256 "$gcc_archive" | awk '{print $1}')"

printf '%s\n' \
    "binutils official Git: $BINUTILS_GIT_URL" \
    "binutils ref:          $BINUTILS_GIT_REF" \
    "binutils commit:       $binutils_commit" \
    "GCC official Git:      $GCC_GIT_URL" \
    "GCC ref:               $GCC_GIT_REF" \
    "GCC commit:            $gcc_commit"

export POWERPC_BINUTILS_VERSION="$binutils_version"
export POWERPC_BINUTILS_URL="file://$binutils_archive"
export POWERPC_BINUTILS_SHA256="$binutils_sha"
export POWERPC_GCC_VERSION="$gcc_version"
export POWERPC_GCC_URL="file://$gcc_archive"
export POWERPC_GCC_SHA256="$gcc_sha"
export POWERPC_TOOLCHAIN_SOURCE_DESCRIPTION="binutils=$binutils_commit gcc=$gcc_commit"

bash "$CORE_BOOTSTRAP" "$@"

cat > "$TOOLCHAIN_DIR/.whp-official-git-sources" <<MANIFEST
BINUTILS_GIT_URL=$BINUTILS_GIT_URL
BINUTILS_GIT_REF=$BINUTILS_GIT_REF
BINUTILS_GIT_COMMIT=$binutils_commit
BINUTILS_ARCHIVE_SHA256=$binutils_sha
GCC_GIT_URL=$GCC_GIT_URL
GCC_GIT_REF=$GCC_GIT_REF
GCC_GIT_COMMIT=$gcc_commit
GCC_ARCHIVE_SHA256=$gcc_sha
MANIFEST
