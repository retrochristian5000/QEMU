# QEMU host CPU code-generation tuning adapter.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_host_cpu_tuning()
{
    local tool="$SOURCE_DIR/scripts/whp-build/host-cpu-tuning.py"
    local requested="${QEMU_HOST_CPU_TUNING:-native}"
    local args=()

    : "${PYTHON:=python3}"
    QEMU_HOST_CPU_TUNING="$requested"
    args=(
        --value "$requested"
        --host-arch "${HOST_ARCH:-unknown}"
        --cc "${CC:-cc}"
        --cxx "${CXX:-c++}"
    )
    if [[ -n "${OBJC:-}" ]]; then
        args+=(--objc "$OBJC")
    fi

    QEMU_HOST_CPU_FLAGS_RESOLVED="$("$PYTHON" "$tool" "${args[@]}")" || return 1
    WHP_HOST_CPU_TUNING_APPLIED=0
    export QEMU_HOST_CPU_TUNING QEMU_HOST_CPU_FLAGS_RESOLVED \
        WHP_HOST_CPU_TUNING_APPLIED

    case "$requested" in
        portable)
            printf 'QEMU host CPU tuning: portable\n'
            ;;
        native)
            if [[ -n "$QEMU_HOST_CPU_FLAGS_RESOLVED" ]]; then
                printf 'QEMU host CPU tuning: native -> %s\n' \
                    "$QEMU_HOST_CPU_FLAGS_RESOLVED"
            else
                printf '%s\n' \
                    'warning: native QEMU host CPU tuning is unsupported by the active compiler;' \
                    'continuing with the compiler default CPU baseline.' >&2
            fi
            ;;
        *)
            printf 'QEMU host CPU tuning: custom -> %s\n' \
                "$QEMU_HOST_CPU_FLAGS_RESOLVED"
            ;;
    esac
}

whp_apply_host_cpu_tuning()
{
    if [[ "${WHP_HOST_CPU_TUNING_APPLIED:-0}" == 1 ]]; then
        return 0
    fi
    if [[ -n "${QEMU_HOST_CPU_FLAGS_RESOLVED:-}" ]]; then
        whp_append_flag CFLAGS "$QEMU_HOST_CPU_FLAGS_RESOLVED"
        whp_append_flag CXXFLAGS "$QEMU_HOST_CPU_FLAGS_RESOLVED"
        if [[ -n "${OBJC:-}" ]]; then
            whp_append_flag OBJCFLAGS "$QEMU_HOST_CPU_FLAGS_RESOLVED"
        fi
    fi
    WHP_HOST_CPU_TUNING_APPLIED=1
    export WHP_HOST_CPU_TUNING_APPLIED
}
