# WHP compilation and optional installation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_build_targets()
{
local build_target_list=()
local build_runner=()
local target
local run_qemu_tests=0
local test_plan=
local test_selector="$SOURCE_DIR/scripts/whp-build/select-tests.py"
local test_target
local test_targets=()
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
if [[ "${BUILD_SEABIOS_HYBRID_ISO:-0}" == 1 ]]; then
    build_target_list+=(whp-seabios-hybrid-iso)
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

# RUN_TESTS controls QEMU regression testing after core QEMU builds.  The
# default changed-only scope asks the selector which documented Make suites are
# affected since the last successful state.  QEMU_TEST_SCOPE=full preserves a
# deliberate escape hatch to the complete `make check` umbrella.
if [[ "${RUN_TESTS:-1}" == 1 ]]; then
    for target in "${build_target_list[@]}"; do
        case "$target" in
            all|qemu-img|qemu-system-*)
                run_qemu_tests=1
                break
                ;;
        esac
    done
fi
if [[ "$run_qemu_tests" == 1 ]]; then
    case "${QEMU_TEST_SCOPE:-changed}" in
        full)
            test_targets=(check)
            ;;
        changed)
            test_plan="$(
                "${PYTHON:-python3}" "$test_selector" plan \
                    --source "$SOURCE_DIR" \
                    --build "$BUILD_DIR" \
                    --targets "${QEMU_TARGET_LIST:-}"
            )" || return 1
            while IFS= read -r test_target; do
                [[ -n "$test_target" ]] && test_targets+=("$test_target")
            done <<< "$test_plan"
            ;;
        *)
            printf 'error: QEMU_TEST_SCOPE must be changed or full: %s\n' \
                "${QEMU_TEST_SCOPE:-}" >&2
            return 1
            ;;
    esac

    if (( ${#test_targets[@]} > 0 )); then
        if [[ -z "${MAKE_CMD:-}" ]]; then
            printf '%s\n' \
                'error: RUN_TESTS=1 requires GNU Make for the QEMU test suites.' \
                'Install GNU Make, set MAKE_CMD, or disable tests in menuconfig.' >&2
            return 1
        fi
        printf 'WHP QEMU tests: %s\n' "${test_targets[*]}"
        "$MAKE_CMD" -C "$BUILD_DIR" -j"$JOBS" "${test_targets[@]}"
    else
        printf '%s\n' 'WHP QEMU tests: no affected suites; skipping unchanged tests.'
    fi

    # State is advisory optimization metadata.  A source archive without Git
    # can still build and run the conservative full suite; it simply cannot
    # remember a changed-only baseline for the next invocation.
    if ! "${PYTHON:-python3}" "$test_selector" record \
        --source "$SOURCE_DIR" \
        --build "$BUILD_DIR" \
        --targets "${QEMU_TARGET_LIST:-}"; then
        printf '%s\n' \
            'warning: QEMU tests passed but selective test state could not be recorded.' >&2
    fi
fi

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
