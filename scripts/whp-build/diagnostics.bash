# QEMU host diagnostic build policy.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_apply_qemu_diagnostics()
{
    QEMU_WERROR="${QEMU_WERROR:-1}"
    QEMU_ASAN="${QEMU_ASAN:-0}"
    QEMU_UBSAN="${QEMU_UBSAN:-0}"
    QEMU_TSAN="${QEMU_TSAN:-0}"

    whp_require_boolean_values \
        QEMU_WERROR QEMU_ASAN QEMU_UBSAN QEMU_TSAN || return 1

    if [[ "$QEMU_TSAN" == 1 &&
          ( "$QEMU_ASAN" == 1 || "$QEMU_UBSAN" == 1 ) ]]; then
        printf '%s\n' \
            'error: QEMU_TSAN cannot be combined with QEMU_ASAN or QEMU_UBSAN.' \
            'QEMU does not support ThreadSanitizer together with the other sanitizers.' >&2
        return 1
    fi

    whp_add_optional_configure_switch "$QEMU_WERROR" werror
    whp_add_optional_configure_switch "$QEMU_ASAN" asan
    whp_add_optional_configure_switch "$QEMU_UBSAN" ubsan
    whp_add_optional_configure_switch "$QEMU_TSAN" tsan
}
