# WHP configuration identity and configure execution stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_configure_canonical_host_arch()
{
    case "$1" in
        amd64|x86_64) printf 'x86_64\n' ;;
        aarch64|arm64) printf 'arm64\n' ;;
        *) printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]_.-\n' '-' ;;
    esac
}

whp_configure_canonical_host_os()
{
    case "$1" in
        Darwin) printf 'apple-darwin\n' ;;
        Windows|MINGW*|MSYS*|CYGWIN*) printf 'windows\n' ;;
        *) printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]_.-\n' '-' ;;
    esac
}

whp_configure_host_tag()
{
    printf '%s-%s\n' \
        "$(whp_configure_canonical_host_arch "$HOST_ARCH")" \
        "$(whp_configure_canonical_host_os "$HOST_OS")"
}

whp_configure_metadata_value()
{
    local path="$1"
    local key="$2"
    local line

    [[ -f "$path" ]] || return 0
    while IFS= read -r line; do
        case "$line" in
            "$key"=*) printf '%s\n' "${line#*=}"; return 0 ;;
        esac
    done < "$path"
}

whp_configure_validate_build_tree_owner()
{
    local owner_file="$BUILD_DIR/.whp-build-owner"
    local config_file="$BUILD_DIR/.whp-config"
    local expected_tag
    local recorded_source=""
    local recorded_tag=""
    local recorded_arch=""
    local recorded_os=""
    local adopted=0

    mkdir -p "$BUILD_DIR"
    expected_tag="$(whp_configure_host_tag)"

    if [[ -f "$owner_file" ]]; then
        recorded_source="$(whp_configure_metadata_value "$owner_file" SOURCE_DIR)"
        recorded_tag="$(whp_configure_metadata_value "$owner_file" HOST_TAG)"
        if [[ "$recorded_source" != "$SOURCE_DIR" ]]; then
            printf '%s\n' \
                "error: BUILD_DIR belongs to another QEMU source tree: $BUILD_DIR" \
                'The existing build tree was preserved.' >&2
            return 1
        fi
        if [[ -n "$recorded_tag" && "$recorded_tag" != "$expected_tag" ]]; then
            printf '%s\n' \
                "error: BUILD_DIR belongs to host ABI $recorded_tag, not $expected_tag." \
                "build directory: $BUILD_DIR" \
                'Use a different BUILD_DIR for a different host ABI; the existing tree was preserved.' >&2
            return 1
        fi
    elif [[ -n "$(ls -A "$BUILD_DIR" 2>/dev/null)" ]]; then
        # One-time adoption for WHP trees created before the owner marker was
        # introduced.  Source ownership is mandatory; host metadata, when it
        # exists, must also agree with this build machine.
        recorded_source="$(whp_configure_metadata_value "$config_file" SOURCE_DIR)"
        if [[ "$recorded_source" != "$SOURCE_DIR" ]]; then
            printf '%s\n' \
                "error: refusing to reuse non-empty unowned BUILD_DIR: $BUILD_DIR" \
                'Choose an empty directory or an existing WHP tree for this source checkout.' >&2
            return 1
        fi
        recorded_arch="$(whp_configure_metadata_value "$config_file" HOST_ARCH)"
        recorded_os="$(whp_configure_metadata_value "$config_file" HOST_OS)"
        if [[ -n "$recorded_arch" && -n "$recorded_os" ]]; then
            recorded_tag="$(printf '%s-%s' \
                "$(whp_configure_canonical_host_arch "$recorded_arch")" \
                "$(whp_configure_canonical_host_os "$recorded_os")")"
            if [[ "$recorded_tag" != "$expected_tag" ]]; then
                printf '%s\n' \
                    "error: BUILD_DIR belongs to host ABI $recorded_tag, not $expected_tag." \
                    "build directory: $BUILD_DIR" \
                    'The existing tree was preserved.' >&2
                return 1
            fi
        fi
        adopted=1
    fi

    {
        printf 'SCHEMA=2\n'
        printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
        printf 'BUILD_DIR=%s\n' "$BUILD_DIR"
        printf 'HOST_TAG=%s\n' "$expected_tag"
    } > "$owner_file.new"
    mv "$owner_file.new" "$owner_file"

    if [[ "$adopted" == 1 ]]; then
        printf 'Adopted existing WHP build tree without deleting prior outputs: %s\n' \
            "$BUILD_DIR"
    fi
}

