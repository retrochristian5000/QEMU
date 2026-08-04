#!/usr/bin/env bash

set -euo pipefail

: "${BUILD_DIR:?the WHP build must export BUILD_DIR}"
: "${QEMU_TARGET_LIST:?the WHP build must export QEMU_TARGET_LIST}"

requested_targets=("$@")
if (( ${#requested_targets[@]} == 0 )); then
    read -r -a requested_targets <<< "${BUILD_TARGETS:-all}"
fi

verify_ppc=0
for target in "${requested_targets[@]}"; do
    case "$target" in
        all|qemu-system-ppc)
            verify_ppc=1
            ;;
    esac
done

if (( verify_ppc == 0 )); then
    exit 0
fi

case ",${QEMU_TARGET_LIST// /}," in
    *,ppc-softmmu,*) ;;
    *) exit 0 ;;
esac

qemu_ppc="$BUILD_DIR/qemu-system-ppc"
if [[ ! -x "$qemu_ppc" ]]; then
    printf 'error: expected PowerPC emulator was not produced: %s\n' \
        "$qemu_ppc" >&2
    exit 1
fi

machine_list="$($qemu_ppc -machine help)"
if ! grep -Eq '^[[:space:]]*powermac3_1[[:space:]]' <<< "$machine_list"; then
    printf '%s\n' \
        'error: the newly built qemu-system-ppc does not register powermac3_1' \
        "binary: $qemu_ppc" \
        'This usually means the executable is stale or the machine source was' \
        'not included in the active Meson configuration.' \
        'Registered PowerMac-related machine types:' >&2
    grep -E 'g3beige|mac99|powermac|sawtooth' <<< "$machine_list" >&2 || true
    exit 1
fi

printf 'verified QEMU machine profile: powermac3_1 (%s)\n' "$qemu_ppc"
