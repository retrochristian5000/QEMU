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

[[ "$TOOLCHAIN_TARGET" == i386-none-elf ]] || {
    printf 'error: i386 LLVM firmware lane requires i386-none-elf\n' >&2
    exit 1
}
case "$TOOLCHAIN_FORCE_REBUILD" in 0|1) ;; *)
    printf 'error: I386_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
    exit 1
;; esac

for tool in git cmake ninja awk grep mkdir rm ln; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: i386 LLVM bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

if [[ ! -f "$LLVM_SOURCE_DIR/llvm/CMakeLists.txt" ]]; then
    git -C "$SOURCE_DIR" submodule update --init --depth 1 "$LLVM_SUBMODULE_PATH"
fi
[[ -f "$LLVM_SOURCE_DIR/clang/CMakeLists.txt" && -f "$LLVM_SOURCE_DIR/lld/CMakeLists.txt" ]] || {
    printf 'error: LLVM submodule is missing clang/lld: %s\n' "$LLVM_SOURCE_DIR" >&2
    exit 1
}

llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse HEAD)"
marker="$TOOLCHAIN_DIR/.whp-i386-toolchain"
expected_marker="$(cat <<EOF
BOOTSTRAP_SCHEMA=1
TARGET=$TOOLCHAIN_TARGET
LLVM_GIT_COMMIT=$llvm_revision
LLVM_TARGETS_TO_BUILD=X86
LINKER=ld.lld
BINUTILS=llvm
EOF
)"

usable()
{
    local tool
    [[ -x "$TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-gcc" ]] || return 1
    for tool in as ld ar nm objcopy objdump readelf strip ranlib; do
        [[ -x "$TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-$tool" ]] || return 1
    done
}

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 && -f "$marker" && "$(cat "$marker")" == "$expected_marker" ]] && usable; then
    printf 'i386 LLVM toolchain is current: %s/bin/%s-\n' "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    exit 0
fi

mkdir -p "$TOOLCHAIN_WORK_DIR"
if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then
    rm -rf "$LLVM_BUILD_DIR"
fi

cmake_args=(
    -S "$LLVM_SOURCE_DIR/llvm"
    -B "$LLVM_BUILD_DIR"
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR/llvm"
    '-DLLVM_ENABLE_PROJECTS=clang;lld'
    -DLLVM_TARGETS_TO_BUILD=X86
    -DLLVM_INCLUDE_TESTS=OFF
    -DLLVM_INCLUDE_EXAMPLES=OFF
    -DLLVM_INCLUDE_BENCHMARKS=OFF
    -DCLANG_INCLUDE_TESTS=OFF
    -DLLD_INCLUDE_TESTS=OFF
    -DLLVM_ENABLE_TERMINFO=OFF
    -DLLVM_ENABLE_ZLIB=OFF
    -DLLVM_ENABLE_ZSTD=OFF
)
cmake "${cmake_args[@]}"
if [[ -n "$JOBS" ]]; then
    cmake --build "$LLVM_BUILD_DIR" --parallel "$JOBS" --target clang lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-readelf llvm-strip
else
    cmake --build "$LLVM_BUILD_DIR" --parallel --target clang lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-readelf llvm-strip
fi
cmake --install "$LLVM_BUILD_DIR"

llvm="$TOOLCHAIN_DIR/llvm/bin"
bin="$TOOLCHAIN_DIR/bin"
mkdir -p "$bin"
for required in clang ld.lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-readelf llvm-strip llvm-ranlib llvm-mc; do
    [[ -x "$llvm/$required" ]] || {
        printf 'error: LLVM install did not produce %s\n' "$required" >&2
        exit 1
    }
done

cat >"$bin/$TOOLCHAIN_TARGET-gcc" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
args=()
for arg in "$@"; do
    case "$arg" in
        -fno-defer-pop|-fwhole-program) ;;
        *) args+=("$arg") ;;
    esac
done
exec "$prefix/llvm/bin/clang" --target=i386-none-elf -fuse-ld=lld "${args[@]}"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-gcc"

cat >"$bin/$TOOLCHAIN_TARGET-ld" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
args=()
for arg in "$@"; do
    case "$arg" in
        -melf_i386) args+=(-m elf_i386) ;;
        *) args+=("$arg") ;;
    esac
done
exec "$prefix/llvm/bin/ld.lld" "${args[@]}"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-ld"

cat >"$bin/$TOOLCHAIN_TARGET-as" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
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
[[ -n "$out" && ${#inputs[@]} -gt 0 ]] || { echo 'error: unsupported SeaBIOS assembler invocation' >&2; exit 1; }
tmp="${TMPDIR:-/tmp}/whp-i386-as.$$.$RANDOM.s"
trap 'rm -f "$tmp"' EXIT
cat "${inputs[@]}" > "$tmp"
exec "$prefix/llvm/bin/llvm-mc" --triple=i386-none-elf --filetype=obj "$tmp" -o "$out"
EOF
chmod +x "$bin/$TOOLCHAIN_TARGET-as"

for pair in \
    ar:llvm-ar nm:llvm-nm objcopy:llvm-objcopy objdump:llvm-objdump \
    readelf:llvm-readelf strip:llvm-strip ranlib:llvm-ranlib; do
    name="${pair%%:*}"
    target="${pair#*:}"
    ln -sfn "../llvm/bin/$target" "$bin/$TOOLCHAIN_TARGET-$name"
done

printf '%s\n' "$expected_marker" > "$marker"
usable || {
    printf 'error: staged i386 LLVM toolchain is incomplete\n' >&2
    exit 1
}
printf 'i386 LLVM toolchain ready: %s/bin/%s-\n' "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