whp_configure_previous_target_list()
{
    local path="$1"
    local line
    local value
    local arg

    [[ -f "$path" ]] || return 0

    while IFS= read -r line; do
        case "$line" in
            QEMU_TARGET_LIST=*)
                printf '%s\n' "${line#QEMU_TARGET_LIST=}"
                return 0
                ;;
        esac
    done < "$path"

    # Backward compatibility for build trees created before QEMU_TARGET_LIST
    # had its own identity field.  CONFIGURE_ARG is sufficient to recover the
    # old target set without forcing users to throw the tree away once.
    while IFS= read -r line; do
        case "$line" in
            CONFIGURE_ARG=*)
                value="${line#CONFIGURE_ARG=}"
                for arg in $value; do
                    case "$arg" in
                        --target-list=*)
                            printf '%s\n' "${arg#--target-list=}"
                            return 0
                            ;;
                    esac
                done
                ;;
        esac
    done < "$path"
}

whp_configure_add_target()
{
    local target="$1"

    [[ -n "$target" ]] || return 0
    case ",${QEMU_TARGET_LIST:-}," in
        *",$target,"*) return 0 ;;
    esac
    QEMU_TARGET_LIST="${QEMU_TARGET_LIST:+$QEMU_TARGET_LIST,}$target"
}

whp_configure_merge_previous_targets()
{
    local config_file="$1"
    local current="${QEMU_TARGET_LIST:-}"
    local previous
    local target
    local current_targets=()
    local previous_targets=()

    [[ "${WHP_INCREMENTAL_BUILD:-1}" == 1 ]] || return 0
    previous="$(whp_configure_previous_target_list "$config_file")"
    [[ -n "$previous" ]] || return 0

    # Preserve the established target order first, then append genuinely new
    # targets from this invocation.  Reversing that order based on whichever
    # target the user requested would change CONFIGURE_ARG despite an identical
    # target set and cause pointless reconfigure churn on alternating builds.
    QEMU_TARGET_LIST=
    IFS=, read -r -a previous_targets <<< "$previous"
    for target in "${previous_targets[@]}"; do
        whp_configure_add_target "$target"
    done
    IFS=, read -r -a current_targets <<< "$current"
    for target in "${current_targets[@]}"; do
        whp_configure_add_target "$target"
    done
}

whp_configure_sync_target_args()
{
    local arg
    local synced=()

    for arg in "${configure_args[@]}"; do
        case "$arg" in
            --target-list=*|--disable-system) ;;
            *) synced+=("$arg") ;;
        esac
    done

    if [[ -n "${QEMU_TARGET_LIST:-}" ]]; then
        synced+=("--target-list=$QEMU_TARGET_LIST")
    else
        synced+=(--disable-system)
    fi
    configure_args=("${synced[@]}")
}

whp_configure_hardware_value()
{
    local name="$1"
    local value="$2"

    case "$value" in
        auto|AUTO|Auto) printf 'auto\n' ;;
        1|y|Y|yes|YES|Yes|true|TRUE|True|on|ON|On) printf 'y\n' ;;
        0|n|N|no|NO|No|false|FALSE|False|off|OFF|Off) printf 'n\n' ;;
        *)
            printf 'error: %s must be auto or a boolean value\n' "$name" >&2
            return 1
            ;;
    esac
}

