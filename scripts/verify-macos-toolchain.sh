#!/usr/bin/env bash

set -euo pipefail

: "${MACOS_HOST_ARCH:?MACOS_HOST_ARCH is required}"
: "${BUILD_MACHINE_ARCH:?BUILD_MACHINE_ARCH is required}"
: "${CC:?CC is required}"
: "${CXX:?CXX is required}"
: "${OBJC:?OBJC is required}"
: "${CC_FOR_BUILD:?CC_FOR_BUILD is required}"
: "${SDKROOT:?SDKROOT is required}"

MACOS_COMPILER_MANIFEST="${MACOS_COMPILER_MANIFEST:-.whp-macos-toolchain}"
MACOS_COMPILER_PROBE_DIR="${MACOS_COMPILER_PROBE_DIR:-${MACOS_COMPILER_MANIFEST}.d}"
MACOS_ALLOW_NONCLANG="${MACOS_ALLOW_NONCLANG:-0}"
MACOS_ALLOW_COMPILER_CONFIG="${MACOS_ALLOW_COMPILER_CONFIG:-0}"

for boolean_value in MACOS_ALLOW_NONCLANG MACOS_ALLOW_COMPILER_CONFIG; do
    case "${!boolean_value}" in
        0|1) ;;
        *)
            printf 'error: %s must be 0 or 1\n' "$boolean_value" >&2
            exit 1
            ;;
    esac
done

case "$MACOS_HOST_ARCH" in
    arm64|x86_64) ;;
    *) printf 'error: unsupported macOS host architecture: %s\n' "$MACOS_HOST_ARCH" >&2; exit 1 ;;
esac
case "$BUILD_MACHINE_ARCH" in
    arm64|x86_64) ;;
    *) printf 'error: unsupported macOS build architecture: %s\n' "$BUILD_MACHINE_ARCH" >&2; exit 1 ;;
esac

if [[ ! -d "$SDKROOT" ]]; then
    printf 'error: macOS SDK does not exist: %s\n' "$SDKROOT" >&2
    exit 1
fi
for required in xcrun awk sed; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: macOS compiler probe dependency not found: %s\n' "$required" >&2
        exit 1
    fi
done

mkdir -p "$MACOS_COMPILER_PROBE_DIR" "$(dirname "$MACOS_COMPILER_MANIFEST")"
manifest_candidate="${MACOS_COMPILER_MANIFEST}.new.$$"
cleanup()
{
    rm -f "$manifest_candidate"
}
trap cleanup EXIT

canonical_arch_from_triple()
{
    case "$1" in
        arm64-*|aarch64-*) printf 'arm64\n' ;;
        x86_64-*|amd64-*) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

set_command()
{
    local command_string="$1"

    case "$command_string" in
        *';'*|*'|'*|*'&'*|*'<'*|*'>'*)
            printf 'error: compiler commands may not contain shell operators: %s\n' \
                "$command_string" >&2
            exit 1
            ;;
    esac

    COMPILER_CMD=()
    read -r -a COMPILER_CMD <<< "$command_string"
    if [[ "${#COMPILER_CMD[@]}" -eq 0 ]]; then
        printf 'error: empty compiler command\n' >&2
        exit 1
    fi
    if ! command -v "${COMPILER_CMD[0]}" >/dev/null 2>&1; then
        printf 'error: compiler command is not executable: %s\n' \
            "${COMPILER_CMD[0]}" >&2
        exit 1
    fi
}

