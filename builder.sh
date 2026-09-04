#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"

# builder.sh is the normalized stage runner, not a second public entry point.
# Redirect accidental direct invocations through build.sh so host policy cannot
# be bypassed.
if [[ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]]; then
    exec "$SOURCE_DIR/build.sh" "$@"
fi

# Exhaustive cross-platform syntax validation belongs in CI. Making every
# runtime build parse every macOS/firmware helper would let an irrelevant
# optional path reject an otherwise viable QEMU host. Keep the old validation
# available as an explicit diagnostic switch.
case "${WHP_RUNTIME_PREFLIGHT:-0}" in
    0) ;;
    1)
        source "$BUILD_SYSTEM_DIR/preflight.bash"
        whp_validate_build_scripts
        ;;
    *)
        printf 'error: WHP_RUNTIME_PREFLIGHT must be 0 or 1\n' >&2
        exit 1
        ;;
esac

# Keep module loading beside the execution order so the build has one
# production orchestrator.  The modules define stages; builder.sh owns how
# those stages are assembled and run.
source "$BUILD_SYSTEM_DIR/common.bash"
source "$BUILD_SYSTEM_DIR/prepare-build.bash"
source "$BUILD_SYSTEM_DIR/diagnostics.bash"
source "$BUILD_SYSTEM_DIR/prepare-sources.bash"
source "$BUILD_SYSTEM_DIR/prepare-seabios-grub.bash"
source "$BUILD_SYSTEM_DIR/prepare-mold.bash"
source "$BUILD_SYSTEM_DIR/host-cpu-tuning.bash"
source "$BUILD_SYSTEM_DIR/configure.bash"
source "$BUILD_SYSTEM_DIR/build-targets.bash"
source "$BUILD_SYSTEM_DIR/homebrew-deps.bash"

# CPU tuning belongs to QEMU host objects only. Remove inherited copies before
# any preparation stage so they cannot leak into firmware or bootstrap tools.
whp_strip_inherited_host_cpu_tuning

# Native LLVM replaces CC/CXX at the public build boundary because those
# variables select QEMU's host compiler. Remember whether the build-machine
# compiler variables were explicitly selected before defaults are filled in;
# firmware and bootstrap tools must not inherit QEMU's native LLVM by accident.
cc_for_build_was_set=0
cxx_for_build_was_set=0
objc_for_build_was_set=0
[[ -n "${CC_FOR_BUILD:-}" ]] && cc_for_build_was_set=1
[[ -n "${CXX_FOR_BUILD:-}" ]] && cxx_for_build_was_set=1
[[ -n "${OBJC_FOR_BUILD:-}" ]] && objc_for_build_was_set=1

# Preparation must see the requested build outputs.  A command such as
# `./build.sh qemu-system-ppc` is a run-specific request and must be able to
# expand an existing incremental build even when the saved PPC toggle is off.
whp_prepare_build "$@"

# Host optimization is a QEMU-only policy. Saved configuration is validated by
# config.py, but environment overrides bypass that parser and must be checked
# here before any expensive firmware/tool preparation starts.
QEMU_HOST_OPTIMIZATION="${QEMU_HOST_OPTIMIZATION:-3}"
case "$QEMU_HOST_OPTIMIZATION" in
    0|1|2|3|g|s) ;;
    *)
        printf '%s\n' \
            'error: QEMU_HOST_OPTIMIZATION must be one of: 0, 1, 2, 3, g, s' >&2
        exit 1
        ;;
esac
export QEMU_HOST_OPTIMIZATION

# macOS already pins build-machine tools to Apple Clang. On other hosts,
# whp_prepare_host_tools historically derived *_FOR_BUILD from CC/CXX; when
# BOOTSTRAP_NATIVE_LLVM is enabled that makes firmware helpers use QEMU's LLVM.
# Restore ordinary build-machine defaults only when the user did not select an
# explicit *_FOR_BUILD compiler, then refresh QEMU's configure arguments.
if [[ "${BOOTSTRAP_NATIVE_LLVM:-0}" == 1 && "$HOST_OS" != Darwin ]]; then
    native_llvm_build_compiler_reset=0
    if [[ "$cc_for_build_was_set" == 0 ]]; then
        CC_FOR_BUILD=cc
        export CC_FOR_BUILD
        native_llvm_build_compiler_reset=1
    fi
    if [[ "$cxx_for_build_was_set" == 0 ]]; then
        CXX_FOR_BUILD=c++
        export CXX_FOR_BUILD
        native_llvm_build_compiler_reset=1
    fi
    if [[ "$objc_for_build_was_set" == 0 ]]; then
        OBJC_FOR_BUILD="$CC_FOR_BUILD"
        export OBJC_FOR_BUILD
        native_llvm_build_compiler_reset=1
    fi
    if [[ "$native_llvm_build_compiler_reset" == 1 ]]; then
        whp_prepare_configure_args
    fi
fi

BUILD_QEMU_SYSTEM_SPARC="${BUILD_QEMU_SYSTEM_SPARC:-0}"
whp_require_boolean_values BUILD_QEMU_SYSTEM_SPARC
if [[ "$BUILD_QEMU_SYSTEM_SPARC" == 1 ]]; then
    whp_qemu_target_list_add sparc-softmmu
    whp_prepare_configure_args
fi
whp_apply_qemu_diagnostics
if [[ "$HOST_OS" == Darwin ]]; then
    whp_refresh_homebrew_dependency_identity
fi
if [[ "$HOST_OS" == Darwin && "$MACOS_ENABLE_GTK" == 1 ]]; then
    source "$SOURCE_DIR/scripts/macos-gtk-environment.bash"
    "$WHP_BUILD_BASH" --noprofile --norc \
        "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
fi
whp_prepare_seabios_grub_sources
whp_prepare_mold
# QEMU's Meson build owns the host optimization baseline. Strip inherited shell
# optimization, sanitizer, coverage, and anti-optimization flags here, after
# firmware/tool bootstraps, so they cannot silently slow the QEMU host binary.
whp_strip_inherited_host_performance_overrides
# Override Meson's upstream -O2 baseline through QEMU's supported host-only
# EXTRA_CFLAGS path. This is intentionally applied after firmware/tool setup so
# -O3 (or an explicit lower level) cannot alter OpenBIOS, SeaBIOS, LLVM, or mold.
configure_args+=(--extra-cflags="-O$QEMU_HOST_OPTIMIZATION")
# CPU code-generation flags belong to QEMU host objects only. Resolve and
# apply them after firmware/tool bootstraps so -march/-mcpu/-mtune cannot leak
# into SeaBIOS, OpenBIOS, LLVM bootstrap tools, or mold itself.
whp_prepare_host_cpu_tuning
whp_apply_host_cpu_tuning
if [[ "$HOST_OS" == Darwin ]]; then
    # Keep Homebrew's versioned Cellar kegs out of QEMU/Meson dependency state.
    # Apply this after firmware preparation so host pkg-config policy cannot
    # leak into SeaBIOS or OpenBIOS toolchains.
    whp_prepare_homebrew_pkg_config
fi
whp_configure_build
whp_build_targets "$@"

source "$BUILD_SYSTEM_DIR/post-build.bash"
whp_verify_build_outputs "$@"
