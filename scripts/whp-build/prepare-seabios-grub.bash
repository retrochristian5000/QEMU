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

    # The real-hardware ISO contains the GRUB-loadable SeaBIOS payload, so the
    # ISO option implies that payload without forcing users to select both menu
    # entries manually.
    if [[ "$hybrid_mode" == 1 ]]; then
        grub_mode=1
        BUILD_SEABIOS_GRUB=1
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
            printf 'GRUB_MKIMAGE=%q\n' "${GRUB_MKIMAGE:-i686-elf-grub-mkimage}"
            printf 'GRUB_I386_EFI_DIR=%q\n' "${GRUB_I386_EFI_DIR:-}"
            printf 'GRUB_X86_64_EFI_DIR=%q\n' "${GRUB_X86_64_EFI_DIR:-}"
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
