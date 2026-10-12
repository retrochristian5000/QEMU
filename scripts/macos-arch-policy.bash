#!/usr/bin/env bash

# Select the Apple Mach-O architecture used for QEMU host objects.  arm64e is
# an ABI variant of the AArch64 backend, not a separate LLVM target backend, so
# keep this policy independent from WHP_HOST_ARCH/LLVM_TARGETS_TO_BUILD.
#
# QEMU's TCG JIT still needs explicit arm64e pointer-authentication handling at
# both C -> JIT and JIT -> C call boundaries.  Keep auto on the established
# arm64 ABI until those paths execute translated guest code under CI.  Explicit
# arm64e remains available as a probe-gated audit/development lane.

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
    # A successful -arch arm64e link alone cannot prove that Clang selected
    # the pointer-authenticated arm64e language ABI.  Validate the ABI macros
    # and exercise an indirect C call (which arm64e authenticates).
    # Do not execute the probe: older macOS versions may link arm64e but
    # disallow launching third-party arm64e binaries.
    if printf '%s\n' \
           '#if !defined(__arm64e__) || !defined(__PTRAUTH__)' \
           '#error "Clang did not select the arm64e pointer-authentication ABI"' \
           '#endif' \
           '#if !__has_feature(ptrauth_calls)' \
           '#error "Clang arm64e indirect-call authentication is unavailable"' \
           '#endif' \
           'static int whp_arm64e_callback(void) { return 0; }' \
           'int main(void) {' \
           '    int (*volatile callback)(void) = whp_arm64e_callback;' \
           '    return callback();' \
           '}' |
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

# Audit the actual compiler-driver command and flag sources, not the WHP INI
# documentation lists.  Clang's --ld-path= overrides -fuse-ld=, and C/C++
# commands can each carry different selectors.  Match the established linker
# choice before the wrapper adds QEMU's managed flags.
whp_macos_audit_linker_driver_flags()
{
    local linker_kind variable value token selected_ld
    local -a tokens=()

    selected_ld="${LD:-}"
    case "${NATIVE_LLVM_LDFLAG:-}" in
        '') linker_kind=apple ;;
        -fuse-ld=lld) linker_kind=lld ;;
        *)
            printf 'error: unknown macOS linker selection: %s\n' \
                "$NATIVE_LLVM_LDFLAG" >&2
            return 1
            ;;
    esac
    if [[ "$linker_kind" == lld ]]; then
        if [[ -z "${NATIVE_LLVM_DIR:-}" ||
              "$selected_ld" != "$NATIVE_LLVM_DIR/bin/ld64.lld" ]]; then
            printf 'error: native Mach-O LLD selection disagrees with LD: %s\n' \
                "${selected_ld:-<unset>}" >&2
            return 1
        fi
    elif [[ "$selected_ld" == */ld64.lld || "$selected_ld" == ld64.lld ]]; then
        printf 'error: Apple ld policy conflicts with LD=%s\n' "$selected_ld" >&2
        return 1
    fi

    case "${WHP_MACOS_ARCH:-auto}:${QEMU_ASAN:-n}" in
        arm64e:*|*:1|*:y)
            if [[ "$linker_kind" == lld ]]; then
                printf 'error: ARM64e/ASan needs Apple ld, not Mach-O LLD\n' >&2
                return 1
            fi
            ;;
    esac

    for variable in CC CXX OBJC CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        tokens=()
        read -r -a tokens <<< "$value"
        # Bash 3.2 treats an empty array as unset under nounset.
        for token in ${tokens[@]+"${tokens[@]}"}; do
            case "$token" in
                -fuse-ld=lld)
                    if [[ "$linker_kind" != lld ]]; then
                        printf 'error: %s overrides Apple ld with %s\n' \
                            "$variable" "$token" >&2
                        return 1
                    fi
                    ;;
                -fuse-ld=*|-fuse-ld)
                    printf 'error: %s conflicts with selected %s linker: %s\n' \
                        "$variable" "$linker_kind" "$token" >&2
                    return 1
                    ;;
                --ld-path=*)
                    # Even with -fuse-ld=lld, this option takes precedence.
                    if [[ "$linker_kind" != lld ||
                          "${token#--ld-path=}" != "$selected_ld" ]]; then
                        printf 'error: %s overrides selected %s linker: %s\n' \
                            "$variable" "$linker_kind" "$token" >&2
                        return 1
                    fi
                    ;;
                --ld-path)
                    printf 'error: %s uses incomplete linker selector: %s\n' \
                        "$variable" "$token" >&2
                    return 1
                    ;;
                -Wl,-O2)
                    if [[ "$linker_kind" == lld ]]; then
                        printf 'error: %s uses Apple ld -O2 with Mach-O LLD\n' \
                            "$variable" >&2
                        return 1
                    fi
                    ;;
                -Wl,--read-workers=*|-Wl,--threads=*)
                    if [[ "$linker_kind" != lld ]]; then
                        printf 'error: %s uses Mach-O LLD worker option with Apple ld: %s\n' \
                            "$variable" "$token" >&2
                        return 1
                    fi
                    ;;
            esac
        done
    done
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
        printf '%s\n' "$native_arch"
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
