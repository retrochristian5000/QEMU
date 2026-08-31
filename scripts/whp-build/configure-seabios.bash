#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DIR:?SOURCE_DIR is required}"
: "${BUILD_DIR:?BUILD_DIR is required}"
: "${MAKE_CMD:?GNU Make is required for SeaBIOS}"

SEABIOS_DIR="${SEABIOS_DIR:-$SOURCE_DIR/roms/seabios}"
SEABIOS_CONFIG_FILE="$BUILD_DIR/.whp-seabios-meson.env"
SEABIOS_BUILD_ROOT="${SEABIOS_BUILD_ROOT:-$BUILD_DIR/firmware-build/seabios}"
I386_TOOLCHAIN_DIR="${I386_TOOLCHAIN_DIR:-$BUILD_DIR/firmware-tools/i386-none-elf}"
BOOTSTRAP_I386_TOOLCHAIN="${BOOTSTRAP_I386_TOOLCHAIN:-auto}"
I386_TOOLCHAIN_FORCE_REBUILD="${I386_TOOLCHAIN_FORCE_REBUILD:-0}"
I386_LLVM_SUBMODULE_PATH="${I386_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"

if [[ ! -f "$SEABIOS_DIR/Makefile" ]]; then
    printf 'error: SeaBIOS source is not initialized: %s\n' "$SEABIOS_DIR" >&2
    exit 1
fi

case "$SEABIOS_BUILD_ROOT/" in
    "$SEABIOS_DIR/"*)
        printf 'error: SeaBIOS build root must remain outside the submodule: %s\n' \
            "$SEABIOS_BUILD_ROOT" >&2
        exit 1
        ;;
esac

case "$BOOTSTRAP_I386_TOOLCHAIN" in
    auto)
        [[ -n "${SEABIOS_CROSS_COMPILE:-}" ]] && BOOTSTRAP_I386_TOOLCHAIN=0 || BOOTSTRAP_I386_TOOLCHAIN=1
        ;;
    0|1) ;;
    *) printf 'error: BOOTSTRAP_I386_TOOLCHAIN must be auto, 0, or 1\n' >&2; exit 1 ;;
esac

bootstrap_i386_toolchain()
{
    local force_rebuild="$1"

    I386_TOOLCHAIN_DIR="$I386_TOOLCHAIN_DIR" \
    I386_TOOLCHAIN_WORK_DIR="${I386_TOOLCHAIN_WORK_DIR:-$BUILD_DIR/firmware-tools/toolchain-work/i386-none-elf}" \
    I386_TOOLCHAIN_FORCE_REBUILD="$force_rebuild" \
    I386_LLVM_SUBMODULE_PATH="$I386_LLVM_SUBMODULE_PATH" \
    JOBS="${JOBS:-}" \
        bash "$SOURCE_DIR/scripts/bootstrap-i386-clang.sh"
}

if [[ "$BOOTSTRAP_I386_TOOLCHAIN" == 1 ]]; then
    bootstrap_i386_toolchain "$I386_TOOLCHAIN_FORCE_REBUILD"

    # A matching marker plus a plain compile cannot detect a mixed LLVM cache
    # whose frontend knows the modern non-leaf frame-pointer mode while its
    # verifier does not. Exercise the exact producer path before SeaBIOS uses
    # the compiler; a failure forces the bootstrap's existing clean rebuild.
    i386_clang="$I386_TOOLCHAIN_DIR/llvm/bin/clang"
    if ! printf 'int whp_i386_frame_pointer(void) { return 0; }\n' |
         "$i386_clang" --target=i386-none-elf -m32 -march=i386 \
             -fno-omit-frame-pointer -momit-leaf-frame-pointer \
             -ffreestanding -x c -c - -o /dev/null >/dev/null 2>&1; then
        printf '%s\n' \
            'i386 LLVM cache failed the frame-pointer verifier probe; rebuilding.' >&2
        bootstrap_i386_toolchain 1
    fi

    SEABIOS_CROSS_COMPILE="$I386_TOOLCHAIN_DIR/bin/i386-none-elf-"
fi

: "${SEABIOS_CROSS_COMPILE:?SeaBIOS needs SEABIOS_CROSS_COMPILE or BOOTSTRAP_I386_TOOLCHAIN=1}"
for tool in gcc cpp as ld objcopy objdump strip; do
    [[ -x "${SEABIOS_CROSS_COMPILE}${tool}" ]] || {
        printf 'error: SeaBIOS cross tool is missing: %s%s\n' "$SEABIOS_CROSS_COMPILE" "$tool" >&2
        exit 1
    }
done

mkdir -p "$BUILD_DIR"
tmp="$SEABIOS_CONFIG_FILE.new"
cat >"$tmp" <<EOF
SEABIOS_DIR=$SEABIOS_DIR
SEABIOS_BUILD_ROOT=$SEABIOS_BUILD_ROOT
SEABIOS_CROSS_COMPILE=$SEABIOS_CROSS_COMPILE
MAKE_CMD=$MAKE_CMD
EOF
if [[ -f "$SEABIOS_CONFIG_FILE" ]] && cmp -s "$tmp" "$SEABIOS_CONFIG_FILE"; then
    rm -f "$tmp"
else
    mv "$tmp" "$SEABIOS_CONFIG_FILE"
fi
