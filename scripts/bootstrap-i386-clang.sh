#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${I386_TOOLCHAIN_TARGET:-i386-none-elf}"
TOOLCHAIN_DIR="${I386_TOOLCHAIN_DIR:-$SOURCE_DIR/build/firmware-tools/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${I386_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
LLVM_SUBMODULE_PATH="${I386_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SOURCE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
LLVM_BUILD_DIR="${I386_LLVM_BUILD_DIR:-$TOOLCHAIN_WORK_DIR/llvm-build}"
TOOLCHAIN_FORCE_REBUILD="${I386_TOOLCHAIN_FORCE_REBUILD:-0}"
JOBS="${JOBS:-}"
stage_root=""

cleanup()
{
    local status=$?
    [[ -z "$stage_root" ]] || rm -rf "$stage_root"
    exit "$status"
}
trap cleanup EXIT

[[ "$TOOLCHAIN_TARGET" == i386-none-elf ]] || {
    printf 'error: i386 LLVM firmware lane requires i386-none-elf\n' >&2
    exit 1
}
case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: I386_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac

cmake_parallel_args=(--parallel)
if [[ -n "$JOBS" ]]; then
    case "$JOBS" in
        0|*[!0-9]*)
            printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2
            exit 1
            ;;
    esac
    cmake_parallel_args=(--parallel "$JOBS")
fi

for tool in git cmake ninja grep mkdir mv rm ln; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: i386 LLVM bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

if [[ ! -f "$LLVM_SOURCE_DIR/llvm/CMakeLists.txt" ]]; then
    git -C "$SOURCE_DIR" submodule update --init --depth 1 "$LLVM_SUBMODULE_PATH"
fi
[[ -f "$LLVM_SOURCE_DIR/clang/CMakeLists.txt" &&
   -f "$LLVM_SOURCE_DIR/lld/CMakeLists.txt" ]] || {
    printf 'error: LLVM submodule is missing clang/lld: %s\n' "$LLVM_SOURCE_DIR" >&2
    exit 1
}

llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse HEAD)"
marker="$TOOLCHAIN_DIR/.whp-i386-toolchain"
expected_marker="$(cat <<EOF
BOOTSTRAP_SCHEMA=8
TARGET=$TOOLCHAIN_TARGET
LLVM_GIT_COMMIT=$llvm_revision
LLVM_TARGETS_TO_BUILD=X86
LLVM_DISTRIBUTION=seabios-minimal
COMPILER=clang
ASSEMBLER=clang-integrated
LINKER=ld.lld
LINKER_DEFAULT_EMULATION=elf_i386
OBJECT_TOOLS=llvm-objcopy;llvm-objdump;llvm-strip
EOF
)"

usable()
{
    local prefix="$1"
    local tool

    for tool in gcc cpp as ld objcopy objdump strip; do
        [[ -x "$prefix/bin/$TOOLCHAIN_TARGET-$tool" ]] || return 1
    done
}

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 && -f "$marker" &&
      "$(cat "$marker")" == "$expected_marker" ]] && usable "$TOOLCHAIN_DIR"; then
    printf 'i386 LLVM toolchain is current: %s/bin/%s-\n' \
        "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    exit 0
fi

mkdir -p "$TOOLCHAIN_WORK_DIR"

# SeaBIOS needs a C compiler/preprocessor, an assembler interface, an ELF
# linker, and three object-image inspection/transformation tools. Build only
# the LLVM components that implement that command surface. Clang itself drives
# the integrated assembler, so a separate assembler binary is not part of this
# lane.
llvm_distribution_components='clang;clang-resource-headers;lld;llvm-objcopy;llvm-objdump;llvm-strip'

