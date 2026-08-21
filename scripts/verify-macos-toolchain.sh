#!/usr/bin/env bash

set -euo pipefail

: "${CC:?CC is required}"
: "${CXX:?CXX is required}"
: "${OBJC:?OBJC is required}"
: "${CC_FOR_BUILD:?CC_FOR_BUILD is required}"
: "${SDKROOT:?SDKROOT is required}"

case "$(uname -m)" in
    arm64|aarch64) host_arch=arm64 ;;
    x86_64|amd64) host_arch=x86_64 ;;
    *)
        printf 'error: unsupported macOS process architecture: %s\n' "$(uname -m)" >&2
        exit 1
        ;;
esac

MACOS_COMPILER_MANIFEST="${MACOS_COMPILER_MANIFEST:-.whp-macos-toolchain}"
MACOS_COMPILER_PROBE_DIR="${MACOS_COMPILER_PROBE_DIR:-${MACOS_COMPILER_MANIFEST}.d}"
MACOS_COMPILER_INPUTS="${MACOS_COMPILER_MANIFEST}.inputs"
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

if [[ ! -d "$SDKROOT" ]]; then
    printf 'error: macOS SDK does not exist: %s\n' "$SDKROOT" >&2
    exit 1
fi
for required in xcrun awk sed cksum cmp stat; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: macOS compiler probe dependency not found: %s\n' "$required" >&2
        exit 1
    fi
done

mkdir -p "$MACOS_COMPILER_PROBE_DIR" "$(dirname "$MACOS_COMPILER_MANIFEST")"
manifest_candidate="${MACOS_COMPILER_MANIFEST}.new.$$"
inputs_candidate="${MACOS_COMPILER_INPUTS}.new.$$"
cleanup()
{
    rm -f "$manifest_candidate" "$inputs_candidate"
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

    QUERY_CMD=()
    skip_cache_prefix=0
    for ((index = 0; index < DRIVER_INDEX; index++)); do
        token="${COMPILER_CMD[$index]}"
        base="$(basename "$token")"
        case "$base" in
            ccache|sccache|distcc|icecc)
                skip_cache_prefix=1
                continue
                ;;
        esac
        if [[ "$skip_cache_prefix" == "0" ]]; then
            QUERY_CMD+=("$token")
        fi
    done
    QUERY_CMD+=("${COMPILER_CMD[@]:$DRIVER_INDEX}")
}

split_flags()
{
    FLAG_ARRAY=()
    if [[ -n "$1" ]]; then
        read -r -a FLAG_ARRAY <<< "$1"
    fi
}

# Bash 3.2 treats an empty array as unset when nounset is active.  Keep every
# optional flag-array copy and expansion guarded with the parameter + form.

first_line()
{
    sed -n '1p'
}

file_metadata_signature()
{
    local path="$1"
    local signature=""

    if signature="$(stat -L -f '%z:%m' "$path" 2>/dev/null)"; then
        printf '%s\n' "$signature"
        return 0
    fi
    if signature="$(stat -L -c '%s:%Y' "$path" 2>/dev/null)"; then
        printf '%s\n' "$signature"
        return 0
    fi
    if [[ -f "$path" ]]; then
        cksum "$path" | awk '{print $1 ":" $2}'
        return 0
    fi
    printf 'missing\n'
}

write_cached_value()
{
    local key="$1"
    local value="$2"

    printf '%s=%q\n' "$key" "$value" >> "$inputs_candidate"
}