whp_configure_audio_signature()
{
    local prefix="$1"
    local sb16 adlib gus cs4231a pcspk es1370 ac97 cs4630 hda
    local name

    name="${prefix}_AUDIO_SB16"; sb16="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_ADLIB"; adlib="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_GUS"; gus="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_CS4231A"; cs4231a="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_PCSPK"; pcspk="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_ES1370"; es1370="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_AC97"; ac97="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_CS4630"; cs4630="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1
    name="${prefix}_AUDIO_HDA"; hda="$(whp_configure_hardware_value "$name" "${!name:-auto}")" || return 1

    printf 'sb16=%s;adlib=%s;gus=%s;cs4231a=%s;pcspk=%s;es1370=%s;ac97=%s;cs4630=%s;hda=%s\n' \
        "$sb16" "$adlib" "$gus" "$cs4231a" "$pcspk" "$es1370" "$ac97" "$cs4630" "$hda"
}

whp_configure_ppc_audio_signature()
{
    whp_configure_audio_signature PPC
}

# Compatibility name for existing i386-focused tests and helper callers.
whp_configure_i386_audio_value()
{
    whp_configure_hardware_value "$@"
}

whp_configure_i386_audio_signature()
{
    whp_configure_audio_signature I386
}

whp_configure_append_audio_override()
{
    local output="$1"
    local name="$2"
    local raw_value="$3"
    local symbol="$4"
    local value

    value="$(whp_configure_hardware_value "$name" "$raw_value")" || return 1
    if [[ "$value" != auto ]]; then
        printf '%s=%s\n' "$symbol" "$value" >> "$output"
    fi
}

whp_configure_append_i386_audio_override()
{
    whp_configure_append_audio_override "$@"
}

whp_configure_write_ppc_device_config()
{
    local base="$1"
    local output="$2"
    local sb16 adlib gus cs4231a pcspk es1370 ac97 cs4630 hda
    local drop_re='^CONFIG_(MAC_NEWWORLD|MAC_OLDWORLD)='

    sb16="$(whp_configure_hardware_value PPC_AUDIO_SB16 "${PPC_AUDIO_SB16:-auto}")" || return 1
    adlib="$(whp_configure_hardware_value PPC_AUDIO_ADLIB "${PPC_AUDIO_ADLIB:-auto}")" || return 1
    gus="$(whp_configure_hardware_value PPC_AUDIO_GUS "${PPC_AUDIO_GUS:-auto}")" || return 1
    cs4231a="$(whp_configure_hardware_value PPC_AUDIO_CS4231A "${PPC_AUDIO_CS4231A:-auto}")" || return 1
    pcspk="$(whp_configure_hardware_value PPC_AUDIO_PCSPK "${PPC_AUDIO_PCSPK:-auto}")" || return 1
    es1370="$(whp_configure_hardware_value PPC_AUDIO_ES1370 "${PPC_AUDIO_ES1370:-auto}")" || return 1
    ac97="$(whp_configure_hardware_value PPC_AUDIO_AC97 "${PPC_AUDIO_AC97:-auto}")" || return 1
    cs4630="$(whp_configure_hardware_value PPC_AUDIO_CS4630 "${PPC_AUDIO_CS4630:-auto}")" || return 1
    hda="$(whp_configure_hardware_value PPC_AUDIO_HDA "${PPC_AUDIO_HDA:-auto}")" || return 1

    [[ "$sb16" != auto ]] && drop_re="$drop_re|^CONFIG_SB16="
    [[ "$adlib" != auto ]] && drop_re="$drop_re|^CONFIG_ADLIB="
    [[ "$gus" != auto ]] && drop_re="$drop_re|^CONFIG_GUS="
    [[ "$cs4231a" != auto ]] && drop_re="$drop_re|^CONFIG_CS4231A="
    [[ "$pcspk" != auto ]] && drop_re="$drop_re|^CONFIG_PCSPK="
    [[ "$es1370" != auto ]] && drop_re="$drop_re|^CONFIG_ES1370="
    [[ "$ac97" != auto ]] && drop_re="$drop_re|^CONFIG_AC97="
    [[ "$cs4630" != auto ]] && drop_re="$drop_re|^CONFIG_CS4630="
    [[ "$hda" != auto ]] && drop_re="$drop_re|^CONFIG_HDA="

    awk -v re="$drop_re" '$0 !~ re { print }' "$base" > "$output" || return 1

    printf '\n# WHP generated PPC device overrides; retained for Meson regeneration.\n' >> "$output"
    printf 'CONFIG_MAC_NEWWORLD=%s\n' "${CONFIG_MAC_NEWWORLD:-y}" >> "$output"
    printf 'CONFIG_MAC_OLDWORLD=%s\n' "${CONFIG_MAC_OLDWORLD:-y}" >> "$output"
    whp_configure_append_audio_override "$output" PPC_AUDIO_SB16 "$sb16" CONFIG_SB16 || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_ADLIB "$adlib" CONFIG_ADLIB || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_GUS "$gus" CONFIG_GUS || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_CS4231A "$cs4231a" CONFIG_CS4231A || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_PCSPK "$pcspk" CONFIG_PCSPK || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_ES1370 "$es1370" CONFIG_ES1370 || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_AC97 "$ac97" CONFIG_AC97 || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_CS4630 "$cs4630" CONFIG_CS4630 || return 1
    whp_configure_append_audio_override "$output" PPC_AUDIO_HDA "$hda" CONFIG_HDA || return 1
}

