#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
clang="$prefix/llvm/bin/clang"
tool_shims="$prefix/libexec/powerpc-clang-gnu"
translated=()
freestanding_link=0
compile_only=0
source_input=0
object_input=0

# OpenBIOS carries GCC/GNU-as-only PowerPC policy flags. Clang's bare-metal
# PowerPC ABI already uses static, non-small-data addressing for this lane, and
# -m64 selects PPC64 integrated-assembler mode without GNU as's -a64 switch.
# Keep this translation local to the compatibility driver so PPC-Firmware does
# not have to change during the compiler migration.
for arg in "$@"; do
    case "$arg" in
        -nostdlib) freestanding_link=1 ;;
        -c|-S|-E|-fsyntax-only|-M|-MM) compile_only=1 ;;
        *.c|*.cc|*.cpp|*.cxx|*.C|*.s|*.S|*.i|*.ii|-x) source_input=1 ;;
        *.o|*.a) object_input=1 ;;
    esac
    case "$arg" in
        -mcall-sysv-noeabi|-msdata=none|-G0|-Wa,-a64|\
        -Wbuiltin-declaration-mismatch|-Wmaybe-uninitialized|-Wno-maybe-uninitialized)
            ;;
        *)
            translated+=("$arg")
            ;;
    esac
done

# Generic GCC toolchains can delegate a bare-metal ELF link to host GCC,
# even when -print-prog-name=ld reports the private linker. Use Clang's
# direct bare-metal linker driver only for freestanding precompiled inputs.
# Keep the existing compilation triple (and hence the firmware C ABI).
if ((freestanding_link == 1 && compile_only == 0 && object_input == 1)); then
    if ((source_input == 1)); then
        printf '%s\n' 'error: compile PowerPC firmware sources separately before linking.' >&2
        exit 1
    fi
    exec "$clang" \
        --target=powerpc-unknown-none-eabi \
        --ld-path="$tool_shims/ld" \
        -B"$tool_shims" \
        "${translated[@]}"
fi

exec "$clang" \
    --target=powerpc-none-elf \
    -fintegrated-as \
    -B"$tool_shims" \
    "${translated[@]}"
