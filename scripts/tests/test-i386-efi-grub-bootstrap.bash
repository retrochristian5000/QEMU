#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bootstrap="$root/scripts/bootstrap-i386-efi-grub.bash"
[[ -f "$bootstrap" ]] || {
    printf 'missing IA32 EFI GRUB bootstrap: %s\n' "$bootstrap" >&2
    exit 1
}

for probe in \
    'whp_i386_grub_cache_size' \
    '-fno-omit-frame-pointer -momit-leaf-frame-pointer' \
    '"$LLVM_BIN/ld.lld" -m elf_i386 -r' \
    '"$LLVM_BIN/llvm-objdump" -f' \
    '"$LLVM_BIN/llvm-objcopy"' \
    '"$LLVM_BIN/llvm-strip"'; do
    grep -Fq -- "$probe" "$bootstrap" || {
        printf 'GRUB i386 LLVM cache gate is not semantic: %s\n' "$probe" >&2
        exit 1
    }
done

scratch="$(mktemp -d "${TMPDIR:-/tmp}/grub-i386-efi-test.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/src/grub-test/grub-core" "$scratch/bin"

cat > "$scratch/src/grub-test/configure" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$WHP_GRUB_CONFIGURE_LOG"
{
    printf 'CC=%s\n' "${CC:-}"
    printf 'BUILD_CC=%s\n' "${BUILD_CC:-}"
    printf 'HOST_CC=%s\n' "${HOST_CC:-}"
    printf 'TARGET_CC=%s\n' "${TARGET_CC:-}"
    printf 'TARGET_CFLAGS=%s\n' "${TARGET_CFLAGS:-}"
    printf 'TARGET_CPPFLAGS=%s\n' "${TARGET_CPPFLAGS:-}"
    printf 'TARGET_CCASFLAGS=%s\n' "${TARGET_CCASFLAGS:-}"
    printf 'TARGET_LDFLAGS=%s\n' "${TARGET_LDFLAGS:-}"
    printf 'TARGET_OBJCOPY=%s\n' "${TARGET_OBJCOPY:-}"
    printf 'TARGET_NM=%s\n' "${TARGET_NM:-}"
    printf 'TARGET_RANLIB=%s\n' "${TARGET_RANLIB:-}"
    printf 'TARGET_STRIP=%s\n' "${TARGET_STRIP:-}"
    printf 'CFLAGS=%s\n' "${CFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
} > "$WHP_GRUB_TOOLCHAIN_LOG"
bindir=
libdir=
for arg in "$@"; do
    case "$arg" in
        --bindir=*) bindir="${arg#*=}" ;;
        --libdir=*) libdir="${arg#*=}" ;;
    esac
done
[[ -n "$bindir" && -n "$libdir" ]]
printf 'bindir=%q\nlibdir=%q\n' "$bindir" "$libdir" > "$PWD/whp-install.env"
SCRIPT
chmod +x "$scratch/src/grub-test/configure"
tar -C "$scratch/src" -cJf "$scratch/grub.tar.xz" grub-test

cat > "$scratch/bin/make" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
build_dir=
install=0
while (($#)); do
    case "$1" in
        -C) build_dir="$2"; shift 2 ;;
        install) install=1; shift ;;
        *) shift ;;
    esac
done
[[ -n "$build_dir" ]]
if [[ "$install" == 0 ]]; then
    exit 0
fi
source "$build_dir/whp-install.env"
mkdir -p "${DESTDIR:?}$bindir" "${DESTDIR}$libdir/grub/i386-efi"
cat > "${DESTDIR}$bindir/i386-efi-grub-mkimage" <<'MKIMAGE'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --version ]]; then
    printf 'grub-mkimage (WHP test)\n'
    exit 0
fi
out=
while (($#)); do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[[ -n "$out" ]]
printf EFI > "$out"
MKIMAGE
chmod +x "${DESTDIR}$bindir/i386-efi-grub-mkimage"
: > "${DESTDIR}$libdir/grub/i386-efi/moddep.lst"
SCRIPT
chmod +x "$scratch/bin/make"

cat > "$scratch/bin/host-cc" <<'SCRIPT'
#!/usr/bin/env bash
exit 0
SCRIPT
chmod +x "$scratch/bin/host-cc"

i386_toolchain="$scratch/i386-toolchain"
llvm_bin="$i386_toolchain/llvm/bin"
mkdir -p "$llvm_bin"
for tool in clang ld.lld llvm-ar llvm-nm llvm-ranlib llvm-objcopy llvm-strip llvm-objdump; do
    cat > "$llvm_bin/$tool" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
tool="${0##*/}"
if [[ "${1:-}" == --version ]]; then
    printf 'WHP LLVM fork test tool\n'
    exit 0
fi
case "$tool" in
    clang|ld.lld)
        out=""
        while (($#)); do
            case "$1" in
                -o) out="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        [[ -z "$out" ]] || printf 'ELF' > "$out"
        ;;
    llvm-objcopy)
        cp "$1" "$2"
        ;;
    llvm-strip)
        out=""
        input=""
        while (($#)); do
            case "$1" in
                -o) out="$2"; shift 2 ;;
                *) input="$1"; shift ;;
            esac
        done
        [[ -n "$out" && -n "$input" ]]
        cp "$input" "$out"
        ;;
    llvm-objdump)
        if [[ "${1:-}" == -f ]]; then
            printf '%s\n' \
                'file format elf32-i386' \
                'architecture: i386'
        fi
        ;;
esac
exit 0
SCRIPT
    chmod +x "$llvm_bin/$tool"
