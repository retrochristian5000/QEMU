#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"

case "$TOOLCHAIN_TARGET" in
    powerpc-elf) ;;
    *)
        printf 'error: LLVM MC assembler stage currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

clang="$TOOLCHAIN_DIR/llvm/bin/clang"
llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
for required in "$clang" "$llvm_readelf"; do
    if [[ ! -x "$required" ]]; then
        printf 'error: LLVM MC assembler stage dependency is missing: %s\n' \
            "$required" >&2
        exit 1
    fi
done

public_as="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
target_as="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/as"
wrapper="$TOOLCHAIN_DIR/libexec/powerpc-llvm-mc-as"
marker="$TOOLCHAIN_DIR/.whp-powerpc-as"

mkdir -p "$(dirname "$public_as")" \
         "$(dirname "$target_as")" \
         "$(dirname "$wrapper")"

cat > "$wrapper" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$prefix/llvm/bin/clang" \
    --target=powerpc-none-elf \
    -fintegrated-as \
    -c -x assembler \
    "$@"
WRAPPER
chmod +x "$wrapper"
ln -sfn "../libexec/powerpc-llvm-mc-as" "$public_as"
ln -sfn "../../bin/${TOOLCHAIN_TARGET}-as" "$target_as"

smoke_dir="$TOOLCHAIN_WORK_DIR/mc-as-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/smoke.s" <<'SOURCE'
.text
.globl _start
_start:
    nop
SOURCE
"$public_as" -g -o "$smoke_dir/smoke.o" "$smoke_dir/smoke.s"

"$llvm_readelf" -hW "$smoke_dir/smoke.o" |
    grep -Eq 'Class:[[:space:]]+ELF32'
"$llvm_readelf" -hW "$smoke_dir/smoke.o" |
    grep -Eq "Data:[[:space:]]+2's complement, big endian"
"$llvm_readelf" -hW "$smoke_dir/smoke.o" |
    grep -Eq 'Machine:[[:space:]]+PowerPC'

for stale in \
    "$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/as.bfd" \
    "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as.bfd" \
    "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/as.bfd"; do
    if [[ -e "$stale" ]]; then
        printf 'error: GNU assembler fallback survived LLVM MC publication: %s\n' \
            "$stale" >&2
        exit 1
    fi
done

cat > "$marker" <<MARKER
AS_SCHEMA=1
ASSEMBLER=clang-integrated-mc
GNU_AS=disabled
TARGET=$TOOLCHAIN_TARGET
TRIPLE=powerpc-none-elf
OBJECT_ABI=ELF32-powerpc-big-endian
MARKER

printf 'PowerPC LLVM MC assembler: %s\n' "$public_as"
