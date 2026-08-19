#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
base="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
mc_stage="$ROOT/scripts/bootstrap-powerpc-llvm-mc.sh"
nm_stage="$ROOT/scripts/bootstrap-powerpc-llvm-nm.sh"
strip_stage="$ROOT/scripts/bootstrap-powerpc-llvm-strip.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"
build_openbios="$ROOT/scripts/build-openbios.sh"
meson_openbios="$ROOT/scripts/meson-build-openbios.sh"
configure_openbios="$ROOT/scripts/whp-build/configure-openbios.bash"
openbios_target="$ROOT/roms/openbios/Makefile.target"
openbios_rules="$ROOT/roms/openbios/config/xml/rules.xml"
openbios_objects="$ROOT/roms/openbios/config/xml/object.xsl"
openbios_ppc_build="$ROOT/roms/openbios/arch/ppc/build.xml"
openbios_libgcc_build="$ROOT/roms/openbios/libgcc/build.xml"
gitmodules="$ROOT/.gitmodules"

# Normal QEMU builds are pinned by the LLVM gitlink.  If .gitmodules names a
# tracking branch, it may only name the LLVM repository's default branch.
llvm_module="$(awk '
    /^\[submodule "toolchains\/llvm-project"\]$/ { in_llvm=1; next }
    /^\[submodule / { if (in_llvm) exit }
    in_llvm { print }
' "$gitmodules")"
llvm_branch="$(awk -F= '
    /^[[:space:]]*branch[[:space:]]*=/ {
        value=$2
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' <<< "$llvm_module")"
case "$llvm_branch" in
    ''|main) ;;
    *)
        printf 'error: LLVM submodule tracks a non-default branch: %s\n' "$llvm_branch" >&2
        exit 1
        ;;
esac
grep -Fq 'LLVM_GIT_REF="${POWERPC_LLVM_GIT_REF:-HEAD}"' "$base"
grep -Fq 'LLVM_GIT_COMMIT="${POWERPC_LLVM_GIT_COMMIT:-}"' "$base"

# The OpenBIOS Clang lane is LLVM-only. In particular, do not keep a partial
# GNU BFD build: current binutils couples BFD to libsframe even when OpenBIOS
# never emits or consumes SFrame unwind metadata.
grep -Fq 'BOOTSTRAP_SCHEMA=16' "$base"
grep -Fq 'GNU_BINUTILS=disabled' "$base"
grep -Fq 'SFRAME=disabled' "$base"
for binutils_token in BINUTILS_VERSION BINUTILS_URL BINUTILS_SHA256 \
                      binutils_src build-binutils --disable-gas libsframe; do
    if grep -Fq -- "$binutils_token" "$base"; then
        printf 'error: LLVM-only Clang base still references %s\n' \
            "$binutils_token" >&2
        exit 1
    fi
done
if grep -Fq -- '-fno-integrated-as' "$base"; then
    printf 'error: PowerPC Clang wrapper still disables the integrated assembler\n' >&2
    exit 1
fi
grep -Fq -- '-fintegrated-as' "$base"
if grep -Fq 'ln -sf "../../bin/${TOOLCHAIN_TARGET}-as" "$shim_dir/as"' "$base"; then
    printf 'error: base bootstrap still wires a private GNU assembler shim\n' >&2
    exit 1
fi

grep -Fq 'LLD_SCHEMA=4' "$core"
grep -Fq 'ASSEMBLER=clang-integrated' "$core"
grep -Fq 'GNU_BINUTILS=disabled' "$core"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$core"
if grep -Fq 'ld.bfd' "$core" || grep -Fq 'GNU ld' "$core"; then
    printf 'error: LLD stage still retains a GNU linker fallback\n' >&2
    exit 1
fi

# The old standalone-as implementation is forbidden. The replacement is a
# narrow LLVM-MC publication stage over the already-proven Clang IAS.
if [[ -e "$ROOT/scripts/bootstrap-powerpc-llvm-as.sh" ]] ||
   grep -Fq 'bootstrap-powerpc-llvm-as.sh' "$orchestrator"; then
    printf 'error: obsolete standalone PowerPC as stage remains wired\n' >&2
    exit 1