whp_configure_write_i386_audio_config()
{
    local base="$1"
    local output="$2"

    awk '
        !/^CONFIG_SB16=/ &&
        !/^CONFIG_ADLIB=/ &&
        !/^CONFIG_GUS=/ &&
        !/^CONFIG_CS4231A=/ &&
        !/^CONFIG_PCSPK=/ &&
        !/^CONFIG_ES1370=/ &&
        !/^CONFIG_AC97=/ &&
        !/^CONFIG_CS4630=/ &&
        !/^CONFIG_HDA=/ { print }
    ' "$base" > "$output" || return 1

    printf '\n# WHP generated i386 audio overrides; retained for Meson regeneration.\n' >> "$output"
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_SB16 "${I386_AUDIO_SB16:-auto}" CONFIG_SB16 || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_ADLIB "${I386_AUDIO_ADLIB:-auto}" CONFIG_ADLIB || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_GUS "${I386_AUDIO_GUS:-auto}" CONFIG_GUS || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_CS4231A "${I386_AUDIO_CS4231A:-auto}" CONFIG_CS4231A || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_PCSPK "${I386_AUDIO_PCSPK:-auto}" CONFIG_PCSPK || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_ES1370 "${I386_AUDIO_ES1370:-auto}" CONFIG_ES1370 || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_AC97 "${I386_AUDIO_AC97:-auto}" CONFIG_AC97 || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_CS4630 "${I386_AUDIO_CS4630:-auto}" CONFIG_CS4630 || return 1
    whp_configure_append_i386_audio_override "$output" I386_AUDIO_HDA "${I386_AUDIO_HDA:-auto}" CONFIG_HDA || return 1
}

