#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
WIN9X_TARGET="${WIN9X_TOOLCHAIN_TARGET:-i386-pc-win9x}"
I386_TARGET="${I386_TOOLCHAIN_TARGET:-i386-none-elf}"
I386_BOOTSTRAP="$SOURCE_DIR/scripts/bootstrap-i386-clang.sh"
I386_TOOLCHAIN_DIR="${I386_TOOLCHAIN_DIR:-$SOURCE_DIR/build/firmware-tools/$I386_TARGET}"
I386_TOOLCHAIN_WORK_DIR="${I386_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$I386_TARGET-clang}"
LLVM_SUBMODULE_PATH="${I386_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SOURCE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
LLVM_BUILD_DIR="${I386_LLVM_BUILD_DIR:-$I386_TOOLCHAIN_WORK_DIR/llvm-build}"
WIN9X_TOOLCHAIN_DIR="${WIN9X_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$WIN9X_TARGET}"
JOBS="${JOBS:-}"

[[ "$WIN9X_TARGET" == i386-pc-win9x ]] || {
    printf 'error: Win9x LLVM lane requires i386-pc-win9x\n' >&2
    exit 1
}
[[ "$I386_TARGET" == i386-none-elf ]] || {
    printf 'error: shared x86 LLVM core requires i386-none-elf bootstrap\n' >&2
    exit 1
}
[[ -x "$I386_BOOTSTRAP" ]] || {
    printf 'error: shared i386 LLVM bootstrap is missing: %s\n' "$I386_BOOTSTRAP" >&2
    exit 1
}

for tool in cmake git grep mkdir rm python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: Win9x LLVM bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

# Reuse the existing X86 Clang/LLVM build. Win9x only needs one additional LLD
# object-format backend, so do not build a second LLVM tree for this ABI.
"$I386_BOOTSTRAP"

[[ -f "$LLVM_SOURCE_DIR/llvm/CMakeLists.txt" ]] || {
    printf 'error: LLVM source is missing after i386 bootstrap: %s\n' \
        "$LLVM_SOURCE_DIR" >&2
    exit 1
}

llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse HEAD)"
marker="$WIN9X_TOOLCHAIN_DIR/.whp-win9x-toolchain"
expected_marker="$(cat <<EOF
BOOTSTRAP_SCHEMA=1
TARGET=$WIN9X_TARGET
LLVM_GIT_COMMIT=$llvm_revision
LLVM_TARGETS_TO_BUILD=X86
LLD_ENABLE_BACKENDS=ELF;COFF
OBJECT_FORMAT=PE32-COFF-i386
CPU_BASELINE=i386
POINTER_WIDTH=32
RUNTIME=freestanding-no-default-libraries
SUBSYSTEM_BASELINE=windows-4.0
EOF
)"

usable()
{
    local bin="$WIN9X_TOOLCHAIN_DIR/bin"

    [[ -x "$bin/$WIN9X_TARGET-clang" &&
       -x "$bin/$WIN9X_TARGET-lld-link" &&
       -x "$bin/$WIN9X_TARGET-objdump" &&
       -f "$LLVM_BUILD_DIR/CMakeCache.txt" ]] || return 1
    grep -Fq 'LLD_ENABLE_BACKENDS:STRING=ELF;COFF' \
        "$LLVM_BUILD_DIR/CMakeCache.txt" || return 1
}

if [[ -f "$marker" && "$(cat "$marker")" == "$expected_marker" ]] && usable; then
    printf 'Win9x LLVM toolchain is current: %s/bin/%s-\n' \
        "$WIN9X_TOOLCHAIN_DIR" "$WIN9X_TARGET"
    exit 0
fi

cmake -S "$LLVM_SOURCE_DIR/llvm" -B "$LLVM_BUILD_DIR" \
    '-DLLD_ENABLE_BACKENDS=ELF;COFF'

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

cmake --build "$LLVM_BUILD_DIR" --target lld "${cmake_parallel_args[@]}"
cmake --build "$LLVM_BUILD_DIR" --target install-lld "${cmake_parallel_args[@]}"

