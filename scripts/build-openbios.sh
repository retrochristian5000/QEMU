#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OPENBIOS_DIR="${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}"
OPENBIOS_OUTPUT="${OPENBIOS_OUTPUT:-$SOURCE_DIR/pc-bios/openbios-ppc}"
OPENBIOS_TOOLS_DIR="${OPENBIOS_TOOLS_DIR:-$SOURCE_DIR/build/firmware-tools}"
OPENBIOS_CROSS_COMPILE="${OPENBIOS_CROSS_COMPILE:-}"
OPENBIOS_HOSTCC="${OPENBIOS_HOSTCC:-${CC:-cc}}"
OPENBIOS_HOSTSTRIP="${OPENBIOS_HOSTSTRIP:-strip}"
OPENBIOS_TOKE="${OPENBIOS_TOKE:-}"
OPENBIOS_FORCE_RECONFIGURE="${OPENBIOS_FORCE_RECONFIGURE:-0}"
FCODE_UTILS_REPOSITORY="${FCODE_UTILS_REPOSITORY:-https://github.com/openbios/fcode-utils.git}"
FCODE_UTILS_REV="${FCODE_UTILS_REV:-6e563ee54aa9f60e538d90eedaa012ae77610344}"
FCODE_UTILS_DIR="${FCODE_UTILS_DIR:-$OPENBIOS_TOOLS_DIR/fcode-utils}"
MAKE_CMD="${MAKE_CMD:-${MAKE:-make}}"
config_candidate=""
temporary_output=""

cleanup()
{
    [[ -z "$config_candidate" ]] || rm -f "$config_candidate"
    [[ -z "$temporary_output" ]] || rm -f "$temporary_output"
}
trap cleanup EXIT

case "$OPENBIOS_FORCE_RECONFIGURE" in
    0|1) ;;
    *)
        printf 'error: OPENBIOS_FORCE_RECONFIGURE must be 0 or 1\n' >&2
        exit 1
        ;;
esac

for required in git xsltproc "$MAKE_CMD"; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: OpenBIOS build dependency not found: %s\n' "$required" >&2
        exit 1
    fi
done

if [[ ! -f "$OPENBIOS_DIR/config/scripts/switch-arch" ]]; then
    printf 'error: OpenBIOS source is missing at %s\n' "$OPENBIOS_DIR" >&2
    printf 'run: git submodule update --init roms/openbios\n' >&2
    exit 1
fi

if [[ -z "$OPENBIOS_TOKE" ]]; then
    OPENBIOS_TOKE="$(command -v toke || true)"
fi

if [[ -z "$OPENBIOS_TOKE" ]]; then
    cached_toke="$FCODE_UTILS_DIR/toke/toke"
    cached_revision=""
    if [[ -d "$FCODE_UTILS_DIR/.git" ]]; then
        cached_revision="$(git -C "$FCODE_UTILS_DIR" rev-parse HEAD 2>/dev/null || true)"
    fi

    if [[ -x "$cached_toke" && "$cached_revision" == "$FCODE_UTILS_REV" ]]; then
        OPENBIOS_TOKE="$cached_toke"
    else
        mkdir -p "$OPENBIOS_TOOLS_DIR"
        if [[ ! -d "$FCODE_UTILS_DIR/.git" ]]; then
            rm -rf "$FCODE_UTILS_DIR"
            git clone --filter=blob:none --no-checkout \
                "$FCODE_UTILS_REPOSITORY" "$FCODE_UTILS_DIR"
        fi

        git -C "$FCODE_UTILS_DIR" fetch --depth=1 origin "$FCODE_UTILS_REV"
        git -C "$FCODE_UTILS_DIR" checkout --detach --force FETCH_HEAD
        git -C "$FCODE_UTILS_DIR" clean -fdx

        "$MAKE_CMD" -C "$FCODE_UTILS_DIR/toke" \
            CC="$OPENBIOS_HOSTCC" STRIP="$OPENBIOS_HOSTSTRIP"
        OPENBIOS_TOKE="$cached_toke"
    fi
fi

if [[ ! -x "$OPENBIOS_TOKE" ]]; then
    printf 'error: toke was not built or is not executable: %s\n' \
        "$OPENBIOS_TOKE" >&2
    exit 1
fi

powerpc_tools=(gcc as ar ld nm strip ranlib)

prefix_is_usable()
{
    local prefix="$1"
    local tool

    [[ -n "$prefix" ]] || return 1
    for tool in "${powerpc_tools[@]}"; do
        command -v "${prefix}${tool}" >/dev/null 2>&1 || return 1
    done
}

if [[ -n "$OPENBIOS_CROSS_COMPILE" ]]; then
    if ! prefix_is_usable "$OPENBIOS_CROSS_COMPILE"; then
        printf 'error: incomplete PowerPC toolchain prefix: %s\n' \
            "$OPENBIOS_CROSS_COMPILE" >&2
        printf 'required tools: %s\n' "${powerpc_tools[*]}" >&2
        exit 1
    fi
