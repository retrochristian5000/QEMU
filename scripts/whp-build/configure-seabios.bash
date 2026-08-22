#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DIR:?SOURCE_DIR is required}"
: "${BUILD_DIR:?BUILD_DIR is required}"
: "${MAKE_CMD:?GNU Make is required for SeaBIOS}"

SEABIOS_DIR="${SEABIOS_DIR:-$SOURCE_DIR/roms/seabios}"
SEABIOS_CONFIG_FILE="$BUILD_DIR/.whp-seabios-meson.env"
I386_TOOLCHAIN_DIR="${I386_TOOLCHAIN_DIR:-$BUILD_DIR/firmware-tools/i386-none-elf}"
BOOTSTRAP_I386_TOOLCHAIN="${BOOTSTRAP_I386_TOOLCHAIN:-auto}"
I386_TOOLCHAIN_FORCE_REBUILD="${I386_TOOLCHAIN_FORCE_REBUILD:-0}"
I386_LLVM_SUBMODULE_PATH="${I386_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"

if [[ ! -f "$SEABIOS_DIR/Makefile" ]]; then
    printf 'error: SeaBIOS source is not initialized: %s\n' "$SEABIOS_DIR" >&2
    exit 1
fi

case "$BOOTSTRAP_I386_TOOLCHAIN" in
    auto)
        [[ -n "${SEABIOS_CROSS_COMPILE:-}" ]] && BOOTSTRAP_I386_TOOLCHAIN=0 || BOOTSTRAP_I386_TOOLCHAIN=1
        ;;
    0|1) ;;
    *) printf 'error: BOOTSTRAP_I386_TOOLCHAIN must be auto, 0, or 1\n' >&2; exit 1 ;;
esac

if [[ "$BOOTSTRAP_I386_TOOLCHAIN" == 1 ]]; then
    I386_TOOLCHAIN_DIR="$I386_TOOLCHAIN_DIR" \
    I386_TOOLCHAIN_WORK_DIR="${I386_TOOLCHAIN_WORK_DIR:-$BUILD_DIR/firmware-tools/toolchain-work/i386-none-elf}" \
    I386_TOOLCHAIN_FORCE_REBUILD="$I386_TOOLCHAIN_FORCE_REBUILD" \
    I386_LLVM_SUBMODULE_PATH="$I386_LLVM_SUBMODULE_PATH" \
    JOBS="${JOBS:-}" \
        bash "$SOURCE_DIR/scripts/bootstrap-i386-clang.sh"
    SEABIOS_CROSS_COMPILE="$I386_TOOLCHAIN_DIR/bin/i386-none-elf-"
fi

: "${SEABIOS_CROSS_COMPILE:?SeaBIOS needs SEABIOS_CROSS_COMPILE or BOOTSTRAP_I386_TOOLCHAIN=1}"
for tool in gcc as ld ar nm objcopy objdump readelf strip ranlib; do
    [[ -x "${SEABIOS_CROSS_COMPILE}${tool}" ]] || {
        printf 'error: SeaBIOS cross tool is missing: %s%s\n' "$SEABIOS_CROSS_COMPILE" "$tool" >&2
        exit 1
    }
done

mkdir -p "$BUILD_DIR"
tmp="$SEABIOS_CONFIG_FILE.new"
cat >"$tmp" <<EOF
SEABIOS_DIR=$SEABIOS_DIR
SEABIOS_CROSS_COMPILE=$SEABIOS_CROSS_COMPILE
MAKE_CMD=$MAKE_CMD
EOF
mv "$tmp" "$SEABIOS_CONFIG_FILE"