write_cached_command_identity()
{
    local role="$1"
    local command_string="$2"
    local version=""
    local target=""
    local resource_dir=""
    local no_default_target="unsupported"

    set_identity_command "$command_string"
    version="$("$DRIVER_PATH" --version 2>&1 | first_line)"
    target="$("${QUERY_CMD[@]}" -print-target-triple 2>/dev/null || \
              "${QUERY_CMD[@]}" -dumpmachine 2>/dev/null || true)"
    target="$(printf '%s\n' "$target" | first_line)"
    resource_dir="$("${QUERY_CMD[@]}" -print-resource-dir 2>/dev/null || true)"
    resource_dir="$(printf '%s\n' "$resource_dir" | first_line)"
    if "${QUERY_CMD[@]}" --no-default-config -print-target-triple \
         >/dev/null 2>&1; then
        no_default_target="$("${QUERY_CMD[@]}" --no-default-config \
                              -print-target-triple 2>/dev/null | first_line)"
    fi

    write_cached_value "${role}_COMMAND" "$command_string"
    write_cached_value "${role}_DRIVER" "$DRIVER_PATH"
    write_cached_value "${role}_DRIVER_STAT" \
        "$(file_metadata_signature "$DRIVER_PATH")"
    write_cached_value "${role}_VERSION" "$version"
    write_cached_value "${role}_TARGET_TRIPLE" "$target"
    write_cached_value "${role}_RESOURCE_DIR" "$resource_dir"
    write_cached_value "${role}_RESOURCE_STAT" \
        "$(file_metadata_signature "$resource_dir")"
    write_cached_value "${role}_NO_DEFAULT_CONFIG_TARGET" "$no_default_target"
}

write_toolchain_cache_identity()
{
    local verifier_signature=""
    local sdk_version="${MACOS_SDK_VERSION:-}"
    local sdk_settings="$SDKROOT/SDKSettings.json"

    verifier_signature="$(cksum "$0" | awk '{print $1 ":" $2}')"
    if [[ -z "$sdk_version" ]]; then
        sdk_version="$(xcrun --sdk "$SDKROOT" --show-sdk-version 2>/dev/null || true)"
    fi
    if [[ ! -e "$sdk_settings" ]]; then
        sdk_settings="$SDKROOT/SDKSettings.plist"
    fi

    : > "$inputs_candidate"
    write_cached_value WHP_MACOS_TOOLCHAIN_INPUT_SCHEMA 1
    write_cached_value VERIFIER_SIGNATURE "$verifier_signature"
    write_cached_value HOST_ARCH "$host_arch"
    write_cached_value SDKROOT "$SDKROOT"
    write_cached_value SDKROOT_STAT "$(file_metadata_signature "$SDKROOT")"
    write_cached_value SDK_VERSION "$sdk_version"
    write_cached_value SDK_SETTINGS "$sdk_settings"
    write_cached_value SDK_SETTINGS_STAT \
        "$(file_metadata_signature "$sdk_settings")"
    write_cached_value MACOSX_DEPLOYMENT_TARGET \
        "${MACOSX_DEPLOYMENT_TARGET:-}"
    write_cached_value MACOS_ALLOW_NONCLANG "$MACOS_ALLOW_NONCLANG"
    write_cached_value MACOS_ALLOW_COMPILER_CONFIG \
        "$MACOS_ALLOW_COMPILER_CONFIG"
    write_cached_value CFLAGS "${CFLAGS:-}"
    write_cached_value CXXFLAGS "${CXXFLAGS:-}"
    write_cached_value OBJCFLAGS "${OBJCFLAGS:-}"
    write_cached_value CPPFLAGS "${CPPFLAGS:-}"
    write_cached_value LDFLAGS "${LDFLAGS:-}"

    write_cached_command_identity CC "$CC"
    write_cached_command_identity CXX "$CXX"
    write_cached_command_identity OBJC "$OBJC"
    write_cached_command_identity CC_FOR_BUILD "$CC_FOR_BUILD"
}

write_toolchain_cache_identity
if [[ -f "$MACOS_COMPILER_MANIFEST" ]] &&
   grep -Fqx 'WHP_MACOS_TOOLCHAIN_SCHEMA=2' "$MACOS_COMPILER_MANIFEST" &&
   [[ -f "$MACOS_COMPILER_INPUTS" ]] &&
   cmp -s "$inputs_candidate" "$MACOS_COMPILER_INPUTS"; then
    rm -f "$inputs_candidate"
    trap - EXIT
    printf 'Reused cached macOS compiler toolchain verification: %s\n' \
        "$MACOS_COMPILER_MANIFEST"
    exit 0