fi
grep -Fq 'AS_SCHEMA=1' "$mc_stage"
grep -Fq 'ASSEMBLER=clang-integrated-mc' "$mc_stage"
grep -Fq 'GNU_AS=disabled' "$mc_stage"
grep -Fq -- '--target=powerpc-none-elf' "$mc_stage"
grep -Fq -- '-fintegrated-as' "$mc_stage"
grep -Fq -- '-c -x assembler' "$mc_stage"
grep -Fq 'OBJECT_ABI=ELF32-powerpc-big-endian' "$mc_stage"
grep -Fq 'bootstrap-powerpc-llvm-mc.sh' "$orchestrator"
grep -Fq 'rm -f "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"' "$orchestrator"
grep -Fq 'rm -f "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/as"' "$orchestrator"

# OpenBIOS's active XML-generated target-object graph compiles .S through CC.
# That gives Clang ownership of both preprocessing and integrated assembly;
# the legacy arch/ppc/Makefile.asm pipeline is not the qemu-ppc object graph.
grep -Fq 'CC     := $(TARGET)gcc' "$openbios_target"
grep -Fq '$(CC) $$EXTRACFLAGS $(CFLAGS) $(INCLUDES) $(DEPFLAGS) -c -o $@ $&lt;' \
    "$openbios_rules"
grep -Fq "document('rules.xml',.)//rule[@target=\$target][@entity='object']" \
    "$openbios_objects"
if grep -Fq '$(AS)' "$openbios_rules" ||
   grep -Fq 'AS     := $(TARGET)as' "$openbios_target"; then
    printf 'error: active OpenBIOS object graph still dispatches through standalone as\n' >&2
    exit 1
fi

# Keep the corpus list explicit so adding, removing, or rerouting PPC assembly
# cannot silently escape the LLVM integrated-assembler qualification lane.
grep -Fq '<object source="qemu/start.S"/>' "$openbios_ppc_build"
grep -Fq '<object source="qemu/switch.S"/>' "$openbios_ppc_build"
grep -Fq '<object source="timebase.S"/>' "$openbios_ppc_build"
grep -Fq '<object source="crtsavres.S" condition="PPC"/>' "$openbios_libgcc_build"

# OpenBIOS intentionally consumes the compiler driver rather than making the
# separately published assembler part of its required cross-prefix contract.
grep -Fq 'powerpc_tools=(gcc ar ld nm strip ranlib)' "$build_openbios"
grep -Fq 'for tool in gcc ar ld nm strip ranlib; do' "$meson_openbios"
grep -Fq 'POWERPC_TOOLCHAIN_COMPILER="${POWERPC_TOOLCHAIN_COMPILER:-clang}"' \
    "$build_openbios"
grep -Fq 'compiler_mode="${POWERPC_TOOLCHAIN_COMPILER:-clang}"' \
    "$meson_openbios"
grep -Fq 'compiler_mode="${POWERPC_TOOLCHAIN_COMPILER:-clang}"' \
    "$configure_openbios"
grep -Fq 'bootstrap-powerpc-clang.sh' "$build_openbios"
if grep -Fq 'powerpc_tools=(gcc as ar ld nm strip ranlib)' "$build_openbios" ||
   grep -Fq 'for tool in gcc as ar ld nm strip ranlib; do' "$meson_openbios"; then
    printf 'error: OpenBIOS tool contract depends on standalone as\n' >&2
    exit 1
fi
if grep -Fq 'bash "$SOURCE_DIR/scripts/bootstrap-powerpc-toolchain.sh"' \
       "$build_openbios"; then
    printf 'error: standalone OpenBIOS still unconditionally selects GNU tools\n' >&2
    exit 1
fi
if grep -Fq 'compiler_mode" == clang && "$source_mode" != release' \
       "$meson_openbios" ||
   grep -Fq 'compiler_mode" == clang && "$source_mode" != release' \
       "$configure_openbios"; then
    printf 'error: LLVM submodule lane is still coupled to GNU source mode\n' >&2
    exit 1
fi

# The existing utility stages still use the compiler IAS directly in this
# slice. Their migration to the public assembler can follow after publication
# is proven, without mixing failures between interfaces.
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$nm_stage"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$strip_stage"
if grep -Fq 'public_as=' "$nm_stage" || grep -Fq 'public_as=' "$strip_stage"; then
    printf 'error: LLVM utility qualification moved to public as before its smoke\n' >&2
    exit 1
fi

printf 'PowerPC LLVM assembler wiring: verified\n'