done
cat > "$i386_toolchain/.whp-i386-toolchain" <<'EOF_MARKER'
BOOTSTRAP_SCHEMA=15
TARGET=i386-none-elf
LLVM_DISTRIBUTION=firmware-minimal
COMPILER=clang
EOF_MARKER

install="$scratch/install/grub-i386-efi"
run_bootstrap()
{
    PATH="$scratch/bin:$PATH" \
    BUILD_DIR="$scratch/build" \
    I386_TOOLCHAIN_DIR="$i386_toolchain" \
    GRUB_I386_LLVM_BIN="$llvm_bin" \
    GRUB_I386_BUILD_CC="$scratch/bin/host-cc" \
    GRUB_I386_INSTALL_PREFIX="$install" \
    GRUB_I386_SOURCE_ARCHIVE="$scratch/grub.tar.xz" \
    GRUB_I386_AUTO_INSTALL_DEPS=0 \
    WHP_GRUB_CONFIGURE_LOG="$scratch/configure.log" \
    WHP_GRUB_TOOLCHAIN_LOG="$scratch/toolchain.log" \
    CFLAGS='-arch arm64 -mmacosx-version-min=15.0' \
    CPPFLAGS='-arch arm64' \
    LDFLAGS='-mmacosx-version-min=15.0' \
    JOBS=1 \
    bash "$bootstrap" "$@"
}

run_bootstrap > "$scratch/first.log"
grep -Fxq -- '--target=i386-none-elf' "$scratch/configure.log"
grep -Fxq -- '--with-platform=efi' "$scratch/configure.log"
if grep -Fq -- '--with-platform=pc' "$scratch/configure.log"; then
    printf 'bootstrap configured the PC platform instead of EFI\n' >&2
    exit 1
fi

grep -Fxq "CC=$scratch/bin/host-cc" "$scratch/toolchain.log"
grep -Fxq "BUILD_CC=$scratch/bin/host-cc" "$scratch/toolchain.log"
grep -Fxq "HOST_CC=$scratch/bin/host-cc" "$scratch/toolchain.log"
grep -Fxq "TARGET_CC=$llvm_bin/clang" "$scratch/toolchain.log"
grep -Eq '^TARGET_CFLAGS=.*--target=i386-none-elf' "$scratch/toolchain.log"
grep -Eq '^TARGET_CPPFLAGS=.*--target=i386-none-elf' "$scratch/toolchain.log"
grep -Eq '^TARGET_CCASFLAGS=.*--target=i386-none-elf' "$scratch/toolchain.log"
grep -Eq '^TARGET_LDFLAGS=.*--target=i386-none-elf.*-fuse-ld=lld' "$scratch/toolchain.log"
grep -Fxq "TARGET_OBJCOPY=$llvm_bin/llvm-objcopy" "$scratch/toolchain.log"
grep -Fxq "TARGET_NM=$llvm_bin/llvm-nm" "$scratch/toolchain.log"
grep -Fxq "TARGET_RANLIB=$llvm_bin/llvm-ranlib" "$scratch/toolchain.log"
grep -Fxq "TARGET_STRIP=$llvm_bin/llvm-strip" "$scratch/toolchain.log"
grep -Fxq 'CFLAGS=' "$scratch/toolchain.log"
grep -Fxq 'CPPFLAGS=' "$scratch/toolchain.log"
grep -Fxq 'LDFLAGS=' "$scratch/toolchain.log"
if grep -Eq '(^|[ =])(-arch|-mmacosx-version-min)' "$scratch/toolchain.log"; then
    printf 'Darwin host flags leaked into the IA32 EFI GRUB target configuration\n' >&2
    cat "$scratch/toolchain.log" >&2
    exit 1
fi
if grep -Eq '(i686-elf-gcc|/opt/homebrew/.*/clang|/usr/local/.*/clang)' "$scratch/toolchain.log"; then
    printf 'IA32 EFI GRUB escaped the QEMU LLVM-fork toolchain ABI\n' >&2
    exit 1
fi

[[ -x "$install/bin/i386-efi-grub-mkimage" ]]
[[ -f "$install/lib/i386-none-elf/grub/i386-efi/moddep.lst" ]]
[[ -f "$install/.whp-grub-i386-efi" ]]
grep -Fxq 'BOOTSTRAP_SCHEMA=5' "$install/.whp-grub-i386-efi"
grep -Fxq 'TOOLCHAIN=whp-llvm-fork' "$install/.whp-grub-i386-efi"
grep -Fxq "LLVM_BIN=$llvm_bin" "$install/.whp-grub-i386-efi"

printf 'sentinel\n' > "$scratch/configure.log"
run_bootstrap > "$scratch/second.log"
grep -Fxq 'sentinel' "$scratch/configure.log"
grep -Fq 'IA32 EFI GRUB is current:' "$scratch/second.log"

old_marker="$(cat "$install/.whp-grub-i386-efi")"
printf 'new source revision\n' > "$scratch/src/grub-test/revision.txt"
tar -C "$scratch/src" -cJf "$scratch/grub.tar.xz" grub-test
printf 'stale-cache-sentinel\n' > "$scratch/configure.log"
run_bootstrap > "$scratch/third.log"
grep -Fxq -- '--target=i386-none-elf' "$scratch/configure.log"
new_marker="$(cat "$install/.whp-grub-i386-efi")"
[[ "$new_marker" != "$old_marker" ]] || {
    printf 'source archive changed without invalidating the IA32 EFI GRUB marker\n' >&2
    exit 1
}
grep -Fq 'SOURCE_CKSUM=' <<<"$new_marker"

printf 'IA32 EFI GRUB reuses the WHP LLVM fork with clean host/target flags: verified\n'