fi

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

    target="$("${QUERY_CMD[@]}" -print-target-triple 2>/dev/null || \
              "${QUERY_CMD[@]}" -dumpmachine 2>/dev/null || true)"
    target="$(printf '%s\n' "$target" | first_line)"
    target_arch="$(canonical_arch_from_triple "$target" 2>/dev/null || true)"
    if [[ "$target_arch" != "$expected_arch" ]]; then
        printf '%s\n' \
            "error: $role targets '$target', expected $expected_arch macOS." \
            "command: $command_string" >&2
        exit 1
    fi

    resource_dir="$("${QUERY_CMD[@]}" -print-resource-dir 2>/dev/null || true)"
    resource_dir="$(printf '%s\n' "$resource_dir" | first_line)"
    if [[ "$MACOS_ALLOW_NONCLANG" != "1" && ! -d "$resource_dir" ]]; then
        printf 'error: %s reported an unusable Clang resource directory: %s\n' \
            "$role" "${resource_dir:-<empty>}" >&2
        exit 1
    fi

    default_config_state=unsupported
    no_default_target=""
    no_default_arch=""
    if "${QUERY_CMD[@]}" --no-default-config -print-target-triple \
         >/dev/null 2>&1; then
        default_config_state=stable
        no_default_target="$("${QUERY_CMD[@]}" --no-default-config \
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
    C_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    "${COMPILER_CMD[@]}" \
        ${CPP_FLAGS[@]+"${CPP_FLAGS[@]}"} \
        ${C_FLAGS[@]+"${C_FLAGS[@]}"} \
        -x c "$source" -o "$output" \
        ${LD_FLAGS[@]+"${LD_FLAGS[@]}"}
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
    require_output_arch "$role" "$output" "$host_arch"
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
    CXX_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    "${COMPILER_CMD[@]}" \
        ${CPP_FLAGS[@]+"${CPP_FLAGS[@]}"} \
        ${CXX_FLAGS[@]+"${CXX_FLAGS[@]}"} \
        -x c++ "$source" -o "$output" \
        ${LD_FLAGS[@]+"${LD_FLAGS[@]}"}
    require_output_arch CXX "$output" "$host_arch"
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
    OBJC_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${CPPFLAGS:-}"
    CPP_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "${LDFLAGS:-}"
    LD_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    "${COMPILER_CMD[@]}" \
        ${CPP_FLAGS[@]+"${CPP_FLAGS[@]}"} \
        ${OBJC_FLAGS[@]+"${OBJC_FLAGS[@]}"} \
        -x objective-c "$source" -o "$output" -framework Cocoa \
        ${LD_FLAGS[@]+"${LD_FLAGS[@]}"}
    require_output_arch OBJC "$output" "$host_arch"
}

{
    printf 'WHP_MACOS_TOOLCHAIN_SCHEMA=2\n'
    printf 'HOST_ARCH=%s\n' "$host_arch"
    printf 'SDKROOT=%s\n' "$SDKROOT"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
} > "$manifest_candidate"

write_identity CC "$CC" "$host_arch" c
write_identity CXX "$CXX" "$host_arch" cxx
write_identity OBJC "$OBJC" "$host_arch" objc
write_identity CC_FOR_BUILD "$CC_FOR_BUILD" "$host_arch" c

compile_c_probe CC "$CC" "$host_arch"
compile_cxx_probe
compile_objc_probe
compile_build_probe

for role in CC CXX OBJC CC_FOR_BUILD; do
    command_var="$role"
    command_string="${!command_var}"
    set_identity_command "$command_string"
    source="$MACOS_COMPILER_PROBE_DIR/${role}.identity.c"
    printf 'int whp_compiler_identity(void) { return 0; }\n' > "$source"
    "${QUERY_CMD[@]}" -### -x c -c "$source" \
        2> "$MACOS_COMPILER_PROBE_DIR/${role}.pipeline" || true
done

mv -f "$manifest_candidate" "$MACOS_COMPILER_MANIFEST"
mv -f "$inputs_candidate" "$MACOS_COMPILER_INPUTS"
trap - EXIT
printf 'Verified macOS compiler toolchain: %s\n' "$MACOS_COMPILER_MANIFEST"
