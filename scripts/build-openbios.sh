#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"
OPENBIOS_DIR="${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}"
OPENBIOS_BUILD_DIR="${OPENBIOS_BUILD_DIR:-$SOURCE_DIR/build/openbios}"
OPENBIOS_OUTPUT="${OPENBIOS_OUTPUT:-$SOURCE_DIR/pc-bios/openbios-ppc}"
OPENBIOS_TOOLS_DIR="${OPENBIOS_TOOLS_DIR:-$SOURCE_DIR/build/firmware-tools}"
OPENBIOS_CROSS_COMPILE="${OPENBIOS_CROSS_COMPILE:-}"
OPENBIOS_HOSTCC="${OPENBIOS_HOSTCC:-${CC_FOR_BUILD:-${CC:-cc}}}"
OPENBIOS_HOSTCXX="${OPENBIOS_HOSTCXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
OPENBIOS_HOSTSTRIP="${OPENBIOS_HOSTSTRIP:-${STRIP_FOR_BUILD:-strip}}"
OPENBIOS_READELF="${OPENBIOS_READELF:-}"
OPENBIOS_TOKE="${OPENBIOS_TOKE:-}"
OPENBIOS_FORCE_RECONFIGURE="${OPENBIOS_FORCE_RECONFIGURE:-0}"
BOOTSTRAP_POWERPC_TOOLCHAIN="${BOOTSTRAP_POWERPC_TOOLCHAIN:-1}"
POWERPC_TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$OPENBIOS_TOOLS_DIR/powerpc-elf}"
POWERPC_TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$OPENBIOS_TOOLS_DIR/toolchain-work/powerpc-elf}"
POWERPC_TOOLCHAIN_DOWNLOAD_DIR="${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$OPENBIOS_TOOLS_DIR/toolchain-downloads}"
POWERPC_TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
POWERPC_TOOLCHAIN_COMPILER="${POWERPC_TOOLCHAIN_COMPILER:-clang}"
POWERPC_TOOLCHAIN_SOURCE_MODE="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
POWERPC_LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-}"
if [[ -z "$POWERPC_LLVM_SUBMODULE_PATH" ]]; then
    POWERPC_LLVM_SUBMODULE_PATH=toolchains/llvm-project
fi
OPENBIOS_FIRMWARE_VALIDATION="${OPENBIOS_FIRMWARE_VALIDATION:-compatible}"
FCODE_UTILS_REPOSITORY="${FCODE_UTILS_REPOSITORY:-https://github.com/retrochristian5000/fcode-utils.git}"
FCODE_UTILS_REV="${FCODE_UTILS_REV:-e506db25b0aff34b98accc18b9b81f5673351cbf}"
FCODE_UTILS_DIR="${FCODE_UTILS_DIR:-$OPENBIOS_TOOLS_DIR/fcode-utils-retrochristian5000}"
MAKE_CMD_REQUESTED="${MAKE_CMD:-${MAKE:-}}"
if [[ -n "$MAKE_CMD_REQUESTED" ]]; then
    MAKE_CMD="$(whp_resolve_gnu_make "$MAKE_CMD_REQUESTED" || true)"
else
    MAKE_CMD="$(whp_find_gnu_make || true)"
fi
if [[ -z "$MAKE_CMD" ]]; then
    printf '%s\n' \
        'error: OpenBIOS requires GNU Make.' \
        'Install GNU Make (often gmake on BSD hosts) or set MAKE_CMD explicitly.' >&2
    exit 1
fi
config_candidate=""
temporary_output=""
probe_object=""

cleanup()
{
    [[ -z "$config_candidate" ]] || rm -f "$config_candidate"
    [[ -z "$temporary_output" ]] || rm -f "$temporary_output"
    [[ -z "$probe_object" ]] || rm -f "$probe_object"
}
trap cleanup EXIT

case "$OPENBIOS_FORCE_RECONFIGURE" in
    0|1) ;;
    *)
        printf 'error: OPENBIOS_FORCE_RECONFIGURE must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$BOOTSTRAP_POWERPC_TOOLCHAIN" in
    0|1) ;;
    *)
        printf 'error: BOOTSTRAP_POWERPC_TOOLCHAIN must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$POWERPC_TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$POWERPC_TOOLCHAIN_COMPILER" in
    clang|gcc) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_COMPILER must be clang or gcc\n' >&2
        exit 1
        ;;
