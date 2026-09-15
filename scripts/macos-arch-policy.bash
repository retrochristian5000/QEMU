#!/usr/bin/env bash

# Select the Apple Mach-O architecture used for QEMU host objects.  arm64e is
# an ABI variant of the AArch64 backend, not a separate LLVM target backend, so
# keep this policy independent from WHP_HOST_ARCH/LLVM_TARGETS_TO_BUILD.

whp_macos_arch_probe_arm64e()
{
    local compiler="$1"
    local sdkroot="$2"
    local deployment_target="$3"
    local output
    local compiler_command=()
    local linker_flag="${NATIVE_LLVM_LDFLAG:-}"

    read -r -a compiler_command <<< "$compiler"
    if [[ "${#compiler_command[@]}" -eq 0 ]]; then
        return 1
    fi

    output="$(mktemp "${TMPDIR:-/tmp}/whp-arm64e-probe.XXXXXX")" || return 1
    if printf 'int main(void) { return 0; }\n' |
       "${compiler_command[@]}" -arch arm64e \
           -isysroot "$sdkroot" \
           "-mmacosx-version-min=$deployment_target" \
           ${linker_flag:+"$linker_flag"} \
           -x c - -o "$output" >/dev/null 2>&1; then
        rm -f "$output"
        return 0
    fi

    rm -f "$output"
    return 1
}

whp_select_macos_arch()
{
    local compiler="$1"
    local sdkroot="$2"
    local deployment_target="$3"
    local process_arch="$4"
    local requested="${WHP_MACOS_ARCH:-auto}"
    local native_arch

    case "$requested" in
        auto|arm64|arm64e|x86_64) ;;
        *)
            printf 'error: WHP_MACOS_ARCH must be auto, arm64, arm64e, or x86_64: %s\n' \
                "$requested" >&2
            return 1
            ;;
    esac

    case "$process_arch" in
        arm64|aarch64) native_arch=arm64 ;;
        x86_64|amd64) native_arch=x86_64 ;;
        *)
            printf 'error: unsupported macOS process architecture: %s\n' \
                "$process_arch" >&2
            return 1
            ;;
    esac

    if [[ "$requested" == auto ]]; then
        if [[ "$native_arch" == arm64 ]] &&
           whp_macos_arch_probe_arm64e \
               "$compiler" "$sdkroot" "$deployment_target"; then
            printf 'arm64e\n'
        else
            printf '%s\n' "$native_arch"
        fi
        return 0
    fi

    case "$native_arch:$requested" in
        arm64:arm64|arm64:arm64e|x86_64:x86_64) ;;
        *)
            printf '%s\n' \
                'error: requested macOS architecture is not native to this process.' \
                "process:   $native_arch" \
                "requested: $requested" >&2
            return 1
            ;;
    esac

    if [[ "$requested" == arm64e ]] &&
       ! whp_macos_arch_probe_arm64e \
           "$compiler" "$sdkroot" "$deployment_target"; then
        printf '%s\n' \
            'error: requested arm64e, but the selected compiler/SDK/deployment target cannot link it.' \
            "compiler: $compiler" \
            "SDK:      $sdkroot" \
            "target:   $deployment_target" >&2
        return 1
    fi

    printf '%s\n' "$requested"
}
