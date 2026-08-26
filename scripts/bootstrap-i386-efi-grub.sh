#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BUILD_ROOT="${BUILD_DIR:-$SOURCE_DIR/build}"
INSTALL_PREFIX="${GRUB_I386_INSTALL_PREFIX:-$BUILD_ROOT/firmware-tools/grub-i386-efi}"
WORK_DIR="${GRUB_I386_WORK_DIR:-$BUILD_ROOT/toolchain-work/grub-i386-efi}"
FORMULA="${GRUB_I386_SOURCE_FORMULA:-i686-elf-grub}"
BREW_CMD="${GRUB_I386_BREW:-${WHP_HOMEBREW_BREW:-brew}}"
AUTO_INSTALL_DEPS="${GRUB_I386_AUTO_INSTALL_DEPS:-1}"
FORCE_REBUILD="${GRUB_I386_FORCE_REBUILD:-0}"
JOBS="${JOBS:-}"

case "$AUTO_INSTALL_DEPS" in 0|1) ;; *) printf 'error: GRUB_I386_AUTO_INSTALL_DEPS must be 0 or 1\n' >&2; exit 1 ;; esac
case "$FORCE_REBUILD" in 0|1) ;; *) printf 'error: GRUB_I386_FORCE_REBUILD must be 0 or 1\n' >&2; exit 1 ;; esac
case "$INSTALL_PREFIX" in /*) ;; *) printf 'error: GRUB_I386_INSTALL_PREFIX must be absolute: %s\n' "$INSTALL_PREFIX" >&2; exit 1 ;; esac

mkimage="$INSTALL_PREFIX/bin/i386-efi-grub-mkimage"
module_dir="$INSTALL_PREFIX/lib/i686-elf/grub/i386-efi"
marker="$INSTALL_PREFIX/.whp-grub-i386-efi"

for tool in make tar mktemp cksum awk; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: IA32 EFI GRUB bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

# Resolve the source identity before accepting an existing tool. This is the
# cache's Homebrew-upgrade guard: a formula source update must invalidate an
# otherwise healthy old i386-efi build instead of silently reusing it.
archive="${GRUB_I386_SOURCE_ARCHIVE:-}"
if [[ -z "$archive" ]]; then
    command -v "$BREW_CMD" >/dev/null 2>&1 || {
        printf 'error: Homebrew is required to resolve the GRUB source archive\n' >&2
        exit 1
    }
    archive="$($BREW_CMD --cache --build-from-source "$FORMULA" 2>/dev/null || true)"
    if [[ -z "$archive" || ! -f "$archive" ]]; then
        "$BREW_CMD" fetch --build-from-source "$FORMULA" >/dev/null
        archive="$($BREW_CMD --cache --build-from-source "$FORMULA")"
    fi
fi
[[ -f "$archive" ]] || {
    printf 'error: IA32 EFI GRUB source archive is missing: %s\n' "$archive" >&2
    exit 1
}
source_id="$(cksum "$archive" | awk '{printf "%s:%s", $1, $2}')"
expected_marker="$(cat <<EOF_MARKER
BOOTSTRAP_SCHEMA=2
FORMULA=$FORMULA
SOURCE_CKSUM=$source_id
TARGET=i686-elf
PLATFORM=i386-efi
PROGRAM_PREFIX=i386-efi-
EOF_MARKER
)"

usable()
{
    [[ -x "$mkimage" && -f "$module_dir/moddep.lst" && -f "$marker" ]] || return 1
    [[ "$(cat "$marker")" == "$expected_marker" ]] || return 1
    "$mkimage" --version >/dev/null 2>&1
}

if [[ "$FORCE_REBUILD" == 0 ]] && usable; then
    printf 'IA32 EFI GRUB is current: %s\n' "$INSTALL_PREFIX"
    exit 0
fi

need_cross=0
for tool in i686-elf-gcc i686-elf-ld i686-elf-objcopy i686-elf-nm i686-elf-ranlib i686-elf-strip; do
    command -v "$tool" >/dev/null 2>&1 || need_cross=1
done

if [[ "$need_cross" == 1 && "$AUTO_INSTALL_DEPS" == 1 ]]; then
    command -v "$BREW_CMD" >/dev/null 2>&1 || {
        printf 'error: Homebrew is required to install the IA32 EFI GRUB cross tools\n' >&2
        exit 1
    }
    "$BREW_CMD" install i686-elf-binutils i686-elf-gcc gawk help2man texinfo xz
    for dep in i686-elf-binutils i686-elf-gcc gawk help2man texinfo xz; do
        dep_prefix="$($BREW_CMD --prefix "$dep" 2>/dev/null || true)"
        [[ -z "$dep_prefix" || ! -d "$dep_prefix/bin" ]] || PATH="$dep_prefix/bin:$PATH"
    done
    export PATH
fi

for tool in i686-elf-gcc i686-elf-ld i686-elf-objcopy i686-elf-nm i686-elf-ranlib i686-elf-strip; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: IA32 EFI GRUB cross tool not found after dependency preparation: %s\n' "$tool" >&2
        exit 1
    }
done

source_root="$WORK_DIR/source"
build_root="$WORK_DIR/build"
stage_root="$WORK_DIR/install-root.$$"
rm -rf "$source_root" "$build_root" "$stage_root"
mkdir -p "$source_root" "$build_root" "$stage_root" "$(dirname "$INSTALL_PREFIX")"
tar -xf "$archive" -C "$source_root"

set -- "$source_root"/*
[[ $# -eq 1 && -d "$1" && -x "$1/configure" ]] || {
    printf 'error: GRUB archive did not unpack to one configured source tree\n' >&2
    exit 1
}
grub_source="$1"

configure_args=(
    --disable-werror
    --disable-nls
    --target=i686-elf
    --with-platform=efi
    --program-prefix=i386-efi-
    --prefix="$INSTALL_PREFIX/i686-elf"
    --bindir="$INSTALL_PREFIX/bin"
    --libdir="$INSTALL_PREFIX/lib/i686-elf"
)
(
    cd "$build_root"
    "$grub_source/configure" "${configure_args[@]}"
)

make_args=()
if [[ -n "$JOBS" ]]; then
    case "$JOBS" in 0|*[!0-9]*) printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2; exit 1 ;; esac
    make_args=(-j"$JOBS")
fi
make -C "$build_root" "${make_args[@]}"
DESTDIR="$stage_root" make -C "$build_root" install

staged="$stage_root$INSTALL_PREFIX"
staged_mkimage="$staged/bin/i386-efi-grub-mkimage"
staged_modules="$staged/lib/i686-elf/grub/i386-efi"
[[ -x "$staged_mkimage" && -f "$staged_modules/moddep.lst" ]] || {
    printf 'error: GRUB EFI build did not produce the IA32 mkimage/module ABI\n' >&2
    exit 1
}
"$staged_mkimage" --version >/dev/null
smoke="$WORK_DIR/i386-efi-smoke.efi"
"$staged_mkimage" -O i386-efi -d "$staged_modules" -o "$smoke" normal part_gpt
[[ -s "$smoke" ]] || {
    printf 'error: IA32 grub-mkimage smoke image was not produced\n' >&2
    exit 1
}

printf '%s\n' "$expected_marker" > "$staged/.whp-grub-i386-efi"

replacement="$INSTALL_PREFIX.new.$$"
rm -rf "$replacement"
mv "$staged" "$replacement"
rm -rf "$INSTALL_PREFIX"
mv "$replacement" "$INSTALL_PREFIX"
rm -rf "$stage_root"

usable || {
    printf 'error: installed IA32 EFI GRUB failed post-install validation\n' >&2
    exit 1
}
printf 'IA32 EFI GRUB: %s\n' "$INSTALL_PREFIX"
printf 'GRUB_I386_MKIMAGE=%s\n' "$mkimage"
printf 'GRUB_I386_MODULE_DIR=%s\n' "$module_dir"
