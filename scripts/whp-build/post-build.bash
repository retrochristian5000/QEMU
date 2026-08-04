#!/usr/bin/env bash

# Verify the artifacts produced by the WHP build and record the exact files a
# user should run.  This file is sourced by builder.sh after Make completes.

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: scripts/whp-build/post-build.bash requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi
: "${SOURCE_DIR:?builder.sh must define SOURCE_DIR before post-build checks}"
: "${BUILD_DIR:?whp_prepare_build must define BUILD_DIR}"
: "${QEMU_TARGET_LIST:?whp_prepare_build must define QEMU_TARGET_LIST}"

whp_target_requested()
{
    local wanted="$1"
    shift
    local target

    for target in "$@"; do
        if [[ "$target" == "$wanted" || "$target" == all ]]; then
            return 0
        fi
    done
    return 1
}

whp_target_list_contains()
{
    local wanted="$1"
    local normalized=",${QEMU_TARGET_LIST// /},"

    case "$normalized" in
        *",$wanted,"*) return 0 ;;
        *) return 1 ;;
    esac
}

whp_file_checksum()
{
    local path="$1"

    if command -v cksum >/dev/null 2>&1; then
        cksum "$path" | awk '{ print $1 ":" $2 }'
    else
        printf 'unavailable\n'
    fi
}

whp_verify_build_outputs()
{
    local requested_targets=()
    local target_string
    local qemu_ppc=""
    local machine_list=""
    local qemu_version=""
    local qemu_checksum=""
    local openbios_output=""
    local openbios_checksum=""
    local source_revision="unavailable"
    local manifest="$BUILD_DIR/.whp-build-artifacts"
    local candidate="$manifest.new.$$"

    if (( $# > 0 )); then
        requested_targets=("$@")
    else
        read -r -a requested_targets <<< "${BUILD_TARGETS:-all}"
    fi
    target_string="${requested_targets[*]}"

    if whp_target_requested qemu-system-ppc "${requested_targets[@]}" &&
       whp_target_list_contains ppc-softmmu; then
        qemu_ppc="$BUILD_DIR/qemu-system-ppc"
        if [[ ! -x "$qemu_ppc" ]]; then
            printf 'error: expected PowerPC emulator was not produced: %s\n' \
                "$qemu_ppc" >&2
            return 1
        fi

        machine_list="$($qemu_ppc -machine help)"
        if ! grep -Eq '^[[:space:]]*powermac3_1[[:space:]]' <<< "$machine_list"; then
            printf '%s\n' \
                'error: the newly built qemu-system-ppc does not register powermac3_1' \
                "binary: $qemu_ppc" \
                'Registered PowerMac-related machine types:' >&2
            grep -E 'g3beige|mac99|powermac|sawtooth' <<< "$machine_list" >&2 || true
            return 1
        fi
        if ! grep -Eq '^[[:space:]]*mac99[[:space:]]' <<< "$machine_list"; then
            printf 'error: the newly built emulator lost the base mac99 machine\n' >&2
            return 1
        fi

        qemu_version="$($qemu_ppc --version | sed -n '1p')"
        qemu_checksum="$(whp_file_checksum "$qemu_ppc")"
    fi

    for openbios_candidate in \
        "$BUILD_DIR/pc-bios/openbios-ppc" \
        "$BUILD_DIR/openbios-ppc"; do
        if [[ -s "$openbios_candidate" ]]; then
            openbios_output="$openbios_candidate"
            openbios_checksum="$(whp_file_checksum "$openbios_output")"
            break
        fi
    done

    if [[ -e "$SOURCE_DIR/.git" ]] && command -v git >/dev/null 2>&1; then
        source_revision="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || printf unavailable)"
    fi

    {
        printf 'SCHEMA=1\n'
        printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
        printf 'SOURCE_REVISION=%s\n' "$source_revision"
        printf 'BUILD_DIR=%s\n' "$BUILD_DIR"
        printf 'QEMU_TARGET_LIST=%s\n' "$QEMU_TARGET_LIST"
        printf 'REQUESTED_TARGETS=%s\n' "$target_string"
        printf 'QEMU_SYSTEM_PPC=%s\n' "$qemu_ppc"
        printf 'QEMU_SYSTEM_PPC_VERSION=%s\n' "$qemu_version"
        printf 'QEMU_SYSTEM_PPC_CKSUM=%s\n' "$qemu_checksum"
        printf 'POWERMAC3_1_REGISTERED=%s\n' \
            "$([[ -n "$qemu_ppc" ]] && printf yes || printf not-checked)"
        printf 'OPENBIOS_PPC=%s\n' "$openbios_output"
        printf 'OPENBIOS_PPC_CKSUM=%s\n' "$openbios_checksum"
    } > "$candidate"
    mv -f "$candidate" "$manifest"

    if [[ -n "$qemu_ppc" ]]; then
        printf '%s\n' \
            "verified QEMU machine profile: powermac3_1 ($qemu_ppc)" \
            "build artifact manifest: $manifest"
    else
        printf 'build artifact manifest: %s\n' "$manifest"
    fi
}