set_identity_command()
{
    local command_string="$1"
    local index token base

    set_command "$command_string"
    DRIVER_INDEX=-1
    for ((index = 0; index < ${#COMPILER_CMD[@]}; index++)); do
        token="${COMPILER_CMD[$index]}"
        base="$(basename "$token")"
        case "$base" in
            env|arch|xcrun|ccache|sccache|distcc|icecc) continue ;;
        esac
        case "$token" in
            *=*|-*) continue ;;
        esac
        if command -v "$token" >/dev/null 2>&1; then
            DRIVER_INDEX=$index
            break
        fi
    done

    if [[ "$DRIVER_INDEX" -lt 0 ]]; then
        printf 'error: could not resolve compiler driver from: %s\n' \
            "$command_string" >&2
        exit 1
    fi

    DRIVER_TOKEN="${COMPILER_CMD[$DRIVER_INDEX]}"
    DRIVER_PATH="$(command -v "$DRIVER_TOKEN" 2>/dev/null || true)"
    if [[ -z "$DRIVER_PATH" ]]; then
        printf 'error: compiler driver is not executable: %s\n' "$DRIVER_TOKEN" >&2
        exit 1
    fi
    IDENTITY_CMD=("${COMPILER_CMD[@]:$DRIVER_INDEX}")
}

split_flags()
{
    FLAG_ARRAY=()
    if [[ -n "$1" ]]; then
        read -r -a FLAG_ARRAY <<< "$1"
    fi
}

first_line()
{
    sed -n '1p'
}

write_identity()
{
    local role="$1"
    local command_string="$2"
    local expected_arch="$3"
    local language_role="$4"
    local version target target_arch resource_dir driver_base
    local default_config_state no_default_target no_default_arch

    set_identity_command "$command_string"
    driver_base="$(basename "$DRIVER_PATH")"
    version="$("$DRIVER_PATH" --version 2>&1 | first_line)"

    if [[ "$MACOS_ALLOW_NONCLANG" != "1" ]] &&
       [[ "$version" != *clang* && "$version" != *Clang* ]]; then
        printf 'error: %s is not a Clang-family driver: %s\n' \
            "$role" "$version" >&2
        exit 1
    fi

    case "$language_role:$driver_base" in
        c:*++|c:clang-cl*|c:clang-cpp*|c:cpp*)
            printf 'error: %s resolves to the wrong Clang driver mode: %s\n' \
                "$role" "$DRIVER_PATH" >&2
            exit 1
            ;;
        objc:*++|objc:clang-cl*|objc:clang-cpp*|objc:cpp*)
            printf 'error: %s cannot act as the Objective-C driver: %s\n' \
                "$role" "$DRIVER_PATH" >&2
            exit 1
            ;;
    esac

    target="$("${COMPILER_CMD[@]}" -print-target-triple 2>/dev/null || \
              "${COMPILER_CMD[@]}" -dumpmachine 2>/dev/null || true)"
    target="$(printf '%s\n' "$target" | first_line)"
    target_arch="$(canonical_arch_from_triple "$target" 2>/dev/null || true)"
    if [[ "$target_arch" != "$expected_arch" ]]; then
        printf '%s\n' \
            "error: $role targets '$target', expected $expected_arch macOS." \
            "command: $command_string" >&2
        exit 1
    fi

    resource_dir="$("${COMPILER_CMD[@]}" -print-resource-dir 2>/dev/null || true)"
    resource_dir="$(printf '%s\n' "$resource_dir" | first_line)"
    if [[ "$MACOS_ALLOW_NONCLANG" != "1" && ! -d "$resource_dir" ]]; then
        printf 'error: %s reported an unusable Clang resource directory: %s\n' \
            "$role" "${resource_dir:-<empty>}" >&2
        exit 1
    fi

    default_config_state=unsupported
    no_default_target=""
    no_default_arch=""
    if "${COMPILER_CMD[@]}" --no-default-config -print-target-triple \
         >/dev/null 2>&1; then
        default_config_state=stable
        no_default_target="$("${COMPILER_CMD[@]}" --no-default-config \
                              -print-target-triple 2>/dev/null | first_line)"
        no_default_arch="$(canonical_arch_from_triple "$no_default_target" \
                            2>/dev/null || true)"
        if [[ "$no_default_target" != "$target" ]]; then
            default_config_state=changes-target
            if [[ "$MACOS_ALLOW_COMPILER_CONFIG" != "1" ]]; then
                printf '%s\n' \
                    "error: a default Clang configuration changes $role's target." \
                    "configured target: $target" \
                    "without config:    $no_default_target" \
                    'set MACOS_ALLOW_COMPILER_CONFIG=1 only when this is intentional.' >&2
                exit 1
            fi
        elif [[ "$no_default_arch" != "$expected_arch" ]]; then
            printf 'error: %s has an invalid no-config target: %s\n' \
                "$role" "$no_default_target" >&2
            exit 1
        fi
    fi

    {
        printf '%s_COMMAND=%s\n' "$role" "$command_string"
        printf '%s_DRIVER=%s\n' "$role" "$DRIVER_PATH"
        printf '%s_VERSION=%s\n' "$role" "$version"
        printf '%s_TARGET_TRIPLE=%s\n' "$role" "$target"
        printf '%s_RESOURCE_DIR=%s\n' "$role" "$resource_dir"
        printf '%s_DEFAULT_CONFIG=%s\n' "$role" "$default_config_state"
        printf '%s_NO_DEFAULT_CONFIG_TARGET=%s\n' "$role" "$no_default_target"
    } >> "$manifest_candidate"
}

output_arches()
{
    xcrun lipo -archs "$1" 2>/dev/null || true
}

require_output_arch()
{
    local role="$1"
    local file="$2"
    local expected="$3"
    local arches

    arches="$(output_arches "$file")"
    case " $arches " in
        *" $expected "*) ;;
        *)
            printf 'error: %s produced Mach-O architecture %s, expected %s\n' \
                "$role" "${arches:-<unknown>}" "$expected" >&2
            exit 1
            ;;
    esac
    printf '%s_OUTPUT_ARCHES=%s\n' "$role" "$arches" >> "$manifest_candidate"
}

