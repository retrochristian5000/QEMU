#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
CORE="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"

for file in "$BASE" "$CORE"; do
    if [[ ! -f "$file" ]]; then
        printf 'error: required LLVM bootstrap script is missing: %s\n' "$file" >&2
        exit 1
    fi
done

# The compiler bootstrap is mostly C++. Keep C at the existing -O2 profile,
# but let C++ use a lighter, stable optimization level so header-driven
# incremental rebuilds spend less time re-optimizing every affected TU.
grep -Fq 'LLVM_CXX_OPTIMIZATION="${POWERPC_LLVM_CXX_OPTIMIZATION:--O1}"' "$BASE"
grep -Fq 'POWERPC_LLVM_CXX_OPTIMIZATION must be one of -O0, -O1, -O2, -O3, -Os, or -Oz' "$BASE"
grep -Fq 'host_c_release_flags="-O2 -DNDEBUG -fno-function-sections -fno-data-sections"' "$BASE"
grep -Fq 'host_cxx_release_flags="$LLVM_CXX_OPTIMIZATION -DNDEBUG -fno-function-sections -fno-data-sections"' "$BASE"
grep -Fq '"-DCMAKE_C_FLAGS_RELEASE=$host_c_release_flags"' "$BASE"
grep -Fq '"-DCMAKE_CXX_FLAGS_RELEASE=$host_cxx_release_flags"' "$BASE"

# Persist each language profile independently. A changed optimization knob must
# invalidate the installed-toolchain marker once, while identical subsequent
# invocations remain eligible for the fast current-toolchain exit.
grep -Fq 'BOOTSTRAP_SCHEMA=18' "$BASE"
grep -Fq 'HOST_C_RELEASE_FLAGS=$host_c_release_flags' "$BASE"
grep -Fq 'HOST_CXX_RELEASE_FLAGS=$host_cxx_release_flags' "$BASE"
if grep -Fq 'HOST_RELEASE_FLAGS=' "$BASE"; then
    printf 'error: base bootstrap still flattens C and C++ release flags\n' >&2
    exit 1
fi

# LLD must inherit the exact split profile from the base marker instead of
# recombining both languages under the old shared HOST_RELEASE_FLAGS value.
grep -Fq 'LLD_SCHEMA=5' "$CORE"
grep -Fq 'HOST_C_RELEASE_FLAGS' "$CORE"
grep -Fq 'HOST_CXX_RELEASE_FLAGS' "$CORE"
grep -Fq '"-DCMAKE_C_FLAGS_RELEASE=$lld_host_c_release_flags"' "$CORE"
grep -Fq '"-DCMAKE_CXX_FLAGS_RELEASE=$lld_host_cxx_release_flags"' "$CORE"
if grep -Fq 'lld_host_release_flags=' "$CORE"; then
    printf 'error: LLD bootstrap still reuses one release flag string for both languages\n' >&2
    exit 1
fi

printf 'PowerPC LLVM incremental C++ flag policy: verified\n'