cmake_args=(
    -S "$LLVM_SOURCE_DIR/llvm"
    -B "$LLVM_BUILD_DIR"
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR/llvm"
    -DCMAKE_EXPORT_COMPILE_COMMANDS=OFF
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF
    -DCMAKE_SKIP_INSTALL_ALL_DEPENDENCY=ON
    -DCMAKE_INSTALL_MESSAGE=NEVER
    '-DLLVM_ENABLE_PROJECTS=clang;lld'
    -DLLVM_TARGETS_TO_BUILD=X86
    -DLLD_ENABLE_BACKENDS=ELF
    "-DLLVM_DISTRIBUTION_COMPONENTS=$llvm_distribution_components"
    -DLLVM_APPEND_VC_REV=OFF
    -DLLVM_ENABLE_LTO=OFF
    -DLLVM_ENABLE_FATLTO=OFF
    -DLLVM_BUILD_INSTRUMENTED=OFF
    -DLLVM_ENABLE_MODULES=OFF
    -DLLVM_ENABLE_PLUGINS=OFF
    -DLLVM_ENABLE_BACKTRACES=OFF
    -DLLVM_ENABLE_CRASH_OVERRIDES=OFF
    -DLLVM_ENABLE_UNWIND_TABLES=OFF
    -DLLVM_ENABLE_LIBEDIT=OFF
    -DLLVM_ENABLE_LIBPFM=OFF
    -DLLVM_ENABLE_Z3_SOLVER=OFF
    -DLLVM_ENABLE_WARNINGS=OFF
    -DLLVM_ENABLE_PEDANTIC=OFF
    -DLLVM_INCLUDE_TESTS=OFF
    -DLLVM_INCLUDE_EXAMPLES=OFF
    -DLLVM_INCLUDE_BENCHMARKS=OFF
    -DLLVM_INCLUDE_DOCS=OFF
    -DLLVM_INCLUDE_UTILS=OFF
    -DLLVM_INCLUDE_RUNTIMES=OFF
    -DLLVM_ENABLE_BINDINGS=OFF
    -DCLANG_INCLUDE_TESTS=OFF
    -DCLANG_ENABLE_STATIC_ANALYZER=OFF
    -DLLD_INCLUDE_TESTS=OFF
    -DLLVM_ENABLE_TERMINFO=OFF
    -DLLVM_ENABLE_ZLIB=OFF
    -DLLVM_ENABLE_ZSTD=OFF
    -DLLVM_ENABLE_LIBXML2=OFF
)
cmake "${cmake_args[@]}"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then
    cmake --build "$LLVM_BUILD_DIR" --target clean "${cmake_parallel_args[@]}"
fi

cmake --build "$LLVM_BUILD_DIR" --target distribution "${cmake_parallel_args[@]}"

# Install into a staging root first. Replacing the prefix after validation
# removes stale tools left by older, broader bootstrap schemas without deleting
# the persistent CMake/Ninja build graph.
stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
rm -rf "$stage_root"
mkdir -p "$stage_root"
DESTDIR="$stage_root" \
    cmake --build "$LLVM_BUILD_DIR" --target install-distribution \
        "${cmake_parallel_args[@]}"

llvm="$staged_toolchain/llvm/bin"
bin="$staged_toolchain/bin"
mkdir -p "$bin"
for required in clang ld.lld llvm-objcopy llvm-objdump llvm-strip; do
    [[ -x "$llvm/$required" ]] || {
        printf 'error: LLVM SeaBIOS distribution did not produce %s\n' "$required" >&2
        exit 1
    }
done

cat >"$bin/$TOOLCHAIN_TARGET-gcc" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
link_step=1
for arg in "$@"; do
    case "$arg" in
        -c|-S|-E) link_step=0 ;;
    esac
done

args=()
for arg in "$@"; do
    case "$arg" in
        -mpreferred-stack-boundary=2) args+=(-mstack-alignment=4) ;;
        -fno-defer-pop|-fno-stack-protector-all|-fstack-check=no) ;;
        -fwhole-program)
            printf 'error: SeaBIOS whole-program optimization is unsupported by Clang\n' >&2
            exit 1
            ;;
        *) args+=("$arg") ;;
    esac
done

driver_args=(--target=i386-none-elf)
if [[ "$link_step" == 1 ]]; then
    driver_args+=(-fuse-ld=lld)
fi
exec "$prefix/llvm/bin/clang" "${driver_args[@]}" "${args[@]}"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-gcc"

cat >"$bin/$TOOLCHAIN_TARGET-cpp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$prefix/llvm/bin/clang" --target=i386-none-elf -E "$@"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-cpp"

cat >"$bin/$TOOLCHAIN_TARGET-ld" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == --version ]]; then
    exec "$prefix/llvm/bin/ld.lld" --version
