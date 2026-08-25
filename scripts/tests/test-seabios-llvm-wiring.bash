#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

bootstrap="$root/scripts/bootstrap-i386-clang.sh"
cc_helper="$root/scripts/whp-build/seabios-clang-gcc.bash"
objdump_helper="$root/scripts/whp-build/seabios-llvm-objdump.py"
prepare="$root/scripts/whp-build/prepare-sources.bash"
targets="$root/scripts/whp-build/build-targets.bash"
rom_makefile="$root/roms/Makefile"
meson="$root/pc-bios/meson.build"
meson_builder="$root/scripts/meson-build-seabios.sh"
seabios_config="$root/scripts/whp-build/configure-seabios.bash"
gitmodules="$root/.gitmodules"
seabios="$root/roms/seabios"

[[ -f "$seabios/Makefile" ]] || {
    printf 'SeaBIOS test source is not initialized: %s\n' "$seabios" >&2
    exit 1
}

[[ -f "$bootstrap" ]]
[[ -f "$cc_helper" ]]
[[ -f "$objdump_helper" ]]
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
grep -Fq -- 'BOOTSTRAP_SCHEMA=14' "$bootstrap"
grep -Fq -- 'COMPILER_ABI=seabios-gcc-i386-v1' "$bootstrap"
grep -Fq -- 'CC_COMPAT_HELPER=' "$bootstrap"
grep -Fq -- 'cp "$CC_COMPAT_HELPER" "$bin/$TOOLCHAIN_TARGET-gcc"' "$bootstrap"
grep -Fq -- 'mkdir -p "$(dirname "$TOOLCHAIN_DIR")" "$TOOLCHAIN_WORK_DIR"' "$bootstrap"

# Clang's i386 driver is wrapped only where SeaBIOS depends on GCC semantics
# that raw Clang does not provide or only accepts as ignored spellings.
grep -Fq -- '-mpreferred-stack-boundary=2)' "$cc_helper"
grep -Fq -- 'args+=(-mstack-alignment=4)' "$cc_helper"
grep -Fq -- '-fno-defer-pop|-fno-stack-protector-all|-fstack-check=no)' "$cc_helper"
grep -Fq -- '-fwhole-program)' "$cc_helper"
grep -Fq -- 'SeaBIOS whole-program optimization is unsupported by Clang' "$cc_helper"
grep -Fq -- '-fno-merge-constants)' "$cc_helper"
grep -Fq -- '-fmerge-constants)' "$cc_helper"
grep -Fq -- 'SHF_MERGE' "$cc_helper"
grep -Fq -- 'driver_args+=(-fuse-ld=lld)' "$cc_helper"

# A real i386-none-elf-ld defaults to the elf_i386 emulation. SeaBIOS relies
# on that for final linker-script links which omit an explicit -m option.
grep -Fq -- 'linker_args=(-m elf_i386)' "$bootstrap"
grep -Fq -- 'unsupported i386 linker emulation' "$bootstrap"
grep -Fq -- 'i386 linker default emulation' "$bootstrap"

# layoutrom.py consumes these relocation classes after SeaBIOS's ld -r stage,
# and the VGA link depends on garbage collection support.
grep -Fq -- 'R_386_PC32' "$bootstrap"
grep -Fq -- 'R_386_32' "$bootstrap"
grep -Fq -- '--gc-sections' "$bootstrap"

# SeaBIOS parses GNU objdump -thr output. The cross-tool must be a wrapper,
# not a raw llvm-objdump symlink, and it must restore the GNU alignment field.
grep -Fq -- 'OBJDUMP_ABI=gnu-seabios-thr' "$bootstrap"
grep -Fq -- 'seabios-llvm-objdump.py' "$bootstrap"
grep -Fq -- 'File off  Algn' "$objdump_helper"
grep -Fq -- '2**' "$objdump_helper"
if grep -Fq -- 'objdump:llvm-objdump' "$bootstrap"; then
    printf 'SeaBIOS objdump must not be a raw llvm-objdump symlink\n' >&2
    exit 1
fi

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

grep -Fq '[submodule "roms/seabios"]' "$gitmodules"
grep -Fq 'url = https://github.com/retrochristian5000/X86-Firmware.git' "$gitmodules"

grep -q 'SEABIOS_CROSS_PREFIX' "$rom_makefile"
grep -q 'CPP=$(SEABIOS_CROSS_PREFIX)cpp' "$rom_makefile"
grep -q 'SEABIOS_BUILD_ROOT' "$rom_makefile"
if grep -q 'seabios/builds' "$rom_makefile"; then
    printf 'SeaBIOS build state must not be written inside the submodule\n' >&2
    exit 1
fi
grep -q 'SEABIOS_BUILD_ROOT' "$seabios_config"
grep -q 'SEABIOS_BUILD_ROOT' "$meson_builder"
grep -q 'whp-seabios-x86' "$meson"
grep -q '.whp-seabios-meson.env' "$meson"

# QEMU resolves and exports a Python 3 interpreter before entering the
# firmware build. SeaBIOS must honor that explicit path instead of replacing
# it with the "python" command that modern macOS no longer provides. Its
# standalone fallback must likewise use the Python 3 command.
for required in make mktemp python3; do
    command -v "$required" >/dev/null 2>&1 || {
        printf 'missing SeaBIOS Python portability test tool: %s\n' "$required" >&2
        exit 1
    }
done

scratch="$(mktemp -d "${TMPDIR:-/tmp}/seabios-python.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/bin"
: > "$scratch/.config"

