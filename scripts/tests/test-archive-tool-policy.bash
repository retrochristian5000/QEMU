#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/whp-build/shell-functions.sh"

cc="${CC:-cc}"
ar_tool="${AR:-ar}"
ranlib_tool="${RANLIB:-ranlib}"

command -v "$cc" >/dev/null
command -v "$ar_tool" >/dev/null
command -v "$ranlib_tool" >/dev/null

tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-ar-policy.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# The platform-native archive family should satisfy the capability contract.
whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp"

# A wrapper is intentionally accepted: AR identity is a capability contract,
# not an exact pathname/vendor contract.
real_ar="$(command -v "$ar_tool")"
cat > "$tmp/ar-wrapper" <<EOF
#!/bin/sh
exec "$real_ar" "\$@"
EOF
chmod +x "$tmp/ar-wrapper"
whp_archive_toolchain_smoke "$cc" "$tmp/ar-wrapper" "$ranlib_tool" "$tmp"

# A broken wrapper must fail with a stage-specific diagnostic.
cat > "$tmp/ar-broken" <<'EOF'
#!/bin/sh
printf '%s\n' 'intentional archive failure' >&2
exit 23
EOF
chmod +x "$tmp/ar-broken"
if whp_archive_toolchain_smoke "$cc" "$tmp/ar-broken" "$ranlib_tool" "$tmp" \
    >"$tmp/broken.out" 2>&1; then
    printf '%s\n' 'error: broken AR wrapper passed the capability probe' >&2
    exit 1
fi
grep -Fq 'QEMU archive toolchain failed: create archive' "$tmp/broken.out"
grep -Fq 'intentional archive failure' "$tmp/broken.out"

printf 'archive tool portability tests: passed\n'
