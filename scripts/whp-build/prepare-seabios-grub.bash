# GRUB-loadable SeaBIOS preparation wrapper.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_seabios_grub_sources()
{
    local requested_grub_mode="${BUILD_SEABIOS_GRUB:-0}"
    local hybrid_mode="${BUILD_SEABIOS_HYBRID_ISO:-0}"
    local grub_mode="$requested_grub_mode"
    local seabios_mode="${BUILD_SEABIOS:-auto}"
    local normal_seabios=0
    local normal_config="$BUILD_DIR/.whp-seabios-meson.env"
    local grub_config="$BUILD_DIR/.whp-seabios-grub-meson.env"
    local hybrid_config="$BUILD_DIR/.whp-seabios-hybrid-iso.env"
    local grub_was_enabled=0
    local hybrid_was_enabled=0
    local reconfigure=0
    local seabios_build_root=
    local legacy_grub_mkimage="${GRUB_MKIMAGE:-}"
    local grub_i386_mkimage="${GRUB_I386_MKIMAGE:-${legacy_grub_mkimage:-i386-efi-grub-mkimage}}"
    local grub_x86_64_mkimage="${GRUB_X86_64_MKIMAGE:-${legacy_grub_mkimage:-x86_64-elf-grub-mkimage}}"
    local grub_i386_module_dir="${GRUB_I386_MODULE_DIR:-${GRUB_I386_EFI_DIR:-}}"
    local grub_x86_64_module_dir="${GRUB_X86_64_MODULE_DIR:-${GRUB_X86_64_EFI_DIR:-}}"
    local grub_i386_install_prefix="${GRUB_I386_INSTALL_PREFIX:-${GRUB_I386_PREFIX:-}}"
    local grub_x86_64_install_prefix="${GRUB_X86_64_INSTALL_PREFIX:-${GRUB_X86_64_PREFIX:-}}"
    local grub_i386_bootstrap="${GRUB_I386_BOOTSTRAP:-auto}"
    local grub_i386_bootstrap_prefix="${GRUB_I386_BOOTSTRAP_PREFIX:-$BUILD_DIR/firmware-tools/grub-i386-efi}"
    local i386_toolchain_dir="${I386_TOOLCHAIN_DIR:-$BUILD_DIR/firmware-tools/i386-none-elf}"
    local i386_toolchain_work_dir="${I386_TOOLCHAIN_WORK_DIR:-$BUILD_DIR/firmware-tools/toolchain-work/i386-none-elf}"
    local grub_i386_explicit=0
    local run_i386_bootstrap=0
    local brew_cmd="${GRUB_I386_BREW:-${WHP_HOMEBREW_BREW:-}}"
    local source_dir="${SOURCE_DIR:-}"
    local bootstrap_script

    if [[ -z "$source_dir" ]]; then
        source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
    fi
    bootstrap_script="$source_dir/scripts/bootstrap-i386-efi-grub.sh"

    [[ -f "$grub_config" ]] && grub_was_enabled=1
    [[ -f "$hybrid_config" ]] && hybrid_was_enabled=1

    case "$requested_grub_mode" in
        0|1) ;;
        *)
            printf 'error: BUILD_SEABIOS_GRUB must be 0 or 1\n' >&2
            return 1
            ;;
    esac
    case "$hybrid_mode" in
        0|1) ;;
        *)
            printf 'error: BUILD_SEABIOS_HYBRID_ISO must be 0 or 1\n' >&2
            return 1
            ;;
    esac
    case "$grub_i386_bootstrap" in
        auto|0|1) ;;
        *)
            printf 'error: GRUB_I386_BOOTSTRAP must be auto, 0, or 1\n' >&2
            return 1
            ;;
    esac

    # The real-hardware ISO contains the GRUB-loadable SeaBIOS payload, so the
    # ISO option implies that payload without forcing users to select both menu
    # entries manually.
    if [[ "$hybrid_mode" == 1 ]]; then
        grub_mode=1
        BUILD_SEABIOS_GRUB=1
    fi

    # Any explicit IA32 GRUB tool/module/prefix selection is authoritative.
    # Otherwise Homebrew is only the GRUB source provider. The automatic lane
    # builds a real i386-efi GRUB with the same i386-none-elf LLVM fork already
    # prepared for SeaBIOS; Homebrew's PC-only i686 GRUB is never reused as EFI.
    if [[ -n "${GRUB_I386_MKIMAGE:-}" || -n "$legacy_grub_mkimage" ||
          -n "$grub_i386_module_dir" || -n "$grub_i386_install_prefix" ]]; then
        grub_i386_explicit=1
    fi

    if [[ "$grub_mode" == 0 ]]; then
        rm -f "$grub_config" "$hybrid_config"
        if [[ "$grub_was_enabled" == 1 || "$hybrid_was_enabled" == 1 ]]; then
            rm -f "$BUILD_DIR/.whp-config"
        fi
        whp_prepare_sources
        export BUILD_SEABIOS_GRUB BUILD_SEABIOS_HYBRID_ISO
        return
    fi

    case "$seabios_mode" in
        1) normal_seabios=1 ;;
        0) normal_seabios=0 ;;
        auto)
            case ",${QEMU_TARGET_LIST:-}," in
                *,i386-softmmu,*) normal_seabios=1 ;;
                *) normal_seabios=0 ;;
            esac
            ;;
        *)
            printf 'error: BUILD_SEABIOS must be auto, 0, or 1\n' >&2
            return 1
            ;;
    esac

    # A GRUB payload needs the same SeaBIOS source and i386-none-elf toolchain
    # preparation even when the normal QEMU BIOS image was disabled.
    if [[ "$normal_seabios" == 0 ]]; then
        BUILD_SEABIOS=1
    fi

    whp_prepare_sources || return

    [[ -f "$normal_config" ]] || {
        printf 'error: GRUB SeaBIOS was requested but SeaBIOS preparation produced no config\n' >&2
        return 1
    }

    if [[ "$hybrid_mode" == 1 ]]; then
        seabios_build_root="$(
            # shellcheck disable=SC1090
            source "$normal_config"
            printf '%s' "${SEABIOS_BUILD_ROOT:?SeaBIOS config is missing SEABIOS_BUILD_ROOT}"
        )"

        if [[ "$grub_i386_explicit" == 0 && "$grub_i386_bootstrap" != 0 ]]; then
            if [[ "$grub_i386_bootstrap" == 1 ]]; then
                run_i386_bootstrap=1
            else
                if [[ -z "$brew_cmd" ]]; then
                    brew_cmd="$(command -v brew 2>/dev/null || true)"
                fi
                [[ -n "$brew_cmd" ]] && run_i386_bootstrap=1
            fi
        fi

        if [[ "$run_i386_bootstrap" == 1 ]]; then
            [[ -f "$bootstrap_script" ]] || {
                printf 'error: IA32 EFI GRUB bootstrap is missing: %s\n' \
                    "$bootstrap_script" >&2
                return 1
            }
            BUILD_DIR="$BUILD_DIR" \
            JOBS="${JOBS:-}" \
            I386_TOOLCHAIN_DIR="$i386_toolchain_dir" \
            I386_TOOLCHAIN_WORK_DIR="$i386_toolchain_work_dir" \
            GRUB_I386_BREW="$brew_cmd" \
            GRUB_I386_INSTALL_PREFIX="$grub_i386_bootstrap_prefix" \
                bash "$bootstrap_script" || return
            grub_i386_install_prefix="$grub_i386_bootstrap_prefix"
            grub_i386_mkimage="$grub_i386_install_prefix/bin/i386-efi-grub-mkimage"
            grub_i386_module_dir="$grub_i386_install_prefix/lib/i386-none-elf/grub/i386-efi"
        fi
    fi

    if [[ "$normal_seabios" == 1 ]]; then
        cp "$normal_config" "$grub_config.new"
        mv "$grub_config.new" "$grub_config"
    else
        mv "$normal_config" "$grub_config"
        BUILD_SEABIOS=0
    fi

    if [[ "$grub_was_enabled" == 0 ]]; then
        reconfigure=1
    fi

    if [[ "$hybrid_mode" == 1 ]]; then
        {
            # Keep the old single-tool override for custom installs, but record
            # separate defaults so IA32 and x86-64 EFI never share the wrong
            # GRUB executable or module tree by accident. These are host-side
            # discovery variables for grub-mkimage -d; the image's runtime
            # GRUB prefix (-p /boot/grub) is intentionally a separate contract.
            printf 'GRUB_MKIMAGE=%q\n' "$legacy_grub_mkimage"
            printf 'GRUB_I386_MKIMAGE=%q\n' "$grub_i386_mkimage"
            printf 'GRUB_X86_64_MKIMAGE=%q\n' "$grub_x86_64_mkimage"
            printf 'GRUB_I386_MODULE_DIR=%q\n' "$grub_i386_module_dir"
            printf 'GRUB_X86_64_MODULE_DIR=%q\n' "$grub_x86_64_module_dir"
            printf 'GRUB_I386_EFI_DIR=%q\n' "$grub_i386_module_dir"
            printf 'GRUB_X86_64_EFI_DIR=%q\n' "$grub_x86_64_module_dir"
            printf 'GRUB_I386_INSTALL_PREFIX=%q\n' "$grub_i386_install_prefix"
            printf 'GRUB_X86_64_INSTALL_PREFIX=%q\n' "$grub_x86_64_install_prefix"
            printf 'GRUB_I386_PREFIX=%q\n' "$grub_i386_install_prefix"
            printf 'GRUB_X86_64_PREFIX=%q\n' "$grub_x86_64_install_prefix"
            printf 'GRUB_I386_BOOTSTRAP=%q\n' "$grub_i386_bootstrap"
            printf 'GRUB_I386_BOOTSTRAP_PREFIX=%q\n' "$grub_i386_bootstrap_prefix"
            printf 'HOMEBREW_PREFIX=%q\n' "${HOMEBREW_PREFIX:-}"
            printf 'XORRISO=%q\n' "${XORRISO:-xorriso}"
            printf 'MFORMAT=%q\n' "${MFORMAT:-mformat}"
            printf 'MMD=%q\n' "${MMD:-mmd}"
            printf 'MCOPY=%q\n' "${MCOPY:-mcopy}"
            printf 'PYTHON=%q\n' "${PYTHON:-python3}"
            printf 'SEABIOS_BUILD_ROOT=%q\n' "$seabios_build_root"
        } > "$hybrid_config.new"
        if [[ ! -f "$hybrid_config" ]] || ! cmp -s "$hybrid_config.new" "$hybrid_config"; then
            mv "$hybrid_config.new" "$hybrid_config"
            reconfigure=1
        else
            rm -f "$hybrid_config.new"
        fi
    else
        rm -f "$hybrid_config"
        if [[ "$hybrid_was_enabled" == 1 ]]; then
            reconfigure=1
        fi
    fi

    if [[ "$reconfigure" == 1 ]]; then
        rm -f "$BUILD_DIR/.whp-config"
    fi

    export BUILD_SEABIOS BUILD_SEABIOS_GRUB BUILD_SEABIOS_HYBRID_ISO
}
