#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

bootstrap="$root/scripts/bootstrap-i386-clang.sh"
prepare="$root/scripts/whp-build/prepare-sources.bash"
targets="$root/scripts/whp-build/build-targets.bash"
rom_makefile="$root/roms/Makefile"
meson="$root/pc-bios/meson.build"

[[ -f "$bootstrap" ]]
grep -q 'i386-none-elf' "$bootstrap"
grep -q 'LLVM_TARGETS_TO_BUILD=X86' "$bootstrap"
grep -q 'LLVM_DISTRIBUTION_COMPONENTS' "$bootstrap"
grep -q 'install-distribution' "$bootstrap"
grep -q 'seabios-minimal' "$bootstrap"
grep -q 'staged_toolchain' "$bootstrap"
grep -q 'old_toolchain' "$bootstrap"
grep -q 'ld.lld' "$bootstrap"
grep -q 'llvm-objcopy' "$bootstrap"
grep -q 'llvm-objdump' "$bootstrap"
grep -q 'llvm-strip' "$bootstrap"
grep -q -- '--version' "$bootstrap"
grep -Fq -- '-mpreferred-stack-boundary=2) args+=(-mstack-alignment=4) ;;' "$bootstrap"
grep -Fq -- '-fno-defer-pop|-fno-stack-protector-all|-fstack-check=no) ;;' "$bootstrap"
grep -Fq -- '-fwhole-program)' "$bootstrap"
grep -Fq -- 'SeaBIOS whole-program optimization is unsupported by Clang' "$bootstrap"
grep -Fq -- '-c|-S|-E) link_step=0 ;;' "$bootstrap"
grep -Fq -- 'driver_args+=(-fuse-ld=lld)' "$bootstrap"

# SeaBIOS does not consume these tools. Keep the i386 firmware bootstrap
# narrower than a general-purpose LLVM SDK.
for unused in llvm-ar llvm-nm llvm-readelf llvm-ranlib llvm-mc; do
    if grep -q "$unused" "$bootstrap"; then
        printf 'unexpected SeaBIOS LLVM tool: %s\n' "$unused" >&2
        exit 1
    fi
done

grep -q 'BUILD_SEABIOS' "$prepare"
grep -q 'BOOTSTRAP_I386_TOOLCHAIN' "$prepare"
grep -q 'roms/seabios' "$prepare"
grep -q '.whp-seabios-meson.env' "$prepare"

grep -q 'whp-seabios-x86' "$targets"
grep -q 'qemu-system-i386' "$targets"

grep -q 'SEABIOS_CROSS_PREFIX' "$rom_makefile"
grep -q 'CPP=$(SEABIOS_CROSS_PREFIX)cpp' "$rom_makefile"
grep -q 'whp-seabios-x86' "$meson"
grep -q '.whp-seabios-meson.env' "$meson"
