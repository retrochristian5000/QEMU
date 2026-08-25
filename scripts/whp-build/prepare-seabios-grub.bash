# GRUB-loadable SeaBIOS preparation wrapper.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_seabios_grub_sources()
{
    local grub_mode="${BUILD_SEABIOS_GRUB:-0}"
    local seabios_mode="${BUILD_SEABIOS:-auto}"
    local normal_seabios=0
    local normal_config="$BUILD_DIR/.whp-seabios-meson.env"
    local grub_config="$BUILD_DIR/.whp-seabios-grub-meson.env"

    case "$grub_mode" in
        0|1) ;;
        *)
            printf 'error: BUILD_SEABIOS_GRUB must be 0 or 1\n' >&2
            return 1
            ;;
    esac

    if [[ "$grub_mode" == 0 ]]; then
        rm -f "$grub_config"
        whp_prepare_sources
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

    if [[ "$normal_seabios" == 1 ]]; then
        cp "$normal_config" "$grub_config.new"
        mv "$grub_config.new" "$grub_config"
    else
        mv "$normal_config" "$grub_config"
        BUILD_SEABIOS=0
    fi

    export BUILD_SEABIOS BUILD_SEABIOS_GRUB
}