compile_c_probe()
{
    local role="$1"
    local command_string="$2"
    local expected_arch="$3"
    local source="$MACOS_COMPILER_PROBE_DIR/${role}.c"
    local output="$MACOS_COMPILER_PROBE_DIR/${role}"

    cat > "$source" <<'SOURCE'
#include <stdlib.h>
int main(void) { return EXIT_SUCCESS; }
SOURCE
    set_command "$command_string"
    split_flags "${CFLAGS:-}"
    C_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=("${FLAG_ARRAY[@]}")
    "${COMPILER_CMD[@]}" "${CPP_FLAGS[@]}" "${C_FLAGS[@]}" \
        -x c "$source" -o "$output" "${LD_FLAGS[@]}"
    require_output_arch "$role" "$output" "$expected_arch"
}

compile_build_probe()
{
    local role=CC_FOR_BUILD
    local source="$MACOS_COMPILER_PROBE_DIR/${role}.c"
    local output="$MACOS_COMPILER_PROBE_DIR/${role}"

    cat > "$source" <<'SOURCE'
int main(void) { return 0; }
SOURCE
    set_command "$CC_FOR_BUILD"
    "${COMPILER_CMD[@]}" -isysroot "$SDKROOT" -x c "$source" -o "$output"
    require_output_arch "$role" "$output" "$BUILD_MACHINE_ARCH"
}

compile_cxx_probe()
{
    local source="$MACOS_COMPILER_PROBE_DIR/CXX.cc"
    local output="$MACOS_COMPILER_PROBE_DIR/CXX"

    cat > "$source" <<'SOURCE'
#include <vector>
int main(void) { std::vector<int> values(1, 0); return values[0]; }
SOURCE
    set_command "$CXX"
    split_flags "${CXXFLAGS:-}"
    CXX_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=("${FLAG_ARRAY[@]}")
    "${COMPILER_CMD[@]}" "${CPP_FLAGS[@]}" "${CXX_FLAGS[@]}" \
        -x c++ "$source" -o "$output" "${LD_FLAGS[@]}"
    require_output_arch CXX "$output" "$MACOS_HOST_ARCH"
}

compile_objc_probe()
{
    local source="$MACOS_COMPILER_PROBE_DIR/OBJC.m"
    local output="$MACOS_COMPILER_PROBE_DIR/OBJC"

    cat > "$source" <<'SOURCE'
#import <Cocoa/Cocoa.h>
int main(void) { @autoreleasepool { return NSApp == nil ? 0 : 0; } }
SOURCE
    set_command "$OBJC"
    split_flags "${OBJCFLAGS:-}"
    OBJC_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=("${FLAG_ARRAY[@]}")
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=("${FLAG_ARRAY[@]}")
    "${COMPILER_CMD[@]}" "${CPP_FLAGS[@]}" "${OBJC_FLAGS[@]}" \
        -x objective-c "$source" -o "$output" -framework Cocoa \
        "${LD_FLAGS[@]}"
    require_output_arch OBJC "$output" "$MACOS_HOST_ARCH"
}

{
    printf 'WHP_MACOS_TOOLCHAIN_SCHEMA=1\n'
    printf 'MACOS_HOST_ARCH=%s\n' "$MACOS_HOST_ARCH"
    printf 'BUILD_MACHINE_ARCH=%s\n' "$BUILD_MACHINE_ARCH"
    printf 'SDKROOT=%s\n' "$SDKROOT"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
} > "$manifest_candidate"

write_identity CC "$CC" "$MACOS_HOST_ARCH" c
write_identity CXX "$CXX" "$MACOS_HOST_ARCH" cxx
write_identity OBJC "$OBJC" "$MACOS_HOST_ARCH" objc
write_identity CC_FOR_BUILD "$CC_FOR_BUILD" "$BUILD_MACHINE_ARCH" c

compile_c_probe CC "$CC" "$MACOS_HOST_ARCH"
compile_cxx_probe
compile_objc_probe
compile_build_probe

for role in CC CXX OBJC CC_FOR_BUILD; do
    command_var="$role"
    command_string="${!command_var}"
    set_identity_command "$command_string"
    source="$MACOS_COMPILER_PROBE_DIR/${role}.identity.c"
    printf 'int whp_compiler_identity(void) { return 0; }\n' > "$source"
    "${COMPILER_CMD[@]}" -### -x c -c "$source" \
        2> "$MACOS_COMPILER_PROBE_DIR/${role}.pipeline" || true
done

mv -f "$manifest_candidate" "$MACOS_COMPILER_MANIFEST"
trap - EXIT
printf 'Verified macOS compiler toolchain: %s\n' "$MACOS_COMPILER_MANIFEST"
