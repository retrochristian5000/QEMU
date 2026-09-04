#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
base="$ROOT/scripts/bootstrap-powerpc-clang-base.bash"

validation="$(awk '
    /bootstrap_stage="validating Clang integrated assembler substitution"/ { in_validation=1 }
    in_validation { print }
    in_validation && /printf '\''%s\\n'\'' "\$expected_marker"/ { exit }
' "$base")"

for required in \
    'smoke_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/smoke.o")"' \
    'smoke_sections="$(LC_ALL=C "$llvm_readelf" -SW "$smoke_dir/smoke.o")"' \
    'smoke64_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/smoke64.o")"'; do
    if ! grep -Fq "$required" <<< "$validation"; then
        printf 'error: Clang validation does not capture llvm-readelf output safely: %s\n' \
            "$required" >&2
        exit 1
    fi
done

if grep -Eq '\$llvm_readelf"[[:space:]]+-hW?[[:space:]].*\|[[:space:]]*$' <<< "$validation" ||
   grep -Eq '\$llvm_readelf"[[:space:]]+-SW[[:space:]].*\|[[:space:]]*$' <<< "$validation"; then
    printf '%s\n' \
        'error: Clang validation still pipes llvm-readelf directly into a matcher under pipefail.' >&2
    exit 1
fi

grep -Fq '<<< "$smoke_header"' <<< "$validation"
grep -Fq '<<< "$smoke_sections"' <<< "$validation"
grep -Fq '<<< "$smoke64_header"' <<< "$validation"

printf 'PowerPC Clang validation pipefail policy: verified\n'
