# QEMU host CPU code-generation tuning adapter.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_strip_host_cpu_tuning_from()
{
    local variable="$1"
    local value="${!variable:-}"
    local token
    local skip_value=0
    local tokens=()
    local kept=()

    [[ -n "$value" ]] || return 0

    read -r -a tokens <<< "$value"
    for token in "${tokens[@]}"; do
        if (( skip_value )); then
            skip_value=0
            continue
        fi
        case "$token" in
            -march|-mcpu|-mtune)
                skip_value=1
                ;;
            -march=*|-mcpu=*|-mtune=*)
                ;;
            *)
                kept+=("$token")
                ;;
        esac
    done

    printf -v "$variable" '%s' "${kept[*]}"
    export "$variable"
}

whp_strip_inherited_host_cpu_tuning()
{
    local variable

    for variable in CFLAGS CXXFLAGS OBJCFLAGS; do
        whp_strip_host_cpu_tuning_from "$variable"
    done
}

whp_strip_host_performance_overrides_from()
{
    local variable="$1"
    local value="${!variable:-}"
    local token
    local tokens=()
    local kept=()

    [[ -n "$value" ]] || return 0

    read -r -a tokens <<< "$value"
    for token in "${tokens[@]}"; do
        case "$token" in
            -O|-O0|-O1|-O2|-O3|-Og|-Os|-Oz|-Ofast|\
            -fno-inline|-fno-inline-functions|-fno-inline-small-functions|\
            -fno-omit-frame-pointer|-fno-optimize-sibling-calls|\
            -fno-vectorize|-fno-slp-vectorize|\
            -pg|--coverage|-fprofile-arcs|-ftest-coverage|\
            -finstrument-functions|-fcoverage-mapping|\
            -fsanitize=*|-fsanitize-coverage=*|-fsanitize-recover=*|\
            -fno-sanitize-recover=*|-fprofile-generate|\
            -fprofile-generate=*|-fprofile-instr-generate|\
            -fprofile-instr-generate=*)
                ;;
            *)
                kept+=("$token")
                ;;
        esac
    done

    printf -v "$variable" '%s' "${kept[*]}"
    export "$variable"
}

whp_strip_inherited_host_performance_overrides()
{
    local variable

    for variable in CFLAGS CXXFLAGS OBJCFLAGS; do
        whp_strip_host_performance_overrides_from "$variable"
    done
}

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
