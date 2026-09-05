#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bootstrap="$root/scripts/bootstrap-i386-efi-grub.bash"
[[ -f "$bootstrap" ]] || {
    printf 'missing IA32 EFI GRUB bootstrap: %s\n' "$bootstrap" >&2
    exit 1
}

repo='https://github.com/retrochristian5000/grub.git'
revision='2f972128c48b90bf8b63aadffe6d546976e1dee6'

grep -Fq "GRUB_REPOSITORY=\"\${GRUB_I386_SOURCE_REPOSITORY:-$repo}\"" "$bootstrap" || {
    printf 'IA32 EFI GRUB does not default to the WHP GitHub fork\n' >&2
    exit 1
}
grep -Fq "GRUB_REVISION=\"\${GRUB_I386_SOURCE_REVISION:-$revision}\"" "$bootstrap" || {
    printf 'IA32 EFI GRUB source revision is not pinned\n' >&2
    exit 1
}
grep -Fq 'SOURCE_REPOSITORY=$GRUB_REPOSITORY' "$bootstrap" || {
    printf 'IA32 EFI GRUB marker does not record the source repository\n' >&2
    exit 1
}
grep -Fq 'SOURCE_REVISION=$GRUB_REVISION' "$bootstrap" || {
    printf 'IA32 EFI GRUB marker does not record the pinned source revision\n' >&2
    exit 1
}
if grep -Fq 'fetch --build-from-source "$FORMULA"' "$bootstrap"; then
    printf 'IA32 EFI GRUB still fetches its source through Homebrew\n' >&2
    exit 1
fi
if grep -Fq 'GRUB_I386_SOURCE_FORMULA' "$bootstrap"; then
    printf 'IA32 EFI GRUB still exposes the obsolete Homebrew source formula knob\n' >&2
    exit 1
fi

printf 'IA32 EFI GRUB source is pinned to the WHP GitHub fork: verified\n'