fi

# A GNU i386-none-elf cross linker defaults to elf_i386 even when callers do
# not pass -m. SeaBIOS relies on that ABI for its final linker-script links.
linker_args=(-m elf_i386)
while (($#)); do
    case "$1" in
        -melf_i386|-m=elf_i386)
            shift
            ;;
        -m)
            if (($# < 2)); then
                printf 'error: -m requires an i386 linker emulation\n' >&2
                exit 1
            fi
            if [[ "$2" != elf_i386 ]]; then
                printf 'error: unsupported i386 linker emulation: %s\n' "$2" >&2
                exit 1
            fi
            shift 2
            ;;
        -m*)
            emulation="${1#-m}"
            if [[ "$emulation" != elf_i386 ]]; then
                printf 'error: unsupported i386 linker emulation: %s\n' "$emulation" >&2
                exit 1
            fi
            shift
            ;;
        *)
            linker_args+=("$1")
            shift
            ;;
    esac
done
exec "$prefix/llvm/bin/ld.lld" "${linker_args[@]}"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-ld"

cat >"$bin/$TOOLCHAIN_TARGET-as" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == --version ]]; then
    exec "$prefix/llvm/bin/clang" --version
fi
out=""
inputs=()
while (($#)); do
    case "$1" in
        --32) shift ;;
        -o) out="$2"; shift 2 ;;
        -o*) out="${1#-o}"; shift ;;
        -*) shift ;;
        *) inputs+=("$1"); shift ;;
    esac