esac
case "$POWERPC_TOOLCHAIN_SOURCE_MODE" in
    release|git) ;;
    *)
        printf '%s\n' \
            'error: POWERPC_TOOLCHAIN_SOURCE_MODE must be release or git' >&2
        exit 1
        ;;
esac
case "$OPENBIOS_FIRMWARE_VALIDATION" in
    compatible|strict) ;;
    *)
        printf '%s\n' \
            'error: OPENBIOS_FIRMWARE_VALIDATION must be compatible or strict' >&2
        exit 1
        ;;
esac

for required in git xsltproc install cksum awk grep; do
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

mkdir -p "$OPENBIOS_BUILD_DIR"
OPENBIOS_BUILD_DIR="$(cd -- "$OPENBIOS_BUILD_DIR" && pwd)"
OPENBIOS_DIR="$(cd -- "$OPENBIOS_DIR" && pwd)"
case "$OPENBIOS_BUILD_DIR" in
    /|'')
        printf 'error: unsafe OpenBIOS build directory: %s\n' \
            "$OPENBIOS_BUILD_DIR" >&2
        exit 1
        ;;
esac
if [[ "$OPENBIOS_BUILD_DIR" == "$OPENBIOS_DIR" ]]; then
    printf '%s\n' \
        'error: OpenBIOS must use an out-of-tree build directory.' \
        "source: $OPENBIOS_DIR" \
        "build:  $OPENBIOS_BUILD_DIR" >&2
    exit 1
fi

# Firmware tokenisation is part of the produced ROM, so never select an
# ambient PATH copy implicitly.  An explicit OPENBIOS_TOKE remains an
# intentional escape hatch; otherwise build/use the pinned WHP fcode-utils.
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
elif [[ "$OPENBIOS_TOKE" != */* ]]; then
    OPENBIOS_TOKE="$(command -v "$OPENBIOS_TOKE" 2>/dev/null || true)"
fi

if [[ ! -x "$OPENBIOS_TOKE" ]]; then
    printf 'error: toke was not built or is not executable: %s\n' \
        "${OPENBIOS_TOKE:-missing}" >&2
    exit 1
fi
printf 'OpenBIOS toke: %s\n' "$OPENBIOS_TOKE"

# readelf is intentionally separate from the cross-prefix requirement. The
# default Clang lane uses LLVM's ELF reader; an explicitly selected GCC
# toolchain may provide a prefixed reader instead.
powerpc_tools=(gcc ar ld nm strip ranlib)

prefix_is_usable()
{
    local prefix="$1"
    local tool
    local executable

    [[ -n "$prefix" ]] || return 1
    for tool in "${powerpc_tools[@]}"; do
        executable="${prefix}${tool}"
        if [[ "$executable" == */* ]]; then
            [[ -x "$executable" ]] || return 1
        else
            command -v "$executable" >/dev/null 2>&1 || return 1
        fi
    done
}

if [[ -n "$OPENBIOS_CROSS_COMPILE" ]]; then
    if ! prefix_is_usable "$OPENBIOS_CROSS_COMPILE"; then
        printf 'error: incomplete PowerPC toolchain prefix: %s\n' \
            "$OPENBIOS_CROSS_COMPILE" >&2
        printf 'required tools: %s\n' "${powerpc_tools[*]}" >&2
        exit 1
    fi
