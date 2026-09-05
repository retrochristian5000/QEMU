#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bootstrap="$root/scripts/bootstrap-i386-efi-grub.bash"
gitmodules="$root/.gitmodules"
[[ -f "$bootstrap" ]] || {
    printf 'missing IA32 EFI GRUB bootstrap: %s\n' "$bootstrap" >&2
    exit 1
}

grep -Fq '[submodule "toolchains/grub"]' "$gitmodules" || {
    printf 'QEMU does not declare the WHP GRUB submodule\n' >&2
    exit 1
}
grep -Fq $'\tpath = toolchains/grub' "$gitmodules" || {
    printf 'WHP GRUB submodule path is not toolchains/grub\n' >&2
    exit 1
}
grep -Fq $'\turl = https://github.com/retrochristian5000/grub.git' "$gitmodules" || {
    printf 'WHP GRUB submodule does not use the fork repository\n' >&2
    exit 1
}
grep -Fq 'GRUB_SUBMODULE_PATH="${GRUB_I386_SUBMODULE_PATH:-toolchains/grub}"' "$bootstrap" || {
    printf 'IA32 EFI GRUB does not default to the QEMU GRUB gitlink\n' >&2
    exit 1
}
grep -Fq 'git -C "$SOURCE_DIR" submodule update --init --depth 1 -- "$GRUB_SUBMODULE_PATH"' "$bootstrap" || {
    printf 'IA32 EFI GRUB does not initialize the pinned submodule\n' >&2
    exit 1
}
grep -Fq 'git -C "$GRUB_SUBMODULE_DIR" archive --format=tar "$GRUB_REVISION"' "$bootstrap" || {
    printf 'IA32 EFI GRUB does not build from an immutable gitlink snapshot\n' >&2
    exit 1
}
grep -Fq 'build-aux/whp-configure-toolchain' "$bootstrap" || {
    printf 'IA32 EFI GRUB does not consume the GRUB-owned toolchain frontend\n' >&2
    exit 1
}
grep -Fq -- '--with-target-toolchain=llvm' "$bootstrap" || {
    printf 'IA32 EFI GRUB does not request the GRUB LLVM toolchain mode\n' >&2
    exit 1
}
grep -Fq 'SOURCE_SUBMODULE=$GRUB_SUBMODULE_PATH' "$bootstrap" || {
    printf 'IA32 EFI GRUB marker does not record the source submodule\n' >&2
    exit 1
}
grep -Fq 'SOURCE_REVISION=$GRUB_REVISION' "$bootstrap" || {
    printf 'IA32 EFI GRUB marker does not record the gitlink revision\n' >&2
    exit 1
}
if grep -Fq 'GRUB_I386_SOURCE_REPOSITORY' "$bootstrap" ||
   grep -Fq 'GRUB_I386_SOURCE_REVISION' "$bootstrap" ||
   grep -Fq 'remote add origin' "$bootstrap" ||
   grep -Fq 'git -C "$source_root" fetch' "$bootstrap"; then
    printf 'IA32 EFI GRUB still carries an independent clone/pin path\n' >&2
    exit 1
fi
if grep -Fq 'fetch --build-from-source "$FORMULA"' "$bootstrap" ||
   grep -Fq 'GRUB_I386_SOURCE_FORMULA' "$bootstrap"; then
    printf 'IA32 EFI GRUB still fetches its source through Homebrew\n' >&2
    exit 1
fi

printf 'IA32 EFI GRUB is pinned by QEMU and delegates LLVM policy to GRUB: verified\n'
