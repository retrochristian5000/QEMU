#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
configure_openbios="$ROOT/scripts/whp-build/configure-openbios.bash"
meson_openbios="$ROOT/scripts/meson-build-openbios.sh"
ci="$ROOT/.github/workflows/ci.yml"
switch_arch="$ROOT/roms/openbios/config/scripts/switch-arch"

if [[ ! -f "$switch_arch" ]]; then
    printf '%s\n' \
        'error: OpenBIOS submodule is not initialized for host portability tests.' \
        'run: git submodule update --init roms/openbios' >&2
    exit 1
fi

# OpenBIOS host configuration must retain the 64-bit aarch64 classification.
# Without it, forthstrap truncates host pointers while building a 32-bit PPC
# dictionary on Apple Silicon and other aarch64 hosts.
grep -Fq 's/arm64/aarch64/' "$switch_arch"
grep -Fq -- '-o "$cpu" = "aarch64"' "$switch_arch"

# xsltproc is a build-host tool, not a target tool. Keep its selection explicit
# and serialized just like toke/readelf so hosts with keg-only or nonstandard
# package layouts do not depend on ambient PATH accidents.
grep -Fq "printf 'OPENBIOS_XSLTPROC=%q" "$configure_openbios"
grep -Fq 'OPENBIOS_XSLTPROC="${OPENBIOS_XSLTPROC:-}"' "$meson_openbios"
grep -Fq 'OPENBIOS_ENVIRONMENT_POLICY=9' "$meson_openbios"
grep -Fq '$(dirname "$OPENBIOS_XSLTPROC")' "$meson_openbios"

# The Apple Silicon lane must execute the actual firmware and cross-toolchain
# path; a QEMU-only macOS build cannot catch host-specific OpenBIOS failures.
macos_openbios_job="$(awk '
    /^  build-macos-openbios:/ { capture=1 }
    capture && /^  [A-Za-z0-9_-]+:/ && $1 != "build-macos-openbios:" { exit }
    capture { print }
' "$ci")"
if [[ -z "$macos_openbios_job" ]]; then
    printf 'error: dedicated macOS OpenBIOS CI job is missing\n' >&2
    exit 1
fi
grep -Fq 'runs-on: macos-15' <<< "$macos_openbios_job"
grep -Fq 'test "$(uname -m)" = arm64' <<< "$macos_openbios_job"
grep -Fq "BUILD_OPENBIOS: '1'" <<< "$macos_openbios_job"
grep -Fq "BOOTSTRAP_POWERPC_TOOLCHAIN: '1'" <<< "$macos_openbios_job"
grep -Fq 'libxslt' <<< "$macos_openbios_job"
grep -Fq 'OPENBIOS_XSLTPROC' <<< "$macos_openbios_job"
grep -Fq './build.sh whp-openbios-ppc' <<< "$macos_openbios_job"
grep -Fq 'whp-firmware-tools-arm64-apple-darwin/powerpc-elf/.whp-powerpc-*' \
    <<< "$macos_openbios_job"

printf 'OpenBIOS host portability guards: verified\n'
