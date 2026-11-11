#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
clang="$prefix/llvm/bin/clang"
tool_shims="$prefix/libexec/powerpc-clang-gnu"
translated=()

# OpenBIOS carries GCC/GNU-as-only PowerPC policy flags. Clang's bare-metal
# PowerPC ABI already uses static, non-small-data addressing for this lane, and
# -m64 selects PPC64 integrated-assembler mode without GNU as's -a64 switch.
# Keep this translation local to the compatibility driver so PPC-Firmware does
# not have to change during the compiler migration.
for arg in "$@"; do
    case "$arg" in
        -mcall-sysv-noeabi|-msdata=none|-G0|-Wa,-a64|\
        -Wbuiltin-declaration-mismatch|-Wmaybe-uninitialized|-Wno-maybe-uninitialized)
            ;;
        *)
            translated+=("$arg")
            ;;
    esac
done

exec "$clang" \
    --target=powerpc-none-elf \
    -fintegrated-as \
    -B"$tool_shims" \
    "${translated[@]}"