done
[[ -n "$out" && ${#inputs[@]} -gt 0 ]] || {
    printf 'error: unsupported SeaBIOS assembler invocation\n' >&2
    exit 1
}
tmp="${TMPDIR:-/tmp}/whp-i386-as.$$.$RANDOM.s"
trap 'rm -f "$tmp"' EXIT
cat "${inputs[@]}" > "$tmp"
"$prefix/llvm/bin/clang" --target=i386-none-elf -m32 -c -x assembler \
    "$tmp" -o "$out"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-as"

for pair in objcopy:llvm-objcopy objdump:llvm-objdump strip:llvm-strip; do
    name="${pair%%:*}"
    target="${pair#*:}"
    ln -sfn "../llvm/bin/$target" "$bin/$TOOLCHAIN_TARGET-$name"
done

# SeaBIOS probes -fwhole-program before enabling its whole-file optimization.
# Reject that probe so the firmware build does not mistake Clang's ignored
# compatibility spelling for a functional optimization.
if "$bin/$TOOLCHAIN_TARGET-gcc" -fwhole-program -S -o /dev/null \
       -xc /dev/null >/dev/null 2>&1; then
    printf 'error: SeaBIOS Clang shim unexpectedly accepted -fwhole-program\n' >&2
    exit 1
fi

# Validate the exact firmware ABI without pulling another inspection utility
# into the distribution. Compilation verifies the i386 target and 32-bit
# pointer model; llvm-objdump verifies linker output and relocations.
smoke_dir="$TOOLCHAIN_WORK_DIR/seabios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat >"$smoke_dir/smoke.c" <<'EOF'
#ifndef __i386__
#error compiler is not targeting i386
#endif
_Static_assert(__SIZEOF_POINTER__ == 4, "i386 pointer width mismatch");
extern int whp_seabios_external(int value);
extern int whp_seabios_global;
int whp_seabios_smoke(int value)
{
    return whp_seabios_external(value) + whp_seabios_global;
}
EOF
cat >"$smoke_dir/peer.c" <<'EOF'
int whp_seabios_global;
int whp_seabios_external(int value) { return value + 1; }
EOF
for source in smoke peer; do
    "$bin/$TOOLCHAIN_TARGET-gcc" -m32 -march=i386 -mpreferred-stack-boundary=2 \
        -fno-stack-protector -fno-stack-protector-all -fstack-check=no \
        -fno-defer-pop -ffreestanding -fno-pic -fno-pie \
        -ffunction-sections -fdata-sections -O0 \
        -c "$smoke_dir/$source.c" -o "$smoke_dir/$source.o"
done

# Relocatable links must preserve the relocation classes layoutrom.py consumes.
# They also inherit elf_i386 from the cross-linker ABI when -m is omitted.
"$bin/$TOOLCHAIN_TARGET-ld" -r "$smoke_dir/smoke.o" "$smoke_dir/peer.o" \
    -o "$smoke_dir/smoke-linked.o"
smoke_relocs="$("$bin/$TOOLCHAIN_TARGET-objdump" -r "$smoke_dir/smoke-linked.o")"
grep -q 'R_386_PC32' <<<"$smoke_relocs" || {
    printf 'error: i386 relocatable link lost R_386_PC32\n%s\n' "$smoke_relocs" >&2
    exit 1
}
grep -q 'R_386_32' <<<"$smoke_relocs" || {
    printf 'error: i386 relocatable link lost R_386_32\n%s\n' "$smoke_relocs" >&2
    exit 1
}

# Exercise the GNU linker-script constructs used by SeaBIOS's final ROM link:
# OUTPUT_FORMAT/ARCH, ABSOLUTE, LONG, PHDRS, AT(), -N, and --gc-sections.
cat >"$smoke_dir/smoke.lds" <<'EOF'
OUTPUT_FORMAT("elf32-i386")
OUTPUT_ARCH("i386")
SECTIONS
{
    code32flat_start = 0x1000;
    .text code32flat_start : {
        LONG(0)
        *(.text*)
        code32flat_end = ABSOLUTE(.);
    } :text
    .data : { *(.data*) *(.bss*) } :text
    /DISCARD/ : { *(.eh_frame) *(.note*) *(.comment*) *(.llvm_addrsig*) }
}
ENTRY(whp_seabios_smoke)
PHDRS
{
    text PT_LOAD AT ( code32flat_start );
}
EOF
"$bin/$TOOLCHAIN_TARGET-ld" -N -T "$smoke_dir/smoke.lds" \
    "$smoke_dir/smoke-linked.o" -o "$smoke_dir/smoke-final.o"
"$bin/$TOOLCHAIN_TARGET-ld" --gc-sections -T "$smoke_dir/smoke.lds" \
    "$smoke_dir/smoke-linked.o" -o "$smoke_dir/smoke-gc.o"
for linked in smoke-final.o smoke-gc.o; do
    smoke_format="$("$bin/$TOOLCHAIN_TARGET-objdump" -f "$smoke_dir/$linked")"
    if ! grep -Eq 'file format elf32-i386|architecture:[[:space:]]*i386' <<<"$smoke_format"; then
        printf 'error: i386 linker default emulation produced an unexpected format\n%s\n' \
            "$smoke_format" >&2
        exit 1
    fi
done
if "$bin/$TOOLCHAIN_TARGET-ld" -m elf_x86_64 -r "$smoke_dir/smoke.o" \
       -o "$smoke_dir/bad-emulation.o" >/dev/null 2>&1; then
    printf 'error: i386 linker accepted an incompatible emulation\n' >&2
    exit 1
fi

printf '%s\n' "$expected_marker" > "$staged_toolchain/.whp-i386-toolchain"
usable "$staged_toolchain" || {
    printf 'error: staged i386 LLVM toolchain is incomplete\n' >&2
    exit 1
}

old_toolchain="${TOOLCHAIN_DIR}.old.$$"
rm -rf "$old_toolchain"
if [[ -e "$TOOLCHAIN_DIR" ]]; then
    mv "$TOOLCHAIN_DIR" "$old_toolchain"
fi
if ! mv "$staged_toolchain" "$TOOLCHAIN_DIR"; then
    [[ ! -e "$old_toolchain" ]] || mv "$old_toolchain" "$TOOLCHAIN_DIR"
    exit 1
fi
rm -rf "$old_toolchain" "$stage_root"
stage_root=""

printf '%s\n' \
    "Bootstrapped SeaBIOS compiler: Clang ($llvm_revision)" \
    "Target: $TOOLCHAIN_TARGET" \
    'Assembler: Clang integrated assembler' \
    'Linker: ELF LLD, elf_i386 default emulation' \
    'Object tools: llvm-objcopy, llvm-objdump, llvm-strip' \
    "Compatibility prefix: $TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-"
