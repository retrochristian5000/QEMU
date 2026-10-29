#!/usr/bin/env bash

# Select the Apple Mach-O architecture used for QEMU host objects.  arm64e is
# an ABI variant of the AArch64 backend, not a separate LLVM target backend, so
# keep this policy independent from WHP_HOST_ARCH/LLVM_TARGETS_TO_BUILD.
#
# Auto selects arm64e only after the C/C++ PAC execution and linker probes.
# Explicit arm64e remains a link-only, probe-gated development lane.

whp_macos_arch_probe_arm64e()
{
    local compiler="$1"
    local sdkroot="$2"
    local deployment_target="$3"
    local language="${4:-c}"
    local run_probe="${5:-no}"
    local probe_dir output
    local compiler_command=()
    local linker_flag="${NATIVE_LLVM_LDFLAG:-}"

    read -r -a compiler_command <<< "$compiler"
    if [[ "${#compiler_command[@]}" -eq 0 ]]; then
        return 1
    fi

    probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-arm64e-probe.XXXXXX")" || return 1
    output="$probe_dir/arm64e"
    # Auto mode compiles and executes this authenticated indirect-call probe.
    # An explicit arm64e request retains the compile/link-only development lane.
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
           -x "$language" - -o "$output" >/dev/null 2>&1; then
        if [[ "$run_probe" != yes ]] || "$output" >/dev/null 2>&1; then
            rm -rf "$probe_dir"
            return 0
        fi
    fi

    rm -rf "$probe_dir"
    return 1
}


# Mach-O LLD is only eligible for auto arm64e after proving it can preserve
# authenticated relocations. An explicit opt-in still controls LLD adoption.
whp_macos_arm64e_auto_linker_ready()
{
    if [[ "${NATIVE_LLVM_LDFLAG:-}" != -fuse-ld=lld ]]; then
        return 0
    fi
    [[ "${WHP_ARM64E_USE_LLD:-0}" == 1 &&
       -n "${NATIVE_LLVM_DIR:-}" &&
       "${LD:-}" == "$NATIVE_LLVM_DIR/bin/ld64.lld" &&
       -x "$NATIVE_LLVM_DIR/bin/ld64.lld" &&
       -x "$NATIVE_LLVM_DIR/bin/llvm-objdump" ]] || return 1

    local probe_script
    probe_script="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/whp-build/arm64e-lld-probe.bash"
    "${BASH:-bash}" "$probe_script" "$1" "$2" "$3" "$LD" \
        "$NATIVE_LLVM_DIR/bin/llvm-objdump" >/dev/null 2>&1
}

# The arm64e Mach-O subtype does not guarantee that its C++ code follows
# the authenticated-call ABI. Clang++ accepts -fno-ptrauth-calls and still
# writes cputype ARM64, subtype 0x80000002, but replaces virtual BRAA/BLRAA
# calls with unsigned BR/BLR. Check every active compiler/flag source before
# the wrapper appends -arch; leave ordinary arm64 builds unrestricted.
whp_macos_audit_arm64e_codegen_flags()
{
    [[ "${WHP_MACOS_ARCH:-auto}" == arm64e ]] || return 0
    local variable token value
    local -a tokens=()
    for variable in CC CXX OBJC CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        tokens=()
        read -r -a tokens <<< "$value"
        for token in ${tokens[@]+"${tokens[@]}"}; do
            case "$token" in
                -fno-ptrauth-calls)
                    printf 'error: %s disables authenticated ARM64e calls: %s\n' \
                        "$variable" "$token" >&2
                    return 1
                    ;;
            esac
        done
    done
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
    fi

    # In the Apple-linker lane, inherited LD does not select QEMU's host
    # linker through Clang. Keep the driver-option audit below; the managed
    # native LLD lane still requires the exact LD-to-installation match above.

    case "${WHP_MACOS_ARCH:-auto}:${QEMU_ASAN:-n}" in
        *:1|*:y)
            if [[ "$linker_kind" == lld ]]; then
                printf 'error: ASan needs Apple ld until its LLD runtime contract passes\n' >&2
                return 1
            fi
            ;;
        arm64e:*)
            if [[ "$linker_kind" == lld &&
                  "${WHP_ARM64E_USE_LLD:-0}" != 1 ]]; then
                printf 'error: ARM64e LLD requires WHP_ARM64E_USE_LLD=1\n' >&2
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

    # The CLANG and CLANG++ drivers must actually resolve our selected LLD.
    # -fuse-ld=lld is not proof: -B or a driver configuration could redirect
    # one frontend to a different linker, even when LD is correct.
    if [[ "$linker_kind" == lld && "${WHP_MACOS_ARCH:-auto}" == arm64e ]]; then
        local driver_var language pipeline
        local -a driver_command=()
        for driver_var in CC CXX; do
            driver_command=()
            read -r -a driver_command <<< "${!driver_var:-}"
            [[ -n "${driver_command[0]:-}" ]] || return 1
            if [[ "$driver_var" == CXX ]]; then
                language=c++
            else
                language=c
            fi
            pipeline="$("${driver_command[@]}" -### -arch arm64e \
                -isysroot "$SDKROOT" \
                "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
                -fuse-ld=lld -x "$language" /dev/null -o /dev/null 2>&1)" ||
                return 1
            if [[ "$pipeline" != *"$LD"* ]]; then
                printf 'error: %s resolves a linker other than selected %s\n' \
                    "$driver_var" "$LD" >&2
                return 1
            fi
        done
    fi

    # The installed LLD must consume authenticated relocations and emit
    # versioned arm64e chained fixups, not merely link main().
    if [[ "$linker_kind" == lld && "${WHP_MACOS_ARCH:-auto}" == arm64e ]]; then
        local probe_script
        probe_script="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/whp-build/arm64e-lld-probe.bash"
        if ! "$BASH" "$probe_script" "$CC" "$SDKROOT" \
                "$MACOSX_DEPLOYMENT_TARGET" "$LD" \
                "$NATIVE_LLVM_DIR/bin/llvm-objdump"; then
            printf 'error: selected ARM64e LLD failed authenticated fixup validation\n' >&2
            return 1
        fi
    fi
}