elif [[ "$BOOTSTRAP_POWERPC_TOOLCHAIN" == "1" ]]; then
    case "$POWERPC_TOOLCHAIN_COMPILER" in
        clang)
            llvm_submodule_dir="$SOURCE_DIR/$POWERPC_LLVM_SUBMODULE_PATH"
            if [[ ! -f "$llvm_submodule_dir/llvm/CMakeLists.txt" &&
                  -e "$SOURCE_DIR/.git" ]]; then
                git -C "$SOURCE_DIR" submodule update --init \
                    "$POWERPC_LLVM_SUBMODULE_PATH"
            fi
            bootstrap_name=bootstrap-powerpc-clang.sh
            bootstrap_script="$SCRIPT_DIR/$bootstrap_name"
            ;;
        gcc)
            case "$POWERPC_TOOLCHAIN_SOURCE_MODE" in
                release)
                    bootstrap_name=bootstrap-powerpc-toolchain-host.sh
                    ;;
                git)
                    bootstrap_name=bootstrap-powerpc-toolchain-git.sh
                    ;;
            esac
            bootstrap_script="$SCRIPT_DIR/$bootstrap_name"
            ;;
    esac
    POWERPC_TOOLCHAIN_DIR="$POWERPC_TOOLCHAIN_DIR" \
    POWERPC_TOOLCHAIN_WORK_DIR="$POWERPC_TOOLCHAIN_WORK_DIR" \
    POWERPC_TOOLCHAIN_DOWNLOAD_DIR="$POWERPC_TOOLCHAIN_DOWNLOAD_DIR" \
    POWERPC_TOOLCHAIN_FORCE_REBUILD="$POWERPC_TOOLCHAIN_FORCE_REBUILD" \
    CC_FOR_BUILD="$OPENBIOS_HOSTCC" \
    CXX_FOR_BUILD="$OPENBIOS_HOSTCXX" \
    TOOLCHAIN_HOST_CC="$OPENBIOS_HOSTCC" \
    TOOLCHAIN_HOST_CXX="$OPENBIOS_HOSTCXX" \
    POWERPC_LLVM_SUBMODULE_PATH="$POWERPC_LLVM_SUBMODULE_PATH" \
    MAKE_CMD="$MAKE_CMD" \
    JOBS="${JOBS:-1}" \
        bash "$bootstrap_script"
    bootstrapped_prefix="$POWERPC_TOOLCHAIN_DIR/bin/powerpc-elf-"
    if ! prefix_is_usable "$bootstrapped_prefix"; then
        printf 'error: bootstrapped PowerPC toolchain is incomplete: %s\n' \
            "$bootstrapped_prefix" >&2
        exit 1
    fi
    OPENBIOS_CROSS_COMPILE="$bootstrapped_prefix"
else
    printf '%s\n' \
        'error: no PowerPC cross-toolchain was explicitly selected.' \
        'Enable WHP bootstrapping with BOOTSTRAP_POWERPC_TOOLCHAIN=1 or set:' \
        '  OPENBIOS_CROSS_COMPILE=/absolute/path/to/powerpc-elf-' >&2
    exit 1
fi
printf 'OpenBIOS PowerPC toolchain: %s\n' "$OPENBIOS_CROSS_COMPILE"

if [[ -z "$OPENBIOS_READELF" ]]; then
    llvm_readelf="$POWERPC_TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
    if [[ -x "$llvm_readelf" ]]; then
        OPENBIOS_READELF="$llvm_readelf"
    else
        OPENBIOS_READELF="${OPENBIOS_CROSS_COMPILE}readelf"
    fi