whp_configure_build()
{
local ppc_custom_devices=0
local ppc_generated_config=""
local ppc_generated_temp=""
local ppc_audio_signature=""
local i386_custom_audio=0
local i386_generated_config=""
local i386_generated_temp=""
local i386_audio_signature=""
local configure_status=0
local config_file="$BUILD_DIR/.whp-config"
local config_candidate="$BUILD_DIR/.whp-config.new"
local stale_ppc_config=""
local stale_i386_config=""
local host_tag=""

# BUILD_DIR is persistent state, not scratch space.  Establish ownership before
# configuration so a source checkout or host ABI can never silently take over
# another tree.
whp_configure_validate_build_tree_owner || return 1
host_tag="$(whp_configure_host_tag)"

# Incremental target selection is monotonic.  Reconfiguring QEMU in place to
# add a target is safe; removing an already-configured target would make old
# outputs disappear from the same build tree and turns a small follow-up build
# into an avoidable restart.  WHP_INCREMENTAL_BUILD=0 intentionally opts out.
whp_configure_merge_previous_targets "$config_file"
whp_configure_sync_target_args

# QEMU's tracked ppc-softmmu defaults already include both Old World and New
# World Macintosh boards. Keep those defaults, and all device Kconfig defaults,
# unless the user explicitly filters a machine or PPC hardware model.
WHP_PPC_DEVICE_CONFIG_SIGNATURE=not-requested
case ",${QEMU_TARGET_LIST:-}," in
    *,ppc-softmmu,*)
        ppc_audio_signature="$(whp_configure_ppc_audio_signature)" || return 1
        if [[ "${CONFIG_MAC_NEWWORLD:-y}" == y &&
              "${CONFIG_MAC_OLDWORLD:-y}" == y &&
              "$ppc_audio_signature" == \
              'sb16=auto;adlib=auto;gus=auto;cs4231a=auto;pcspk=auto;es1370=auto;ac97=auto;cs4630=auto;hda=auto' ]]; then
            WHP_PPC_DEVICE_CONFIG_SIGNATURE=tracked-defaults
            stale_ppc_config="$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
            if [[ -f "$stale_ppc_config" ]] &&
               ! grep -Eq '# WHP (user overrides generated from \.whpconfig; do not edit\.|temporary user overrides; removed after configure\.|generated PPC machine overrides; retained for Meson regeneration\.|generated PPC device overrides; retained for Meson regeneration\.)' \
                   "$stale_ppc_config"; then
                stale_ppc_config=""
            fi
        else
            ppc_custom_devices=1
            WHP_PPC_DEVICE_CONFIG_SIGNATURE="newworld=${CONFIG_MAC_NEWWORLD:-y};oldworld=${CONFIG_MAC_OLDWORLD:-y};$ppc_audio_signature"
            configure_args+=(--with-devices-ppc=whp-user)
        fi
        ;;
esac

# Audio devices are optional Kconfig models on i386. Keep upstream defaults
# when every menu entry is auto; only an explicit y/n choice creates a target
# preset. Meson records that preset as a source input, so the generated file
# must remain in configs/devices/i386-softmmu while the custom preset is active.
WHP_I386_AUDIO_CONFIG_SIGNATURE=not-requested
case ",${QEMU_TARGET_LIST:-}," in
    *,i386-softmmu,*)
        i386_audio_signature="$(whp_configure_i386_audio_signature)" || return 1
        if [[ "$i386_audio_signature" == \
              'sb16=auto;adlib=auto;gus=auto;cs4231a=auto;pcspk=auto;es1370=auto;ac97=auto;cs4630=auto;hda=auto' ]]; then
            WHP_I386_AUDIO_CONFIG_SIGNATURE=tracked-defaults
            stale_i386_config="$SOURCE_DIR/configs/devices/i386-softmmu/whp-user.mak"
            if [[ -f "$stale_i386_config" ]] &&
               ! grep -Eq '# WHP (temporary i386 audio overrides; removed after configure\.|generated i386 audio overrides; retained for Meson regeneration\.)' \
                   "$stale_i386_config"; then
                stale_i386_config=""
            fi
        else
            i386_custom_audio=1
            WHP_I386_AUDIO_CONFIG_SIGNATURE="$i386_audio_signature"
            configure_args+=(--with-devices-i386=whp-user)
        fi
        ;;
esac

# Custom device presets are persistent Meson source inputs.  Recreate them
# before deciding that an existing configure is reusable, because ignored
# source-tree files can disappear independently of BUILD_DIR/.whp-config.
# Generate candidates in BUILD_DIR so a read-only source tree remains usable
# when an already-present preset is still correct, and avoid timestamp churn
# when the generated contents have not changed.
if [[ "$ppc_custom_devices" == 1 ]]; then
    ppc_generated_config="$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
    ppc_generated_temp="$BUILD_DIR/.whp-ppc-device-config.tmp.$$"
    if ! whp_configure_write_ppc_device_config \
        "$SOURCE_DIR/configs/devices/ppc-softmmu/default.mak" \
        "$ppc_generated_temp"; then
        rm -f "$ppc_generated_temp"
        return 1
    fi
    if [[ -f "$ppc_generated_config" ]] &&
       cmp -s "$ppc_generated_temp" "$ppc_generated_config"; then
        rm -f "$ppc_generated_temp"
        ppc_generated_temp=""
    else
        if [[ ! -w "$(dirname "$ppc_generated_config")" ]]; then
            printf '%s\n' \
                'error: custom PPC device selection requires configs/devices/ppc-softmmu/whp-user.mak,' \
                'but the source configs directory is read-only. The tracked PPC defaults remain buildable.' >&2
            rm -f "$ppc_generated_temp"
            return 1
        fi
        mv "$ppc_generated_temp" "$ppc_generated_config"
        ppc_generated_temp=""
    fi