cat > "$scratch/check-python.mk" <<'MAKEFILE'
.PHONY: check-python-command
check-python-command:
	@$(PYTHON) -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'
MAKEFILE

cat > "$scratch/bin/python" <<'SCRIPT'
#!/bin/sh
printf 'SeaBIOS selected the obsolete python command\n' >&2
exit 127
SCRIPT

cat > "$scratch/bin/python3" <<'SCRIPT'
#!/bin/sh
exec "$SEABIOS_TEST_PYTHON" "$@"
SCRIPT
chmod +x "$scratch/bin/python" "$scratch/bin/python3"

selected_python="$(command -v python3)"
SEABIOS_TEST_PYTHON="$selected_python" \
PYTHON="$selected_python" \
PATH="$scratch/bin:$PATH" \
    make --no-print-directory -C "$seabios" \
        OUT="$scratch/explicit/" \
        KCONFIG_CONFIG="$scratch/.config" \
        -f Makefile -f "$scratch/check-python.mk" check-python-command

(
    unset PYTHON
    SEABIOS_TEST_PYTHON="$selected_python" \
    PATH="$scratch/bin:$PATH" \
        make --no-print-directory -C "$seabios" \
            OUT="$scratch/default/" \
            KCONFIG_CONFIG="$scratch/.config" \
            -f Makefile -f "$scratch/check-python.mk" check-python-command
)

# rom16.o and rom32seg.o are intermediate ELF containers, not boot entry
# images. Exercise their real Makefile rules with an LLD-compatible boundary
# double that reports the warning LLD emits when no entry address is given.
cat > "$scratch/bin/ld.lld" <<'SCRIPT'
#!/bin/sh
case " $* " in
    *' -e 0 '*) ;;
    *) printf 'ld.lld: warning: cannot find entry symbol _start; not setting start address\n' >&2 ;;
esac
while [ "$#" -gt 1 ]; do
    if [ "$1" = -o ]; then
        : > "$2"
        exit 0
    fi
    shift
done
exit 2
SCRIPT
chmod +x "$scratch/bin/ld.lld"

mkdir -p "$scratch/link-out"
for input in code16.o code32seg.o romlayout16.lds romlayout32seg.lds; do
    : > "$scratch/link-out/$input"
done

link_output="$({
    make --no-print-directory -C "$seabios" \
        OUT="$scratch/link-out/" \
        KCONFIG_CONFIG="$scratch/.config" \
        TESTGCC=2 LD="$scratch/bin/ld.lld" \
        -o "$scratch/link-out/code16.o" \
        -o "$scratch/link-out/code32seg.o" \
        -o "$scratch/link-out/romlayout16.lds" \
        -o "$scratch/link-out/romlayout32seg.lds" \
        "$scratch/link-out/rom16.o" "$scratch/link-out/rom32seg.o"
} 2>&1)"
if [[ "$link_output" == *'cannot find entry symbol _start'* ]]; then
    printf 'SeaBIOS intermediate links still trigger LLD entry warnings\n%s\n' \
        "$link_output" >&2
    exit 1
fi

# Compile-check every SeaBIOS C source with the same GCC-compatibility shim
# used by the i386 LLVM firmware lane. This is intentionally source-only: it
# catches front-end control-flow regressions without bootstrapping LLVM or
# invoking the firmware linker. Any -Wreturn-type diagnostic is a correctness
# failure because a caller may consume an indeterminate return value.
clang_bin="$(command -v clang-18 || command -v clang || true)"
lld_bin="$(command -v ld.lld-18 || command -v ld.lld || true)"
[[ -n "$clang_bin" ]] || {
    printf 'missing Clang for SeaBIOS return-type test\n' >&2
    exit 1
}
[[ -n "$lld_bin" ]] || {
    printf 'missing LLD for SeaBIOS build-environment probe\n' >&2
    exit 1
}
return_root="$scratch/return-types"
return_toolchain="$return_root/toolchain"
return_out="$return_root/out/"
return_config="$return_root/.config"
return_log="$return_root/compile.log"
mkdir -p "$return_toolchain/bin" "$return_toolchain/llvm/bin" "$return_out"
ln -s "$clang_bin" "$return_toolchain/llvm/bin/clang"
cp "$cc_helper" "$return_toolchain/bin/i386-none-elf-gcc"
chmod +x "$return_toolchain/bin/i386-none-elf-gcc"

make --no-print-directory -C "$seabios" \
    OUT="$return_out" KCONFIG_CONFIG="$return_config" HOSTCC=cc TESTGCC=2 \
    CC="$return_toolchain/bin/i386-none-elf-gcc" LD="$lld_bin" olddefconfig

set +e
make --no-print-directory -C "$seabios" \
    OUT="$return_out" KCONFIG_CONFIG="$return_config" HOSTCC=cc TESTGCC=2 \
    CC="$return_toolchain/bin/i386-none-elf-gcc" LD="$lld_bin" \
    "${return_out}ccode16.o" "${return_out}code32seg.o" \
    "${return_out}ccode32flat.o" >"$return_log" 2>&1
return_status=$?
set -e
if ((return_status != 0)); then
    cat "$return_log" >&2
    exit "$return_status"
fi
if grep -Fq '[-Wreturn-type]' "$return_log"; then
    printf 'SeaBIOS Clang return-type warning detected:\n' >&2
    grep -B3 -A3 -F '[-Wreturn-type]' "$return_log" >&2
    exit 1
fi