shared_llvm="$I386_TOOLCHAIN_DIR/llvm/bin"
for required in clang lld-link llvm-objdump; do
    [[ -x "$shared_llvm/$required" ]] || {
        printf 'error: shared X86 LLVM build did not produce %s\n' "$required" >&2
        exit 1
    }
done

bin="$WIN9X_TOOLCHAIN_DIR/bin"
rm -rf "$WIN9X_TOOLCHAIN_DIR"
mkdir -p "$bin"

cat >"$bin/$WIN9X_TARGET-clang" <<EOF
#!/usr/bin/env bash
set -euo pipefail
WIN9X_TARGET="$WIN9X_TARGET"
exec "$shared_llvm/clang" --target="\$WIN9X_TARGET" -m32 -march=i386 "\$@"
EOF
chmod +x "$bin/$WIN9X_TARGET-clang"

cat >"$bin/$WIN9X_TARGET-lld-link" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$shared_llvm/lld-link" /machine:x86 /subsystem:windows,4.0 \
    /nodefaultlib "\$@"
EOF
chmod +x "$bin/$WIN9X_TARGET-lld-link"

cat >"$bin/$WIN9X_TARGET-objdump" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$shared_llvm/llvm-objdump" "\$@"
EOF
chmod +x "$bin/$WIN9X_TARGET-objdump"

# Validate both compiler ABI and final executable format without importing a
# host CRT. The API level is intentionally separate from this generic Win9x ABI.
smoke_dir="$I386_TOOLCHAIN_WORK_DIR/win9x-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat >"$smoke_dir/smoke.c" <<'EOF'
#ifndef _WIN32
#error compiler is not targeting Win32
#endif
#ifndef __i386__
#error compiler is not targeting i386
#endif
_Static_assert(__SIZEOF_POINTER__ == 4, "Win9x pointer width mismatch");
int whp_win9x_smoke(void) { return 9; }
EOF
cat >"$smoke_dir/entry.s" <<'EOF'
.text
.globl _whp_win9x_entry
_whp_win9x_entry:
    jmp _whp_win9x_entry
EOF

"$bin/$WIN9X_TARGET-clang" -ffreestanding -fno-builtin -fno-stack-protector \
    -c "$smoke_dir/smoke.c" -o "$smoke_dir/smoke.obj"
"$bin/$WIN9X_TARGET-clang" -c -x assembler "$smoke_dir/entry.s" \
    -o "$smoke_dir/entry.obj"
"$bin/$WIN9X_TARGET-lld-link" /entry:_whp_win9x_entry \
    /out:"$smoke_dir/smoke.exe" "$smoke_dir/entry.obj"

python3 - "$smoke_dir/smoke.exe" <<'PY'
import struct
import sys

path = sys.argv[1]
data = open(path, 'rb').read()
if data[:2] != b'MZ':
    raise SystemExit('error: Win9x smoke image is missing MZ header')
pe = struct.unpack_from('<I', data, 0x3c)[0]
if data[pe:pe + 4] != b'PE\0\0':
    raise SystemExit('error: Win9x smoke image is missing PE signature')
if struct.unpack_from('<H', data, pe + 4)[0] != 0x014c:
    raise SystemExit('error: Win9x smoke image is not IMAGE_FILE_MACHINE_I386')
optional = pe + 24
if struct.unpack_from('<H', data, optional)[0] != 0x010b:
    raise SystemExit('error: Win9x smoke image is not PE32')
major, minor = struct.unpack_from('<HH', data, optional + 0x30)
if (major, minor) != (4, 0):
    raise SystemExit(
        f'error: Win9x subsystem version is {major}.{minor}, expected 4.0')
if struct.unpack_from('<H', data, optional + 0x44)[0] != 2:
    raise SystemExit('error: Win9x smoke image is not Windows GUI subsystem')
import_rva, import_size = struct.unpack_from('<II', data, optional + 0x68)
if import_rva or import_size:
    raise SystemExit('error: Win9x smoke image unexpectedly imports a runtime')
PY

printf '%s\n' "$expected_marker" >"$marker"
printf 'Win9x LLVM toolchain ready: %s/bin/%s-\n' \
    "$WIN9X_TOOLCHAIN_DIR" "$WIN9X_TARGET"