# An explicit arm64e UBSan build must not silently load a plain arm64
# compiler-rt dylib. The selected Clang owns its resource directory; do not
# borrow Apple's runtime when running the WHP LLVM driver. This is only an ABI
# admission test; Meson still checks the instrumented link against the SDK.
whp_macos_verify_ubsan_abi()
{
    local compiler="$1"
    local lipo="$2"
    local arch="$3"
    local resource runtime slices

    resource="$("$compiler" -print-resource-dir 2>/dev/null)" || {
        printf 'error: UBSan Clang resource directory is unavailable: %s\n' "$compiler" >&2
        return 1
    }
    runtime="$resource/lib/darwin/libclang_rt.ubsan_osx_dynamic.dylib"
    if [[ ! -f "$runtime" ]]; then
        printf 'error: matching compiler-rt UBSan dylib is missing: %s\n' "$runtime" >&2
        return 1
    fi
    slices="$("$lipo" -archs "$runtime" 2>/dev/null)" || {
        printf 'error: cannot inspect UBSan runtime architecture: %s\n' "$runtime" >&2
        return 1
    }
    if ! printf '%s\n' "$slices" | tr '[:space:]' '\n' | grep -Fxq "$arch"; then
        printf 'error: UBSan runtime lacks %s ABI (available: %s): %s\n' \
            "$arch" "$slices" "$runtime" >&2
        return 1
    fi
}

whp_select_macos_arch()
{
    local compiler="$1"
    local sdkroot="$2"
    local deployment_target="$3"
    local process_arch="$4"
    local requested="${WHP_MACOS_ARCH:-auto}"
    local cxx_compiler="${5:-${CXX:-$compiler}}"
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
        # Keep the default on arm64 unless the current macOS runtime can
        # actually execute PAC-authenticated calls compiled by both drivers.
        # ASan, UBSan and unapproved Mach-O LLD configurations do not
        # auto-promote: native LLVM defaults to an arm64-only compiler-rt
        # resource tree unless arm64e is explicitly selected for bootstrap.
        if [[ "$native_arch" == arm64 &&
              "${QEMU_ASAN:-n}" != 1 && "${QEMU_ASAN:-n}" != y &&
              "${QEMU_UBSAN:-n}" != 1 && "${QEMU_UBSAN:-n}" != y ]] &&
           whp_macos_arm64e_auto_linker_ready \
               "$compiler" "$sdkroot" "$deployment_target" &&
           whp_macos_arch_probe_arm64e \
               "$compiler" "$sdkroot" "$deployment_target" c yes &&
           whp_macos_arch_probe_arm64e \
               "$cxx_compiler" "$sdkroot" "$deployment_target" c++ yes; then
            printf '%s\n' arm64e
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