else
    for candidate in \
        powerpc-unknown-linux-gnu- \
        powerpc-linux-gnu- \
        powerpc64-unknown-linux-gnu- \
        powerpc64-linux-gnu- \
        powerpc-none-elf- \
        powerpc64-none-elf- \
        powerpc-elf- \
        ppc-elf-; do
        if prefix_is_usable "$candidate"; then
            OPENBIOS_CROSS_COMPILE="$candidate"
            break
        fi
    done
fi

if [[ -z "$OPENBIOS_CROSS_COMPILE" ]]; then
    printf '%s\n' \
        'error: no complete GNU PowerPC cross-toolchain was found.' \
        'set OPENBIOS_CROSS_COMPILE to its executable prefix, for example:' \
        '  OPENBIOS_CROSS_COMPILE=powerpc-unknown-linux-gnu- ./builder.sh' >&2
    exit 1
fi

openbios_revision="$(git -C "$OPENBIOS_DIR" rev-parse HEAD)"
toke_signature="$(cksum "$OPENBIOS_TOKE" | awk '{print $1 ":" $2}')"
config_stamp="$OPENBIOS_DIR/obj-ppc/.whp-openbios-config"
config_candidate="$OPENBIOS_DIR/.whp-openbios-config.new.$$"

mkdir -p "$(dirname "$config_stamp")"
{
    printf 'OPENBIOS_REVISION=%s\n' "$openbios_revision"
    printf 'OPENBIOS_CROSS_COMPILE=%s\n' "$OPENBIOS_CROSS_COMPILE"
    printf 'OPENBIOS_HOSTCC=%s\n' "$OPENBIOS_HOSTCC"
    printf 'OPENBIOS_TOKE=%s\n' "$OPENBIOS_TOKE"
    printf 'OPENBIOS_TOKE_SIGNATURE=%s\n' "$toke_signature"
} > "$config_candidate"

if [[ "$OPENBIOS_FORCE_RECONFIGURE" == "1" ]] ||
   [[ ! -f "$OPENBIOS_DIR/config-host.mak" ]] ||
   [[ ! -f "$config_stamp" ]] ||
   ! cmp -s "$config_candidate" "$config_stamp"; then
    rm -rf "$OPENBIOS_DIR/obj-ppc" "$OPENBIOS_DIR/config-host.mak"
    (
        cd "$OPENBIOS_DIR"
        PATH="$(dirname "$OPENBIOS_TOKE"):$PATH" \
        CROSS_COMPILE="$OPENBIOS_CROSS_COMPILE" \
            ./config/scripts/switch-arch qemu-ppc
    )
    mkdir -p "$(dirname "$config_stamp")"
    mv "$config_candidate" "$config_stamp"
    config_candidate=""
else
    rm -f "$config_candidate"
    config_candidate=""
fi

PATH="$(dirname "$OPENBIOS_TOKE"):$PATH" \
    "$MAKE_CMD" -C "$OPENBIOS_DIR" -j"${JOBS:-1}" \
    build-verbose HOSTCC="$OPENBIOS_HOSTCC"

firmware="$OPENBIOS_DIR/obj-ppc/openbios-qemu.elf"
if [[ ! -s "$firmware" ]]; then
    printf 'error: OpenBIOS build did not produce %s\n' "$firmware" >&2
    exit 1
fi

if command -v "${OPENBIOS_CROSS_COMPILE}readelf" >/dev/null 2>&1; then
    if ! "${OPENBIOS_CROSS_COMPILE}readelf" -h "$firmware" |
         grep -q 'Machine:.*PowerPC'; then
        printf 'error: built OpenBIOS image is not a PowerPC ELF file\n' >&2
        exit 1
    fi
fi

mkdir -p "$(dirname "$OPENBIOS_OUTPUT")"
temporary_output="${OPENBIOS_OUTPUT}.tmp.$$"
install -m 0644 "$firmware" "$temporary_output"

if [[ -f "$OPENBIOS_OUTPUT" ]] && cmp -s "$temporary_output" "$OPENBIOS_OUTPUT"; then
    rm -f "$temporary_output"
else
    mv -f "$temporary_output" "$OPENBIOS_OUTPUT"
fi
temporary_output=""

if command -v shasum >/dev/null 2>&1; then
    firmware_digest="$(shasum -a 256 "$OPENBIOS_OUTPUT" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
    firmware_digest="$(sha256sum "$OPENBIOS_OUTPUT" | awk '{print $1}')"
else
    firmware_digest="unavailable"
fi

printf 'OpenBIOS %s -> %s (sha256 %s)\n' \
    "$openbios_revision" "$OPENBIOS_OUTPUT" "$firmware_digest"
