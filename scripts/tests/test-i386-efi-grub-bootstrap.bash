#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bootstrap="$root/scripts/bootstrap-i386-efi-grub.sh"
[[ -f "$bootstrap" ]] || {
    printf 'missing IA32 EFI GRUB bootstrap: %s\n' "$bootstrap" >&2
    exit 1
}

scratch="$(mktemp -d "${TMPDIR:-/tmp}/grub-i386-efi-test.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/src/grub-test" "$scratch/bin"

cat > "$scratch/src/grub-test/configure" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$WHP_GRUB_CONFIGURE_LOG"
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
# shellcheck disable=SC1090
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

for tool in gcc ld objcopy nm ranlib strip; do
    cat > "$scratch/bin/i686-elf-$tool" <<'SCRIPT'
#!/usr/bin/env bash
exit 0
SCRIPT
    chmod +x "$scratch/bin/i686-elf-$tool"
done

install="$scratch/install/grub-i386-efi"
PATH="$scratch/bin:$PATH" \
BUILD_DIR="$scratch/build" \
GRUB_I386_INSTALL_PREFIX="$install" \
GRUB_I386_SOURCE_ARCHIVE="$scratch/grub.tar.xz" \
GRUB_I386_AUTO_INSTALL_DEPS=0 \
WHP_GRUB_CONFIGURE_LOG="$scratch/configure.log" \
JOBS=1 \
bash "$bootstrap" > "$scratch/first.log"

grep -Fxq -- '--target=i686-elf' "$scratch/configure.log"
grep -Fxq -- '--with-platform=efi' "$scratch/configure.log"
if grep -Fq -- '--with-platform=pc' "$scratch/configure.log"; then
    printf 'bootstrap configured the PC platform instead of EFI\n' >&2
    exit 1
fi
[[ -x "$install/bin/i386-efi-grub-mkimage" ]]
[[ -f "$install/lib/i686-elf/grub/i386-efi/moddep.lst" ]]
[[ -f "$install/.whp-grub-i386-efi" ]]

printf 'sentinel\n' > "$scratch/configure.log"
PATH="$scratch/bin:$PATH" \
BUILD_DIR="$scratch/build" \
GRUB_I386_INSTALL_PREFIX="$install" \
GRUB_I386_SOURCE_ARCHIVE="$scratch/grub.tar.xz" \
GRUB_I386_AUTO_INSTALL_DEPS=0 \
WHP_GRUB_CONFIGURE_LOG="$scratch/configure.log" \
JOBS=1 \
bash "$bootstrap" > "$scratch/second.log"
grep -Fxq 'sentinel' "$scratch/configure.log"
grep -Fq 'IA32 EFI GRUB is current:' "$scratch/second.log"

printf 'IA32 EFI GRUB bootstrap and cache policy: verified\n'
