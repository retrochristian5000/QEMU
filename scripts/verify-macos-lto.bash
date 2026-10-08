#!/usr/bin/env bash

set -euo pipefail

: "${CC:?CC is required}"
: "${SDKROOT:?SDKROOT is required}"

case "$(uname -m)" in
    arm64|aarch64) host_arch=arm64 ;;
    x86_64|amd64) host_arch=x86_64 ;;
    *)
        printf 'error: unsupported macOS LTO architecture: %s\n' "$(uname -m)" >&2
        exit 1
        ;;
esac

MACOS_LTO_MANIFEST="${MACOS_LTO_MANIFEST:-.whp-macos-lto}"
MACOS_LTO_PROBE_DIR="${MACOS_LTO_PROBE_DIR:-${MACOS_LTO_MANIFEST}.d}"

if [[ ! -d "$SDKROOT" ]]; then
    printf 'error: macOS SDK does not exist: %s\n' "$SDKROOT" >&2
    exit 1
fi
for required in xcrun awk sed; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: macOS LTO probe dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

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

    CC_CMD=()
    read -r -a CC_CMD <<< "$command_string"
    if [[ "${#CC_CMD[@]}" -eq 0 ]] ||
       ! command -v "${CC_CMD[0]}" >/dev/null 2>&1; then
        printf 'error: unusable compiler command: %s\n' "$command_string" >&2
        exit 1
    fi
}

split_flags()
{
    FLAG_ARRAY=()
    if [[ -n "$1" ]]; then
        read -r -a FLAG_ARRAY <<< "$1"
    fi
}

reject_embedded_lto()
{
    local variable value token
    local tokens=()

    for variable in CFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        tokens=()
        read -r -a tokens <<< "$value"
        for token in ${tokens[@]+"${tokens[@]}"}; do
            case "$token" in
                -flto|-flto=*|-fno-lto|-Wl,*lto*|-Wl,*LTO*|\
                -object_path_lto*|-lto_library*|-cache_path_lto*|\
                -Xlinker=*lto*|-Xlinker=*LTO*)
                    printf '%s\n' \
                        "error: $variable contains an LTO option: $value" \
                        'The macOS ThinLTO probe adds -flto=thin itself so the option' \
                        'cannot arrive through a global flag channel.' >&2
                    exit 1
                    ;;
            esac
        done
    done
}

output_arches()
{
    if [[ -n "${LIPO:-}" ]]; then
        "$LIPO" -archs "$1" 2>/dev/null || true
    else
        xcrun lipo -archs "$1" 2>/dev/null || true
    fi
}

mkdir -p "$MACOS_LTO_PROBE_DIR" "$(dirname "$MACOS_LTO_MANIFEST")"
manifest_candidate="${MACOS_LTO_MANIFEST}.new.$$"
cleanup()
{
    rm -f "$manifest_candidate"
}
trap cleanup EXIT

set_archive_command()
{
    local variable="$1"
    local fallback="$2"
    local name="${!variable:-$fallback}"
    local -a command=()

    case "$name" in
        *';'*|*'|'*|*'&'*|*'<'*|*'>'*)
            printf 'error: %s command contains shell operators: %s\n' \
                "$variable" "$name" >&2
            exit 1
            ;;
    esac
    read -r -a command <<< "$name"
    if [[ "${#command[@]}" -eq 0 ]] ||
       ! command -v "${command[0]}" >/dev/null 2>&1; then
        printf 'error: unusable %s command: %s\n' "$variable" "$name" >&2
        exit 1
    fi
    if [[ "$variable" == AR ]]; then
        AR_CMD=("${command[@]}")
    else
        RANLIB_CMD=("${command[@]}")
    fi
}
reject_embedded_lto
set_command "$CC"
# Match QEMU's archive-tool family as well as its compiler/linker.
set_archive_command AR /usr/bin/ar
set_archive_command RANLIB /usr/bin/ranlib
split_flags "${CPPFLAGS:-}"
CPP_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
split_flags "${CFLAGS:-}"
C_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
split_flags "${LDFLAGS:-}"
LD_FLAGS=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})

# Match Meson b_lto_threads for the actual link where a power budget exists.
# Standalone probes without JOBS retain the linker default.
THINLTO_JOBS_ARG=()
if [[ -n "${JOBS:-}" ]]; then
    case "$JOBS" in
        *[!0-9]*|""|0)
            printf 'error: ThinLTO JOBS must be a positive integer: %s\n' \
                "$JOBS" >&2
            exit 1
            ;;
    esac
    THINLTO_JOBS_ARG=("-flto-jobs=$JOBS")
