#!/usr/bin/env bash

# This file is sourced by macos-builder.bash.  Keep it compatible with the
# Bash 3.2 shipped by macOS.

MACOS_ALLOW_INHERITED_SEARCH_PATHS="${MACOS_ALLOW_INHERITED_SEARCH_PATHS:-0}"
MACOS_ALLOW_MIXED_HOMEBREW="${MACOS_ALLOW_MIXED_HOMEBREW:-0}"

for hygiene_boolean in \
    MACOS_ALLOW_INHERITED_SEARCH_PATHS MACOS_ALLOW_MIXED_HOMEBREW; do
    case "${!hygiene_boolean}" in
        0|1) ;;
        *)
            printf 'error: %s must be 0 or 1\n' "$hygiene_boolean" >&2
            return 1
            ;;
    esac
done
export MACOS_ALLOW_INHERITED_SEARCH_PATHS MACOS_ALLOW_MIXED_HOMEBREW

whp_append_colon_path()
{
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"

    if [[ -n "$current" ]]; then
        printf -v "$variable" '%s:%s' "$value" "$current"
    else
        printf -v "$variable" '%s' "$value"
    fi
    export "$variable"
}

whp_remove_path_entry()
{
    local rejected="$1"
    local entry
    local rebuilt=""
    local entries=()

    IFS=: read -r -a entries <<< "${PATH:-}"
    for entry in "${entries[@]}"; do
        [[ "$entry" == "$rejected" ]] && continue
        if [[ -n "$rebuilt" ]]; then
            rebuilt="$rebuilt:$entry"
        else
            rebuilt="$entry"
        fi
    done
    PATH="$rebuilt"
    export PATH
}

sanitize_macos_build_environment()
{
    local variable
    local stripped=()
    local process_arch
    local opposite_prefix=""
    local expected_brew=""

    if [[ "$MACOS_ALLOW_INHERITED_SEARCH_PATHS" != "1" ]]; then
        for variable in \
            CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH \
            COMPILER_PATH GCC_EXEC_PREFIX LIBRARY_PATH \
            DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH \
            DYLD_INSERT_LIBRARIES CMAKE_PREFIX_PATH CMAKE_LIBRARY_PATH \
            CMAKE_INCLUDE_PATH PKG_CONFIG_PATH PKG_CONFIG_LIBDIR \
            PKG_CONFIG_SYSROOT_DIR ACLOCAL_PATH ARCHFLAGS; do
            if [[ -n "${!variable:-}" ]]; then
                stripped+=("$variable")
                unset "$variable"
            fi
        done
    fi

    process_arch="$(uname -m)"
    case "$process_arch" in
        arm64|aarch64)
            expected_brew=/opt/homebrew/bin/brew
            opposite_prefix=/usr/local
            ;;
        x86_64)
            expected_brew=/usr/local/bin/brew
            opposite_prefix=/opt/homebrew
            ;;
        *)
            printf 'error: unsupported macOS process architecture: %s\n' \
                "$process_arch" >&2
            return 1
            ;;
    esac

    if [[ "$MACOS_ALLOW_MIXED_HOMEBREW" != "1" ]]; then
        whp_remove_path_entry "$opposite_prefix/bin"
        whp_remove_path_entry "$opposite_prefix/sbin"
        case "${HOMEBREW_PREFIX:-}" in
            "$opposite_prefix") unset HOMEBREW_PREFIX ;;
        esac
    fi

    if [[ -x "$expected_brew" ]]; then
        HOMEBREW_PREFIX="$("$expected_brew" --prefix)"
        export HOMEBREW_PREFIX
        whp_remove_path_entry "$HOMEBREW_PREFIX/bin"
        whp_remove_path_entry "$HOMEBREW_PREFIX/sbin"
        whp_append_colon_path PATH "$HOMEBREW_PREFIX/sbin"
        whp_append_colon_path PATH "$HOMEBREW_PREFIX/bin"
    fi

    if [[ ${stripped[0]+set} == set ]]; then
        printf 'macOS build environment: removed inherited search variables: %s\n' \
            "${stripped[*]}"
    fi
}

