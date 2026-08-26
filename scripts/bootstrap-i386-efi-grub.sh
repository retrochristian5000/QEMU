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
TARGET_TRIPLE=i386-none-elf
I386_TOOLCHAIN_DIR="${I386_TOOLCHAIN_DIR:-$BUILD_ROOT/firmware-tools/i386-none-elf}"
I386_TOOLCHAIN_WORK_DIR="${I386_TOOLCHAIN_WORK_DIR:-$BUILD_ROOT/firmware-tools/toolchain-work/i386-none-elf}"
I386_LLVM_BUILD_DIR="${I386_LLVM_BUILD_DIR:-$I386_TOOLCHAIN_WORK_DIR/llvm-build}"
LLVM_BIN="${GRUB_I386_LLVM_BIN:-$I386_TOOLCHAIN_DIR/llvm/bin}"
I386_BOOTSTRAP="$SOURCE_DIR/scripts/bootstrap-i386-clang.sh"
BUILD_CC="${GRUB_I386_BUILD_CC:-${CC_FOR_BUILD:-}}"

case "$AUTO_INSTALL_DEPS" in 0|1) ;; *) printf 'error: GRUB_I386_AUTO_INSTALL_DEPS must be 0 or 1\n' >&2; exit 1 ;; esac
case "$FORCE_REBUILD" in 0|1) ;; *) printf 'error: GRUB_I386_FORCE_REBUILD must be 0 or 1\n' >&2; exit 1 ;; esac
case "$INSTALL_PREFIX" in /*) ;; *) printf 'error: GRUB_I386_INSTALL_PREFIX must be absolute: %s\n' "$INSTALL_PREFIX" >&2; exit 1 ;; esac
case "$I386_TOOLCHAIN_DIR" in /*) ;; *) printf 'error: I386_TOOLCHAIN_DIR must be absolute: %s\n' "$I386_TOOLCHAIN_DIR" >&2; exit 1 ;; esac
case "$LLVM_BIN" in /*) ;; *) printf 'error: GRUB_I386_LLVM_BIN must be absolute: %s\n' "$LLVM_BIN" >&2; exit 1 ;; esac

mkimage="$INSTALL_PREFIX/bin/i386-efi-grub-mkimage"
module_dir="$INSTALL_PREFIX/lib/$TARGET_TRIPLE/grub/i386-efi"
marker="$INSTALL_PREFIX/.whp-grub-i386-efi"
llvm_marker="$I386_TOOLCHAIN_DIR/.whp-i386-toolchain"

for tool in make tar mktemp cksum awk; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: IA32 EFI GRUB bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

prepare_homebrew_build_helpers()
{
    local dep dep_prefix

    [[ "$AUTO_INSTALL_DEPS" == 1 ]] || return 0
    command -v "$BREW_CMD" >/dev/null 2>&1 || return 0

    # These are ordinary source-build helpers. LLVM/LLD deliberately do not
    # belong here: GRUB consumes the QEMU fork's existing LLVM submodule build.
    "$BREW_CMD" install cmake ninja gawk help2man texinfo xz >/dev/null
    for dep in cmake ninja gawk help2man texinfo xz; do
        dep_prefix="$($BREW_CMD --prefix "$dep" 2>/dev/null || true)"
        [[ -z "$dep_prefix" || ! -d "$dep_prefix/bin" ]] || PATH="$dep_prefix/bin:$PATH"
    done
    export PATH
}

fork_primary_usable()
{
    local tool
    [[ -f "$llvm_marker" ]] || return 1
    for tool in clang ld.lld llvm-objcopy llvm-objdump llvm-strip; do
        [[ -x "$LLVM_BIN/$tool" ]] || return 1
    done
}

prepare_fork_llvm()
{
    local aux_bin="$I386_LLVM_BUILD_DIR/bin"

    if ! fork_primary_usable; then
        prepare_homebrew_build_helpers
        [[ -f "$I386_BOOTSTRAP" ]] || {
            printf 'error: WHP i386 LLVM bootstrap is missing: %s\n' "$I386_BOOTSTRAP" >&2
            exit 1
        }
        I386_TOOLCHAIN_DIR="$I386_TOOLCHAIN_DIR" \
        I386_TOOLCHAIN_WORK_DIR="$I386_TOOLCHAIN_WORK_DIR" \
        I386_LLVM_BUILD_DIR="$I386_LLVM_BUILD_DIR" \
        I386_LLVM_SUBMODULE_PATH="${I386_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}" \
        JOBS="$JOBS" \
            bash "$I386_BOOTSTRAP"
    fi

    fork_primary_usable || {
        printf 'error: WHP i386 LLVM toolchain is incomplete: %s\n' "$I386_TOOLCHAIN_DIR" >&2
        exit 1
    }

    llvm_nm="$LLVM_BIN/llvm-nm"
    llvm_ranlib="$LLVM_BIN/llvm-ranlib"
    if [[ -x "$llvm_nm" && -x "$llvm_ranlib" ]]; then
        return 0
    fi

    # SeaBIOS did not originally need nm/ranlib. Build only those two LLVM
    # utilities from the same persistent LLVM build graph when GRUB needs them;
    # do not create a second LLVM installation.
    prepare_homebrew_build_helpers
    command -v cmake >/dev/null 2>&1 || {
        printf 'error: cmake is required to extend the WHP LLVM fork for GRUB\n' >&2
        exit 1
    }
    [[ -f "$I386_LLVM_BUILD_DIR/CMakeCache.txt" ]] || {
        printf 'error: WHP LLVM build graph is missing: %s\n' "$I386_LLVM_BUILD_DIR" >&2
        exit 1
    }

    cmake_args=(--build "$I386_LLVM_BUILD_DIR" --target llvm-nm llvm-ar)
    if [[ -n "$JOBS" ]]; then
        case "$JOBS" in 0|*[!0-9]*) printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2; exit 1 ;; esac
        cmake_args+=(--parallel "$JOBS")
    else
        cmake_args+=(--parallel)
    fi
    cmake "${cmake_args[@]}"

    [[ -x "$aux_bin/llvm-nm" ]] || {
        printf 'error: WHP LLVM build did not produce llvm-nm\n' >&2
        exit 1
    }
    llvm_nm="$aux_bin/llvm-nm"

    if [[ -x "$aux_bin/llvm-ranlib" ]]; then
        llvm_ranlib="$aux_bin/llvm-ranlib"
    elif [[ -x "$aux_bin/llvm-ar" ]]; then
        mkdir -p "$WORK_DIR/llvm-aux-bin"
        llvm_ranlib="$WORK_DIR/llvm-aux-bin/llvm-ranlib"
        cat > "$llvm_ranlib" <<EOF_RANLIB
#!/usr/bin/env bash
set -euo pipefail
exec "$aux_bin/llvm-ar" s "\$@"
EOF_RANLIB
        chmod +x "$llvm_ranlib"
    else
        printf 'error: WHP LLVM build did not produce llvm-ar/llvm-ranlib\n' >&2
        exit 1
    fi
}

prepare_fork_llvm
llvm_toolchain_id="$(cksum "$llvm_marker" | awk '{printf "%s:%s", $1, $2}')"
clang="$LLVM_BIN/clang"
llvm_objcopy="$LLVM_BIN/llvm-objcopy"
llvm_strip="$LLVM_BIN/llvm-strip"

if [[ -z "$BUILD_CC" ]]; then
    BUILD_CC="$(command -v cc 2>/dev/null || command -v clang 2>/dev/null || true)"
fi
[[ -n "$BUILD_CC" && -x "$BUILD_CC" ]] || {
    printf 'error: host C compiler not found for GRUB build utilities\n' >&2
    exit 1
}

# Resolve the GRUB source identity before accepting an existing image. Homebrew
# is only a source provider here; no Homebrew GCC/binutils/LLVM target toolchain
# is installed or consumed.
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
BOOTSTRAP_SCHEMA=4
FORMULA=$FORMULA
SOURCE_CKSUM=$source_id
TARGET=$TARGET_TRIPLE
PLATFORM=i386-efi
PROGRAM_PREFIX=i386-efi-
TOOLCHAIN=whp-llvm-fork
LLVM_TOOLCHAIN_CKSUM=$llvm_toolchain_id
LLVM_BIN=$LLVM_BIN
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
: > "$grub_source/grub-core/extra_deps.lst"

configure_args=(
    --disable-werror
    --disable-nls
    --target="$TARGET_TRIPLE"
    --with-platform=efi
    --program-prefix=i386-efi-
    --prefix="$INSTALL_PREFIX/$TARGET_TRIPLE"
    --bindir="$INSTALL_PREFIX/bin"
    --libdir="$INSTALL_PREFIX/lib/$TARGET_TRIPLE"
)
(
    cd "$build_root"

    # Keep macOS host flags on the host side. The target side is selected only
    # by Clang's bare-metal triple, so -arch/-mmacosx-version-min cannot reach
    # an ELF compiler again.
    PATH="$LLVM_BIN:$(dirname "$llvm_nm"):$PATH" \
    CFLAGS= \
    CPPFLAGS= \
    LDFLAGS= \
    BUILD_CFLAGS= \
    BUILD_CPPFLAGS= \
    BUILD_LDFLAGS= \
    HOST_CFLAGS= \
    HOST_CPPFLAGS= \
    HOST_LDFLAGS= \
    CC="$BUILD_CC" \
    BUILD_CC="$BUILD_CC" \
    HOST_CC="$BUILD_CC" \
    TARGET_CC="$clang" \
    TARGET_CFLAGS="-Os --target=$TARGET_TRIPLE" \
    TARGET_CPPFLAGS="--target=$TARGET_TRIPLE" \
    TARGET_CCASFLAGS="--target=$TARGET_TRIPLE" \
    TARGET_LDFLAGS="--target=$TARGET_TRIPLE -fuse-ld=lld" \
    TARGET_OBJCOPY="$llvm_objcopy" \
    TARGET_NM="$llvm_nm" \
    TARGET_RANLIB="$llvm_ranlib" \
    TARGET_STRIP="$llvm_strip" \
        "$grub_source/configure" "${configure_args[@]}"
)

make_args=()
if [[ -n "$JOBS" ]]; then
    case "$JOBS" in 0|*[!0-9]*) printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2; exit 1 ;; esac
    make_args=(-j"$JOBS")
fi
PATH="$LLVM_BIN:$(dirname "$llvm_nm"):$PATH" \
    make -C "$build_root" "${make_args[@]}"
PATH="$LLVM_BIN:$(dirname "$llvm_nm"):$PATH" \
    DESTDIR="$stage_root" make -C "$build_root" install

staged="$stage_root$INSTALL_PREFIX"
staged_mkimage="$staged/bin/i386-efi-grub-mkimage"
staged_modules="$staged/lib/$TARGET_TRIPLE/grub/i386-efi"
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