fi

if [[ "$i386_custom_audio" == 1 ]]; then
    i386_generated_config="$SOURCE_DIR/configs/devices/i386-softmmu/whp-user.mak"
    i386_generated_temp="$BUILD_DIR/.whp-i386-device-config.tmp.$$"
    if ! whp_configure_write_i386_audio_config \
        "$SOURCE_DIR/configs/devices/i386-softmmu/default.mak" \
        "$i386_generated_temp"; then
        rm -f "$i386_generated_temp"
        return 1
    fi
    if [[ -f "$i386_generated_config" ]] &&
       cmp -s "$i386_generated_temp" "$i386_generated_config"; then
        rm -f "$i386_generated_temp"
        i386_generated_temp=""
    else
        if [[ ! -w "$(dirname "$i386_generated_config")" ]]; then
            printf '%s\n' \
                'error: custom i386 audio filtering requires configs/devices/i386-softmmu/whp-user.mak,' \
                'but the source configs directory is read-only. The tracked i386 defaults remain buildable.' >&2
            rm -f "$i386_generated_temp"
            return 1
        fi
        mv "$i386_generated_temp" "$i386_generated_config"
        i386_generated_temp=""
    fi
fi

{
    printf 'HOST_OS=%s\n' "$HOST_OS"
    printf 'PROCESS_ARCH=%s\n' "$PROCESS_ARCH"
    printf 'PHYSICAL_ARCH=%s\n' "$PHYSICAL_ARCH"
    printf 'HOST_ARCH=%s\n' "$HOST_ARCH"
    printf 'HOST_TAG=%s\n' "$host_tag"
    printf 'ROSETTA_TRANSLATED=%s\n' "$ROSETTA_TRANSLATED"
    printf 'MACOS_ALLOW_ROSETTA=%s\n' "$MACOS_ALLOW_ROSETTA"
    printf 'MACOS_VERIFY_TOOLCHAIN=%s\n' "$MACOS_VERIFY_TOOLCHAIN"
    printf 'MACOS_ALLOW_NONCLANG=%s\n' "$MACOS_ALLOW_NONCLANG"
    printf 'MACOS_ALLOW_COMPILER_CONFIG=%s\n' "$MACOS_ALLOW_COMPILER_CONFIG"
    printf 'MACOS_COMPILER_MANIFEST=%s\n' "$MACOS_COMPILER_MANIFEST"
    printf 'MACOS_COMPILER_MANIFEST_SIGNATURE=%s\n' "$MACOS_COMPILER_MANIFEST_SIGNATURE"
    printf 'MACOS_LTO_MANIFEST=%s\n' "$MACOS_LTO_MANIFEST"
    printf 'MACOS_LTO_MANIFEST_SIGNATURE=%s\n' "$MACOS_LTO_MANIFEST_SIGNATURE"
    printf 'CC_FOR_BUILD=%s\n' "$CC_FOR_BUILD"
    printf 'CXX_FOR_BUILD=%s\n' "$CXX_FOR_BUILD"
    printf 'OBJC_FOR_BUILD=%s\n' "$OBJC_FOR_BUILD"
    printf 'STRIP_FOR_BUILD=%s\n' "$STRIP_FOR_BUILD"
    printf 'PKG_CONFIG_FOR_BUILD=%s\n' "$PKG_CONFIG_FOR_BUILD"
    printf 'CC=%s\n' "${CC:-cc}"
    printf 'CXX=%s\n' "${CXX:-c++}"
    printf 'OBJC=%s\n' "${OBJC:-}"
    printf 'CFLAGS=%s\n' "${CFLAGS:-}"
    printf 'CXXFLAGS=%s\n' "${CXXFLAGS:-}"
    printf 'OBJCFLAGS=%s\n' "${OBJCFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
    printf 'DEVELOPER_DIR=%s\n' "${DEVELOPER_DIR:-}"
    printf 'SDKROOT=%s\n' "${SDKROOT:-}"
    printf 'MACOS_SDK_VERSION=%s\n' "${MACOS_SDK_VERSION:-}"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
    printf 'PKG_CONFIG=%s\n' "${PKG_CONFIG:-pkg-config}"
    printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
    printf 'PKG_CONFIG_PATH_FOR_BUILD=%s\n' "${PKG_CONFIG_PATH_FOR_BUILD:-}"
    printf 'HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX:-}"
    printf 'MAKE=%s\n' "${MAKE_CMD:-}"
    printf 'NINJA=%s\n' "${NINJA_CMD:-${NINJA:-}}"
    printf 'PYTHON=%s\n' "${PYTHON:-}"
    printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
    printf 'QEMU_TARGET_LIST=%s\n' "${QEMU_TARGET_LIST:-}"
    printf 'QEMU_HOST_LTO=%s\n' "$QEMU_HOST_LTO"
    printf 'QEMU_HOST_MODULES=%s\n' "${QEMU_HOST_MODULES:-auto}"
    printf 'BUILD_OPENBIOS=%s\n' "$BUILD_OPENBIOS"
    printf 'OPENBIOS_CROSS_COMPILE=%s\n' "$OPENBIOS_CROSS_COMPILE"
    printf 'BOOTSTRAP_POWERPC_TOOLCHAIN=%s\n' "$BOOTSTRAP_POWERPC_TOOLCHAIN"
    printf 'POWERPC_TOOLCHAIN_COMPILER=%s\n' \
        "${POWERPC_TOOLCHAIN_COMPILER:-clang}"
    printf 'POWERPC_TOOLCHAIN_SOURCE_MODE=%s\n' \
        "${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
    printf 'POWERPC_TOOLCHAIN_DIR=%s\n' "$POWERPC_TOOLCHAIN_DIR"
    printf 'CONFIG_MAC_NEWWORLD=%s\n' "${CONFIG_MAC_NEWWORLD:-y}"
    printf 'CONFIG_MAC_OLDWORLD=%s\n' "${CONFIG_MAC_OLDWORLD:-y}"
    printf 'WHP_PPC_DEVICE_CONFIG_SIGNATURE=%s\n' "$WHP_PPC_DEVICE_CONFIG_SIGNATURE"
    printf 'WHP_I386_AUDIO_CONFIG_SIGNATURE=%s\n' "$WHP_I386_AUDIO_CONFIG_SIGNATURE"
    printf 'CONFIGURE_ARG=%s\n' "${configure_args[*]}"
} > "$config_candidate"

if [[ ! -f "$BUILD_DIR/build.ninja" ]] ||
   [[ ! -f "$config_file" ]] ||
   ! cmp -s "$config_candidate" "$config_file"; then
    (
        cd "$BUILD_DIR"
        "$SOURCE_DIR/configure" "${configure_args[@]}"
    ) || configure_status=$?

    rm -f "$ppc_generated_temp" "$i386_generated_temp"
    if [[ "$configure_status" != 0 ]]; then
        rm -f "$config_candidate"
        return "$configure_status"
    fi
    if [[ "$ppc_custom_devices" != 1 && -n "$stale_ppc_config" ]]; then
        rm -f "$stale_ppc_config"
    fi
    if [[ "$i386_custom_audio" != 1 && -n "$stale_i386_config" ]]; then
        rm -f "$stale_i386_config"
    fi
    mv "$config_candidate" "$config_file"
else
    rm -f "$config_candidate"
    if [[ "$ppc_custom_devices" != 1 && -n "$stale_ppc_config" ]]; then
        rm -f "$stale_ppc_config"
    fi
    if [[ "$i386_custom_audio" != 1 && -n "$stale_i386_config" ]]; then
        rm -f "$stale_i386_config"
    fi
fi
}