whp_set_compiler_command()
{
    local command_string="$1"

    case "$command_string" in
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>') return 1 ;;
    esac

    WHP_COMPILER_COMMAND=()
    read -r -a WHP_COMPILER_COMMAND <<< "$command_string"
    [[ "${#WHP_COMPILER_COMMAND[@]}" -gt 0 ]] || return 1
    command -v "${WHP_COMPILER_COMMAND[0]}" >/dev/null 2>&1
}

whp_compiler_signature()
{
    local command_string="$1"
    local version="unavailable"
    local machine="unavailable"

    if whp_set_compiler_command "$command_string"; then
        version="$("${WHP_COMPILER_COMMAND[@]}" --version 2>&1 |
            sed -n '1p' || true)"
        machine="$("${WHP_COMPILER_COMMAND[@]}" -dumpmachine 2>/dev/null |
            sed -n '1p' || true)"
    fi
    printf '%s|%s|%s\n' "$command_string" "$version" "$machine"
}

whp_normalize_build_dir()
{
    local requested="$1"
    local parent
    local leaf

    case "$requested" in
        /*) ;;
        *) requested="$SOURCE_DIR/$requested" ;;
    esac
    parent="$(dirname "$requested")"
    leaf="$(basename "$requested")"
    mkdir -p "$parent"
    parent="$(cd -- "$parent" && pwd -P)"
    printf '%s/%s\n' "$parent" "$leaf"
}

whp_build_tree_owned()
{
    local build_dir="$1"

    if [[ -f "$build_dir/.whp-build-owner" ]] &&
       grep -Fqx "SOURCE_DIR=$SOURCE_DIR" "$build_dir/.whp-build-owner"; then
        return 0
    fi
    if [[ -f "$build_dir/.whp-config" ]] &&
       grep -Fqx "SOURCE_DIR=$SOURCE_DIR" "$build_dir/.whp-config"; then
        return 0
    fi
    if [[ -f "$build_dir/.whp-macos-build-identity" ]] &&
       grep -Fqx "SOURCE_DIR=$SOURCE_DIR" \
           "$build_dir/.whp-macos-build-identity"; then
        return 0
    fi
    return 1
}

whp_recorded_host_arch()
{
    local file="$1"
    local value=""

    [[ -f "$file" ]] || return 0
    value="$(sed -n 's/^HOST_ARCH=//p' "$file" | sed -n '1p')"
    case "$value" in
        arm64|aarch64) printf 'arm64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        '') ;;
        *) printf '%s\n' "$value" ;;
    esac
}

whp_require_persistent_path_outside_build()
{
    local variable="$1"
    local value="${!variable}"

    value="$(whp_normalize_build_dir "$value")"
    printf -v "$variable" '%s' "$value"
    export "$variable"

    case "$value/" in
        "$BUILD_DIR/"*)
            printf '%s\n' \
                "error: $variable must be outside BUILD_DIR." \
                "BUILD_DIR=$BUILD_DIR" \
                "$variable=$value" \
                'Persistent firmware tools must survive QEMU build-tree maintenance.' >&2
            return 1
            ;;
    esac
}

prepare_macos_build_tree()
{
    local process_arch
    local host_arch
    local default_build_dir
    local build_parent
    local legacy_tools_dir
    local toolchain_root
    local identity_file
    local identity_candidate
    local owner_file
    local build_has_files=0
    local expected_pkg_config_path=""
    local recorded_arch=""

    process_arch="$(uname -m)"
    case "$process_arch" in
        arm64|aarch64) host_arch=arm64 ;;
        x86_64|amd64) host_arch=x86_64 ;;
        *)
            printf 'error: unsupported macOS process architecture: %s\n' \
                "$process_arch" >&2
            return 1
            ;;
    esac

    # build.sh normally supplies an absolute, runner-neutral BUILD_DIR.  Keep a
    # compatible fallback for direct test harnesses without reintroducing a PPC
    # target name into host build-tree identity.
    default_build_dir="$SOURCE_DIR/build/whp-${host_arch}-apple-darwin"
    BUILD_DIR="$(whp_normalize_build_dir "${BUILD_DIR:-$default_build_dir}")"
    export BUILD_DIR

    case "$BUILD_DIR" in
        /|"$SOURCE_DIR"|"${HOME:-/nonexistent}")
            printf 'error: refusing unsafe macOS BUILD_DIR: %s\n' "$BUILD_DIR" >&2
            return 1
            ;;
    esac

    build_parent="$(dirname "$BUILD_DIR")"
    legacy_tools_dir="$BUILD_DIR/firmware-tools"
    if [[ -z "${OPENBIOS_TOOLS_DIR:-}" ]]; then
        OPENBIOS_TOOLS_DIR="$build_parent/whp-firmware-tools-${host_arch}-apple-darwin"
        if [[ ! -e "$OPENBIOS_TOOLS_DIR" && -d "$legacy_tools_dir" ]]; then
            mkdir -p "$(dirname "$OPENBIOS_TOOLS_DIR")"
            mv "$legacy_tools_dir" "$OPENBIOS_TOOLS_DIR"
            printf 'Moved firmware tools outside the QEMU Meson tree: %s\n' \
                "$OPENBIOS_TOOLS_DIR"
        fi
    fi
    whp_require_persistent_path_outside_build OPENBIOS_TOOLS_DIR || return 1

    POWERPC_TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$OPENBIOS_TOOLS_DIR/powerpc-elf}"
    whp_require_persistent_path_outside_build POWERPC_TOOLCHAIN_DIR || return 1
    toolchain_root="$(dirname "$POWERPC_TOOLCHAIN_DIR")"
    POWERPC_TOOLCHAIN_WORK_DIR="$toolchain_root/toolchain-work/powerpc-elf"
    POWERPC_TOOLCHAIN_DOWNLOAD_DIR="$toolchain_root/toolchain-downloads"
    whp_require_persistent_path_outside_build POWERPC_TOOLCHAIN_WORK_DIR || return 1
    whp_require_persistent_path_outside_build POWERPC_TOOLCHAIN_DOWNLOAD_DIR || return 1
    export OPENBIOS_TOOLS_DIR POWERPC_TOOLCHAIN_DIR \
        POWERPC_TOOLCHAIN_WORK_DIR POWERPC_TOOLCHAIN_DOWNLOAD_DIR

    if [[ -n "${HOMEBREW_PREFIX:-}" ]]; then
        expected_pkg_config_path="$HOMEBREW_PREFIX/lib/pkgconfig:$HOMEBREW_PREFIX/share/pkgconfig"
    fi

    identity_candidate="$(mktemp "${TMPDIR:-/tmp}/whp-macos-build-identity.XXXXXX")"
    {
        printf 'SCHEMA=4\n'
        printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
        printf 'BUILD_DIR=%s\n' "$BUILD_DIR"
        printf 'PROCESS_ARCH=%s\n' "$process_arch"
        printf 'HOST_ARCH=%s\n' "$host_arch"
        printf 'HOST_TAG=%s-apple-darwin\n' "$host_arch"
        printf 'SDKROOT=%s\n' "${SDKROOT:-}"
        printf 'MACOS_SDK_VERSION=%s\n' "${MACOS_SDK_VERSION:-}"
        printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
        printf 'DEVELOPER_DIR=%s\n' "${DEVELOPER_DIR:-}"
        printf 'CC=%s\n' "$(whp_compiler_signature "${CC:-cc}")"
        printf 'CXX=%s\n' "$(whp_compiler_signature "${CXX:-c++}")"
        printf 'OBJC=%s\n' "$(whp_compiler_signature "${OBJC:-${CC:-cc}}")"
        printf 'CC_FOR_BUILD=%s\n' "$(whp_compiler_signature "${CC_FOR_BUILD:-${CC:-cc}}")"
        printf 'CFLAGS=%s\n' "${CFLAGS:-}"
        printf 'CXXFLAGS=%s\n' "${CXXFLAGS:-}"
        printf 'OBJCFLAGS=%s\n' "${OBJCFLAGS:-}"
        printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
        printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
        printf 'QEMU_HOST_LTO=%s\n' "${QEMU_HOST_LTO:-automatic}"
        printf 'HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX:-}"
        printf 'EXPECTED_PKG_CONFIG_PATH=%s\n' "$expected_pkg_config_path"
        printf 'CONFIG_SHELL=%s\n' "${CONFIG_SHELL:-}"
        printf 'MACOS_ALLOW_INHERITED_SEARCH_PATHS=%s\n' "$MACOS_ALLOW_INHERITED_SEARCH_PATHS"
        printf 'MACOS_ALLOW_MIXED_HOMEBREW=%s\n' "$MACOS_ALLOW_MIXED_HOMEBREW"
        printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
        printf 'CPATH=%s\n' "${CPATH:-}"
        printf 'C_INCLUDE_PATH=%s\n' "${C_INCLUDE_PATH:-}"
        printf 'CPLUS_INCLUDE_PATH=%s\n' "${CPLUS_INCLUDE_PATH:-}"
        printf 'OBJC_INCLUDE_PATH=%s\n' "${OBJC_INCLUDE_PATH:-}"
        printf 'COMPILER_PATH=%s\n' "${COMPILER_PATH:-}"
        printf 'GCC_EXEC_PREFIX=%s\n' "${GCC_EXEC_PREFIX:-}"
        printf 'LIBRARY_PATH=%s\n' "${LIBRARY_PATH:-}"
        printf 'DYLD_LIBRARY_PATH=%s\n' "${DYLD_LIBRARY_PATH:-}"
        printf 'DYLD_FALLBACK_LIBRARY_PATH=%s\n' "${DYLD_FALLBACK_LIBRARY_PATH:-}"
    } > "$identity_candidate"

    mkdir -p "$BUILD_DIR"
    identity_file="$BUILD_DIR/.whp-macos-build-identity"
    owner_file="$BUILD_DIR/.whp-build-owner"

    if [[ -n "$(ls -A "$BUILD_DIR" 2>/dev/null)" ]]; then
        build_has_files=1
    fi

    if [[ "$build_has_files" == 1 ]] && ! whp_build_tree_owned "$BUILD_DIR"; then
        rm -f "$identity_candidate"
        printf '%s\n' \
            "error: refusing to reuse an unowned build directory: $BUILD_DIR" \
            'Choose an empty BUILD_DIR or a WHP-owned tree for this source checkout.' >&2
        return 1
    fi

    recorded_arch="$(whp_recorded_host_arch "$identity_file")"
    if [[ -z "$recorded_arch" ]]; then
        recorded_arch="$(whp_recorded_host_arch "$BUILD_DIR/.whp-config")"
    fi
    if [[ -n "$recorded_arch" && "$recorded_arch" != "$host_arch" ]]; then
        rm -f "$identity_candidate"
        printf '%s\n' \
            "error: BUILD_DIR belongs to host architecture $recorded_arch, not $host_arch." \
            "build directory: $BUILD_DIR" \
            'Use a different BUILD_DIR for a different host ABI; the existing tree was preserved.' >&2
        return 1
    fi

    if [[ -f "$identity_file" ]] && ! cmp -s "$identity_candidate" "$identity_file"; then
        printf '%s\n' \
            'macOS build identity changed; preserving the existing QEMU build tree.' \
            'QEMU/Meson/Ninja will reconfigure and rebuild only stale state.'
    elif [[ ! -f "$identity_file" && "$build_has_files" == 1 ]]; then
        printf '%s\n' \
            'Adopting an older WHP build tree without deleting existing outputs.'
    fi

    {
        printf 'SCHEMA=2\n'
        printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
        printf 'BUILD_DIR=%s\n' "$BUILD_DIR"
        printf 'HOST_TAG=%s-apple-darwin\n' "$host_arch"
    } > "$owner_file.new"
    mv "$owner_file.new" "$owner_file"
    mv "$identity_candidate" "$identity_file"
}
