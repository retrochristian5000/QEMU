# WHP compilation and optional installation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_build_targets()
{
local build_target_list=()
local build_runner=()
local target
if (( $# > 0 )); then
    build_target_list=("$@")
else
    read -r -a build_target_list <<< "$BUILD_TARGETS"
fi

# Firmware targets are build_by_default for their matching system targets, so
# an `all` build already requests them. Named qemu-system-* builds bypass that
# default graph and must carry their firmware companion explicitly.
if [[ "${BUILD_OPENBIOS:-0}" == 1 ]]; then
    for target in "${build_target_list[@]}"; do
        if [[ "$target" == qemu-system-ppc ]]; then
            build_target_list+=(whp-openbios-ppc)
            break
        fi
    done
fi
if [[ "${BUILD_SEABIOS:-0}" == 1 ]]; then
    for target in "${build_target_list[@]}"; do
        if [[ "$target" == qemu-system-i386 ]]; then
            build_target_list+=(whp-seabios-x86)
            break
        fi
    done
fi
if [[ "${BUILD_SEABIOS_GRUB:-0}" == 1 ]]; then
    build_target_list+=(whp-seabios-grub)
fi

if [[ -n "${NINJA_CMD:-}" ]]; then
    build_runner=("$NINJA_CMD" -C "$BUILD_DIR" -j "$JOBS")
elif [[ -n "${MAKE_CMD:-}" ]]; then
    build_runner=("$MAKE_CMD" -C "$BUILD_DIR" -j"$JOBS")
else
    printf '%s\n' \
        'error: neither Ninja nor GNU Make is available to run the configured QEMU build.' \
        'Install Ninja or GNU Make, or set NINJA_CMD/MAKE_CMD explicitly.' >&2
    return 1
fi

"${build_runner[@]}" "${build_target_list[@]}"

# Installation is deliberately separate from compilation and is opt-in. This
# avoids making an otherwise successful unprivileged build fail on a prefix.
if [[ "$INSTALL" == "1" ]]; then
    if [[ -n "${NINJA_CMD:-}" ]]; then
        "$NINJA_CMD" -C "$BUILD_DIR" install
    elif [[ -n "${MAKE_CMD:-}" ]]; then
        "$MAKE_CMD" -C "$BUILD_DIR" install
    fi
fi
}
