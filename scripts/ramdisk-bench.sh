#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Measure a scratch file on a guest RAM-backed filesystem. No raw disk writes.
set -eu

usage()
{
    printf 'Usage: sh %s MOUNT_DIRECTORY [SIZE_MIB]\n' "$0" >&2
    exit 2
}

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage
dir=$1
mib=${2:-4}
case $mib in
    ''|*[!0-9]*|0*) usage ;;
esac
[ "${#mib}" -le 3 ] || usage
[ "$mib" -ge 1 ] && [ "$mib" -le 256 ] || usage
[ -d "$dir" ] && [ -w "$dir" ] || {
    printf 'Error: supply a writable mounted RAM-disk directory.\n' >&2
    exit 1
}

# Convert to an absolute path before making or cleaning up scratch files.
dir=$(cd "$dir" && pwd -P)
umask 077
scratch=$dir/qemu-ramdisk-bench.$$
mkdir "$scratch" || exit 1
cleanup()
{
    rm -f "$scratch/payload"
    rmdir "$scratch"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

blocks=$((mib * 16))
printf 'Directory: %s\nPayload: %s MiB\n' "$dir" "$mib"
printf 'Guest kernel: '
uname -r
printf '\nControl: zero source to null sink\n'
time dd if=/dev/zero of=/dev/null bs=65536 count="$blocks"
printf '\nRAM filesystem write (allocation plus copy)\n'
time dd if=/dev/zero of="$scratch/payload" bs=65536 count="$blocks"
printf '\nRAM filesystem read (warm cache)\n'
time dd if="$scratch/payload" of=/dev/null bs=65536
printf '\nRAM filesystem overwrite (existing allocation)\n'
time dd if=/dev/zero of="$scratch/payload" bs=65536 count="$blocks" conv=notrunc