fi

source_a="$MACOS_LTO_PROBE_DIR/lto-a.c"
source_main="$MACOS_LTO_PROBE_DIR/lto-main.c"
object_a="$MACOS_LTO_PROBE_DIR/lto-a.o"
object_main="$MACOS_LTO_PROBE_DIR/lto-main.o"
archive="$MACOS_LTO_PROBE_DIR/liblto-probe.a"
output="$MACOS_LTO_PROBE_DIR/lto-probe"
pipeline="$MACOS_LTO_PROBE_DIR/LTO.link.pipeline"

cat > "$source_a" <<'SOURCE'
int whp_lto_increment(int value)
{
    return value + 1;
}
SOURCE
cat > "$source_main" <<'SOURCE'
int whp_lto_increment(int value);
int main(void)
{
    return whp_lto_increment(0) == 1 ? 0 : 1;
}
SOURCE

"${CC_CMD[@]}" \
    ${CPP_FLAGS[@]+"${CPP_FLAGS[@]}"} \
    ${C_FLAGS[@]+"${C_FLAGS[@]}"} \
    -flto=thin -c "$source_a" -o "$object_a"
"${CC_CMD[@]}" \
    ${CPP_FLAGS[@]+"${CPP_FLAGS[@]}"} \
    ${C_FLAGS[@]+"${C_FLAGS[@]}"} \
    -flto=thin -c "$source_main" -o "$object_main"
# ThinLTO must survive the archive indexing and extraction used by QEMU.
"${AR_CMD[@]}" rcs "$archive" "$object_a"
"${RANLIB_CMD[@]}" "$archive"
"${CC_CMD[@]}" ${C_FLAGS[@]+"${C_FLAGS[@]}"} -flto=thin \
    "${THINLTO_JOBS_ARG[@]}" "$object_main" "$archive" -o "$output" \
    ${LD_FLAGS[@]+"${LD_FLAGS[@]}"}
arches="$(output_arches "$output")"
case " $arches " in
    *" $host_arch "*) ;;
    *)
        printf 'error: LTO produced Mach-O architecture %s, expected %s\n' \
            "${arches:-<unknown>}" "$host_arch" >&2
        exit 1
        ;;
esac

if ! "$output"; then
    printf 'error: linked macOS LTO probe did not execute successfully\n' >&2
    exit 1
fi

CCACHE_DISABLE=1 "${CC_CMD[@]}" \
    ${C_FLAGS[@]+"${C_FLAGS[@]}"} -flto=thin \
    "${THINLTO_JOBS_ARG[@]}" "$object_main" "$archive" -o "$output.pipeline" \
    ${LD_FLAGS[@]+"${LD_FLAGS[@]}"} \
    -### 2> "$pipeline" || true

compiler_version="$("${CC_CMD[@]}" --version 2>&1 | sed -n '1p')"
output_signature="$(cksum "$output" | awk '{print $1 ":" $2}')"
{
    printf 'WHP_MACOS_LTO_SCHEMA=3\n'
    printf 'QEMU_HOST_LTO=1\n'
    printf 'HOST_ARCH=%s\n' "$host_arch"
    printf 'SDKROOT=%s\n' "$SDKROOT"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
    printf 'CC=%s\n' "$CC"
    printf 'AR=%s\n' "${AR:-/usr/bin/ar}"
    printf 'RANLIB=%s\n' "${RANLIB:-/usr/bin/ranlib}"
    printf 'CC_VERSION=%s\n' "$compiler_version"
    printf 'LIPO=%s\n' "${LIPO:-xcrun lipo}"
    printf 'CFLAGS=%s\n' "${CFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
    printf 'LTO_MODE=thin\n'
    printf 'LTO_JOBS=%s\n' "${JOBS:-auto}"
    printf 'ARCHIVE=%s\n' "$archive"
    printf 'OUTPUT_ARCHES=%s\n' "$arches"
    printf 'OUTPUT_SIGNATURE=%s\n' "$output_signature"
    printf 'LINK_PIPELINE=%s\n' "$pipeline"
} > "$manifest_candidate"

mv -f "$manifest_candidate" "$MACOS_LTO_MANIFEST"
trap - EXIT
printf 'Verified macOS QEMU host LTO: %s\n' "$MACOS_LTO_MANIFEST"
