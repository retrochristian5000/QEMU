#!/usr/bin/env bash

set -euo pipefail

: "${MACOS_HOST_ARCH:?MACOS_HOST_ARCH is required}"
: "${CC:?CC is required}"
: "${SDKROOT:?SDKROOT is required}"

MACOS_LTO_MANIFEST="${MACOS_LTO_MANIFEST:-.whp-macos-lto}"
MACOS_LTO_PROBE_DIR="${MACOS_LTO_PROBE_DIR:-${MACOS_LTO_MANIFEST}.d}"

case "$MACOS_HOST_ARCH" in
    arm64|x86_64) ;;
    *)
        printf 'error: unsupported macOS LTO architecture: %s\n' \
            "$MACOS_HOST_ARCH" >&2
        exit 1
        ;;
esac

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
        for token in "${tokens[@]}"; do
            case "$token" in
                -flto|-flto=*|-fno-lto|-Wl,*lto*|-Wl,*LTO*|\
                -object_path_lto*|-lto_library*|-cache_path_lto*|\
                -Xlinker=*lto*|-Xlinker=*LTO*)
                    printf '%s\n' \
                        "error: $variable contains an LTO option: $value" \
                        'The macOS LTO probe adds -flto itself so the option' \
                        'cannot arrive through a global flag channel.' >&2
                    exit 1
                    ;;
            esac
        done
    done
}

output_arches()
{
    xcrun lipo -archs "$1" 2>/dev/null || true
}

mkdir -p "$MACOS_LTO_PROBE_DIR" "$(dirname "$MACOS_LTO_MANIFEST")"
manifest_candidate="${MACOS_LTO_MANIFEST}.new.$$"
cleanup()
{
    rm -f "$manifest_candidate"
}
trap cleanup EXIT

reject_embedded_lto
set_command "$CC"
split_flags "${CPPFLAGS:-}"
CPP_FLAGS=("${FLAG_ARRAY[@]}")
split_flags "${CFLAGS:-}"
C_FLAGS=("${FLAG_ARRAY[@]}")
split_flags "${LDFLAGS:-}"
LD_FLAGS=("${FLAG_ARRAY[@]}")

source_a="$MACOS_LTO_PROBE_DIR/lto-a.c"
source_main="$MACOS_LTO_PROBE_DIR/lto-main.c"
object_a="$MACOS_LTO_PROBE_DIR/lto-a.o"
object_main="$MACOS_LTO_PROBE_DIR/lto-main.o"
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

"${CC_CMD[@]}" "${CPP_FLAGS[@]}" "${C_FLAGS[@]}" \
    -flto -c "$source_a" -o "$object_a"
"${CC_CMD[@]}" "${CPP_FLAGS[@]}" "${C_FLAGS[@]}" \
    -flto -c "$source_main" -o "$object_main"
"${CC_CMD[@]}" "${C_FLAGS[@]}" -flto \
    "$object_a" "$object_main" -o "$output" "${LD_FLAGS[@]}"

arches="$(output_arches "$output")"
case " $arches " in
    *" $MACOS_HOST_ARCH "*) ;;
    *)
        printf 'error: LTO produced Mach-O architecture %s, expected %s\n' \
            "${arches:-<unknown>}" "$MACOS_HOST_ARCH" >&2
        exit 1
        ;;
esac

if ! "$output"; then
    printf 'error: linked macOS LTO probe did not execute successfully\n' >&2
    exit 1
fi

CCACHE_DISABLE=1 "${CC_CMD[@]}" "${C_FLAGS[@]}" -flto \
    "$object_a" "$object_main" -o "$output.pipeline" "${LD_FLAGS[@]}" \
    -### 2> "$pipeline" || true

compiler_version="$("${CC_CMD[@]}" --version 2>&1 | sed -n '1p')"
output_signature="$(cksum "$output" | awk '{print $1 ":" $2}')"
{
    printf 'WHP_MACOS_LTO_SCHEMA=1\n'
    printf 'QEMU_HOST_LTO=1\n'
    printf 'MACOS_HOST_ARCH=%s\n' "$MACOS_HOST_ARCH"
    printf 'SDKROOT=%s\n' "$SDKROOT"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
    printf 'CC=%s\n' "$CC"
    printf 'CC_VERSION=%s\n' "$compiler_version"
    printf 'CFLAGS=%s\n' "${CFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
    printf 'LTO_MODE=full\n'
    printf 'OUTPUT_ARCHES=%s\n' "$arches"
    printf 'OUTPUT_SIGNATURE=%s\n' "$output_signature"
    printf 'LINK_PIPELINE=%s\n' "$pipeline"
} > "$manifest_candidate"

mv -f "$manifest_candidate" "$MACOS_LTO_MANIFEST"
trap - EXIT
printf 'Verified macOS QEMU host LTO: %s\n' "$MACOS_LTO_MANIFEST"
