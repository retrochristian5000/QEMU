#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
meson_openbios="$ROOT/scripts/meson-build-openbios.sh"

for required in awk grep make mktemp; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: required OpenBIOS environment test tool is missing: %s\n' \
            "$required" >&2
        exit 1
    fi
done

# Exercise the exact clean-environment array used at the Meson/OpenBIOS
# boundary without sourcing the rest of the build driver.
clean_env_definition="$(awk '
    /^openbios_clean_env=\($/ { capture=1 }
    capture { print }
    capture && /^\)$/ { exit }
' "$meson_openbios")"
if [[ -z "$clean_env_definition" ]]; then
    printf 'error: OpenBIOS clean-environment definition is missing\n' >&2
    exit 1
fi
eval "$clean_env_definition"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/openbios-shell-env.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

cat > "$scratch/child.mk" <<'MAKEFILE'
CC := powerpc-elf-gcc
LD := powerpc-elf-ld
AR := powerpc-elf-ar
all:
	@printf 'CC=%s\nLD=%s\nAR=%s\n' '$(CC)' '$(LD)' '$(AR)'
MAKEFILE

cat > "$scratch/poison.mk" <<'MAKEFILE'
override CC := makefiles-host-cc
override LD := makefiles-host-ld
override AR := makefiles-host-ar
MAKEFILE

# GNU Make exports command-line assignments through MAKEFLAGS/MAKEOVERRIDES.
# Merely unsetting CC/LD/AR therefore does not isolate the firmware make: the
# next make process recreates those variables from MAKEFLAGS.  MAKEFILES can
# also inject arbitrary makefile state before OpenBIOS parses its own files.
make_output="$(
    MAKEFLAGS='rR -- CC=makeflags-host-cc LD=makeflags-host-ld AR=makeflags-host-ar' \
    MAKEOVERRIDES='CC=makeflags-host-cc LD=makeflags-host-ld AR=makeflags-host-ar' \
    MAKEFILES="$scratch/poison.mk" \
        "${openbios_clean_env[@]}" \
        make --no-print-directory -f "$scratch/child.mk"
)"
expected_make_output=$'CC=powerpc-elf-gcc\nLD=powerpc-elf-ld\nAR=powerpc-elf-ar'
if [[ "$make_output" != "$expected_make_output" ]]; then
    printf '%s\n' \
        'error: parent Make state leaked into the isolated OpenBIOS build.' \
        "$make_output" >&2
    exit 1
fi

# Non-interactive Bash reads BASH_ENV before executing a build script.  A user
# or CI environment must not be able to mutate the firmware bootstrap that way.
printf 'export WHP_OPENBIOS_BASH_ENV_POISON=1\n' > "$scratch/bash-env"
if ! BASH_ENV="$scratch/bash-env" \
    "${openbios_clean_env[@]}" \
    bash -c 'test -z "${WHP_OPENBIOS_BASH_ENV_POISON:-}"'; then
    printf 'error: BASH_ENV leaked into an isolated OpenBIOS shell\n' >&2
    exit 1
fi

# Keep all GNU Make recursion/control channels and shell startup hooks out of
# the firmware boundary.  JOBS and MAKE_CMD are passed back explicitly.
for variable in \
    MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MAKELEVEL \
    BASH_ENV ENV SHELLOPTS BASHOPTS; do
    if ! grep -Fq -- "-u $variable" "$meson_openbios"; then
        printf 'error: OpenBIOS clean environment does not unset %s\n' \
            "$variable" >&2
        exit 1
    fi
done

printf 'OpenBIOS shell environment isolation: verified\n'
