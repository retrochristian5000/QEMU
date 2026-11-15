# Early macOS CFLAGS compatibility check, before optional firmware bootstraps.
# SPDX-License-Identifier: GPL-2.0-or-later
# Sourced by macos-builder.bash; Bash 3.2 compatible.

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/host-cpu-tuning.bash"

whp_macos_preflight_cflags()
(
    local variable compiler_variable compiler language output token flag_source
    local origin
    local -a compiler_command=() user_flags=() cpp_flags=() target_flags=() flag_tokens=()

    # These flags are removed by builder.bash before configuring QEMU. Probe
    # the effective user flags without changing the flags still needed by
    # earlier firmware/toolchain bootstraps.
    whp_strip_inherited_host_cpu_tuning
    whp_strip_inherited_host_performance_overrides
    [[ -n "${CFLAGS:-}${CXXFLAGS:-}${OBJCFLAGS:-}${CPPFLAGS:-}" ]] || return 0

    read -r -a cpp_flags <<< "${CPPFLAGS:-}"
    target_flags=(-isysroot "$SDKROOT"
                  "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET")
    if [[ "${MACOS_EFFECTIVE_COMPILER_FAMILY:-clang}" == clang ]]; then
        target_flags=(-arch "$WHP_MACOS_ARCH" "${target_flags[@]}")
    fi

    for variable in CFLAGS CXXFLAGS OBJCFLAGS; do
        user_flags=()
        read -r -a user_flags <<< "${!variable:-}"
        if [[ "${#user_flags[@]}" -eq 0 && "${#cpp_flags[@]}" -eq 0 ]]; then
            continue
        fi
        case "$variable" in
            CFLAGS) compiler_variable=CC; language=c ;;
            CXXFLAGS) compiler_variable=CXX; language=c++ ;;
            OBJCFLAGS) compiler_variable=OBJC; language=objective-c ;;
        esac
        compiler=${!compiler_variable:-}
        compiler_command=()
        read -r -a compiler_command <<< "$compiler"
        if [[ "${#compiler_command[@]}" -eq 0 ]]; then
            printf 'error: macOS %s preflight has no %s compiler\n' \
                "$variable" "$compiler_variable" >&2
            return 1
        fi

        # Linker-only options belong to LDFLAGS. Attribute the offending
        # flag to its original lane rather than blaming every C frontend.
        for flag_source in CPPFLAGS "$variable"; do
            flag_tokens=()
            read -r -a flag_tokens <<< "${!flag_source:-}"
            for token in "${flag_tokens[@]}"; do
                case "$token" in
                    -Wl,*|-Xlinker|-Xlinker=*|-L*|-l*|-framework)
                        printf 'error: macOS %s has linker-only flag %s; use LDFLAGS\n' \
                            "$flag_source" "$token" >&2
                        return 1 ;;
                esac
            done
        done

        origin="$variable"
        if [[ "${#cpp_flags[@]}" -gt 0 ]]; then
            if [[ "${#user_flags[@]}" -eq 0 ]]; then
                origin=CPPFLAGS
            else
                origin="$variable/CPPFLAGS"
            fi
        fi

        # No files or headers are installed; the selected SDK, deployment,
        # language frontend, and final (post-filter) flags are exercised.
        if output=$("${compiler_command[@]}" "${target_flags[@]}" \
            "${cpp_flags[@]}" "${user_flags[@]}" \
            -x "$language" -c -o /dev/null - \
            <<< 'int whp_cflags_probe(void) { return 0; }' 2>&1); then
            :
        else
            printf 'error: macOS %s rejected by %s (%s)\n' \
                "$origin" "$compiler_variable" "$compiler" >&2
            [[ -z "$output" ]] || printf '%s\n' "$output" >&2
            return 1
        fi
        # Some Clang/GCC options exit successfully while being ignored.
        # Treat those diagnostics as a failed capability test, not approval.
        case "$output" in
            *'unknown warning option'*|*'argument unused during compilation'*|\
            *'unrecognized command-line option'*|*'ignoring unknown option'*)
                printf 'error: macOS %s has ignored or unsupported %s options\n' \
                    "$origin" "$compiler_variable" >&2
                printf '%s\n' "$output" >&2
                return 1 ;;
        esac
    done
)