fi
if [[ "$OPENBIOS_READELF" == */* ]]; then
    if [[ -x "$OPENBIOS_READELF" ]]; then
        readelf_cmd="$OPENBIOS_READELF"
    else
        readelf_cmd=""
    fi
else
    readelf_cmd="$(command -v "$OPENBIOS_READELF" 2>/dev/null || true)"
fi
if [[ -z "$readelf_cmd" ]]; then
    printf 'error: OpenBIOS ELF reader is not executable: %s\n' \
        "$OPENBIOS_READELF" >&2
    exit 1
fi
printf 'OpenBIOS ELF reader: %s\n' "$readelf_cmd"

# Prove that the explicitly supplied or project-controlled compiler actually
# emits the format consumed by qemu-system-ppc before spending time on firmware.
probe_object="${OPENBIOS_BUILD_DIR}.toolchain-probe.$$"
printf 'int openbios_toolchain_probe;\n' |
    "${OPENBIOS_CROSS_COMPILE}gcc" -m32 -ffreestanding -fno-pic -fno-pie \
        -x c -c -o "$probe_object" -
probe_header="$(LC_ALL=C "$readelf_cmd" -hW "$probe_object")"
if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$probe_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$probe_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$probe_header"; then
    printf '%s\n' \
        "error: $OPENBIOS_CROSS_COMPILE does not emit 32-bit big-endian PowerPC objects." >&2
    exit 1
fi
rm -f "$probe_object"
probe_object=""

openbios_revision="$(git -C "$OPENBIOS_DIR" rev-parse HEAD)"
toke_signature="$(cksum "$OPENBIOS_TOKE" | awk '{print $1 ":" $2}')"
config_stamp="$OPENBIOS_BUILD_DIR/obj-ppc/.whp-openbios-config"
config_candidate="${OPENBIOS_BUILD_DIR}.config.new.$$"

{
    printf 'OPENBIOS_REVISION=%s\n' "$openbios_revision"
    printf 'OPENBIOS_SOURCE_DIR=%s\n' "$OPENBIOS_DIR"
    printf 'OPENBIOS_BUILD_DIR=%s\n' "$OPENBIOS_BUILD_DIR"
    printf 'OPENBIOS_CROSS_COMPILE=%s\n' "$OPENBIOS_CROSS_COMPILE"
    printf 'OPENBIOS_READELF=%s\n' "$readelf_cmd"
    printf 'OPENBIOS_HOSTCC=%s\n' "$OPENBIOS_HOSTCC"
    printf 'OPENBIOS_HOSTCXX=%s\n' "$OPENBIOS_HOSTCXX"
    printf 'OPENBIOS_HOSTSTRIP=%s\n' "$OPENBIOS_HOSTSTRIP"
    printf 'OPENBIOS_TOKE=%s\n' "$OPENBIOS_TOKE"
    printf 'OPENBIOS_TOKE_SIGNATURE=%s\n' "$toke_signature"
    printf 'OPENBIOS_FIRMWARE_VALIDATION=%s\n' "$OPENBIOS_FIRMWARE_VALIDATION"
} > "$config_candidate"

if [[ "$OPENBIOS_FORCE_RECONFIGURE" == "1" ]] ||
   [[ ! -f "$OPENBIOS_BUILD_DIR/config-host.mak" ]] ||
   [[ ! -f "$config_stamp" ]] ||
   ! cmp -s "$config_candidate" "$config_stamp"; then
    rm -rf "$OPENBIOS_BUILD_DIR"
    mkdir -p "$OPENBIOS_BUILD_DIR"
    (
        cd "$OPENBIOS_BUILD_DIR"
        HOSTARCH= \
        TOKE="$OPENBIOS_TOKE" \
        PATH="$(dirname "$OPENBIOS_TOKE"):$PATH" \
        CROSS_COMPILE="$OPENBIOS_CROSS_COMPILE" \
            "$OPENBIOS_DIR/config/scripts/switch-arch" qemu-ppc
    )
    if [[ ! -f "$OPENBIOS_BUILD_DIR/config-host.mak" ||
          ! -f "$OPENBIOS_BUILD_DIR/obj-ppc/rules.mak" ||
          ! -f "$OPENBIOS_BUILD_DIR/obj-ppc/target/include/autoconf.h" ]]; then
        printf '%s\n' \
            'error: OpenBIOS configuration did not generate a complete obj-ppc build tree.' >&2
        exit 1
    fi
    mkdir -p "$(dirname "$config_stamp")"
    mv "$config_candidate" "$config_stamp"
    config_candidate=""
else
    rm -f "$config_candidate"
    config_candidate=""
fi

PATH="$(dirname "$OPENBIOS_TOKE"):$PATH" \
    "$MAKE_CMD" -C "$OPENBIOS_BUILD_DIR" -j"${JOBS:-1}" \
    build-verbose HOSTCC="$OPENBIOS_HOSTCC"

firmware="$OPENBIOS_BUILD_DIR/obj-ppc/openbios-qemu.elf"
symbols="$OPENBIOS_BUILD_DIR/obj-ppc/openbios-qemu.syms"
if [[ ! -s "$firmware" ]]; then
    printf 'error: OpenBIOS build did not produce %s\n' "$firmware" >&2
    exit 1
fi
if [[ ! -s "$symbols" ]]; then
    printf 'error: OpenBIOS build did not produce %s\n' "$symbols" >&2
    exit 1
fi

elf_header="$(LC_ALL=C "$readelf_cmd" -hW "$firmware")"
program_headers="$(LC_ALL=C "$readelf_cmd" -lW "$firmware")"

if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$elf_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$elf_header" ||
   ! grep -Eq 'Type:[[:space:]]+EXEC' <<< "$elf_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$elf_header"; then
    printf '%s\n' \
        'error: OpenBIOS output is not a 32-bit big-endian PowerPC executable.' >&2
    printf '%s\n' "$elf_header" >&2
    exit 1
fi

if grep -Eq '^[[:space:]]*(INTERP|DYNAMIC)[[:space:]]' <<< "$program_headers"; then
    printf '%s\n' \
        'error: OpenBIOS contains a dynamic-loader program header.' >&2
    exit 1
fi

start_address="$(awk '$3 == "_start" {print tolower($1); exit}' "$symbols")"
if [[ -n "$start_address" && "$start_address" != 0x* ]]; then
    start_address="0x$start_address"
fi
if [[ ! "$start_address" =~ ^0x[0-9a-f]+$ ]]; then
    printf 'error: OpenBIOS _start symbol is missing or malformed: %s\n' \
        "${start_address:-missing}" >&2
    exit 1
fi
start_value=$((start_address))
if ((start_value < 0xfff00000 || start_value >= 0x100000000)); then
    printf 'error: OpenBIOS _start is outside the Mac99 PROM: %s\n' \
        "$start_address" >&2
    exit 1
fi

elf_entry_address="$(awk -F: '/Entry point address:/ {
    gsub(/[[:space:]]/, "", $2); print tolower($2); exit
}' <<< "$elf_header")"
if [[ "$elf_entry_address" =~ ^0x[0-9a-f]+$ ]]; then
    elf_entry_value=$((elf_entry_address))
else
    elf_entry_value=0
fi

load_count=0
start_loaded=0
elf_entry_loaded=0
legacy_entry_loaded=0
hard_reset_loaded=0
while IFS='|' read -r vaddr memsz segment_flags; do
    [[ -n "$vaddr" && -n "$memsz" ]] || continue
    ((load_count += 1))
    vaddr_value=$((vaddr))
    memsz_value=$((memsz))
    end_value=$((vaddr_value + memsz_value))
    if [[ "$segment_flags" == *W* && "$segment_flags" == *E* ]]; then
        printf 'error: OpenBIOS LOAD segment is both writable and executable: %s\n' \
            "$segment_flags" >&2
        exit 1
    fi
    if ((vaddr_value < 0xfff00000 || end_value > 0x100000000)); then
        printf 'error: OpenBIOS LOAD segment escapes the 1 MiB PROM window: %s + %s\n' \
            "$vaddr" "$memsz" >&2
        exit 1
    fi
    if ((vaddr_value <= start_value && end_value > start_value)); then
        start_loaded=1
    fi
    if ((elf_entry_value >= 0xfff00000 && elf_entry_value < 0x100000000 &&
         vaddr_value <= elf_entry_value && end_value > elf_entry_value)); then
        elf_entry_loaded=1
    fi
    if ((vaddr_value <= 0xfff00100 && end_value > 0xfff00100)); then
        legacy_entry_loaded=1
    fi
    if ((vaddr_value <= 0xfffffffc && end_value > 0xfffffffc)); then
        hard_reset_loaded=1
    fi
done < <(awk '$1 == "LOAD" { flags=""; for (i=7; i<NF; i++) flags=flags $i; print $3 "|" $6 "|" flags }' <<< "$program_headers")

if ((load_count == 0)); then
    printf 'error: OpenBIOS ELF has no loadable segments\n' >&2
    exit 1
fi
if ((start_loaded == 0)); then
    printf 'error: OpenBIOS _start %s is not covered by a LOAD segment\n' \
        "$start_address" >&2
    exit 1
fi

if [[ "$OPENBIOS_FIRMWARE_VALIDATION" == strict ]]; then
    if [[ "$start_address" != "0xfff00100" ]]; then
        printf 'error: OpenBIOS _start is %s, expected 0xfff00100\n' \
            "$start_address" >&2
        exit 1
    fi
    if ((legacy_entry_loaded == 0 || hard_reset_loaded == 0)); then
        printf '%s\n' \
            'error: strict validation requires both the 0xfff00100 entry vector' \
            'and the 0xfffffffc hard-reset vector in the Power Mac PROM.' >&2
        exit 1
    fi
else
    if ((elf_entry_loaded == 1)); then
        selected_entry="$elf_entry_address"
        selected_entry_source="ELF header"
    else
        selected_entry="$start_address"
        selected_entry_source="_start symbol"
    fi

    if ((elf_entry_loaded == 0)) && [[ "$start_address" != "0xfff00100" ]]; then
        printf '%s\n' \
            "warning: ELF entry $elf_entry_address is unusable; _start is $start_address." \
            'Use the QEMU compatibility override:' \
            "  -machine mac99,firmware-entry=$start_address" >&2
    fi
    if ((legacy_entry_loaded == 0)); then
        printf '%s\n' \
            'warning: firmware does not map QEMU legacy entry 0xfff00100;' \
            "         selected $selected_entry_source entry $selected_entry instead." >&2
    fi
    if ((hard_reset_loaded == 0)); then
        printf '%s\n' \
            'warning: firmware does not map the architectural hard-reset vector' \
            '         at 0xfffffffc; QEMU will use the selected firmware entry.' >&2
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

printf 'OpenBIOS %s -> %s (sha256 %s, validation %s)\n' \
    "$openbios_revision" "$OPENBIOS_OUTPUT" "$firmware_digest" \
    "$OPENBIOS_FIRMWARE_VALIDATION"
