#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/whp-build/shell-functions.sh"

cc="${CC:-cc}"
ar_tool="${AR:-ar}"
ranlib_tool="${RANLIB:-ranlib}"
nm_tool="${NM:-nm}"

command -v "$cc" >/dev/null
command -v "$ar_tool" >/dev/null
command -v "$ranlib_tool" >/dev/null
command -v "$nm_tool" >/dev/null

tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-ar-policy.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# Required tool roles must fail early and name the missing variable.
assert_missing_role()
{
    role=$1
    shift
    if whp_archive_toolchain_smoke "$@" >"$tmp/missing-role.log" 2>&1; then
        printf 'error: empty %s tool name was accepted\n' "$role" >&2
        exit 1
    fi
    grep -Fq "nonempty $role executable" "$tmp/missing-role.log"
}
assert_missing_role CC "" "$ar_tool" "$ranlib_tool" "$tmp" "$nm_tool"
assert_missing_role AR "$cc" "" "$ranlib_tool" "$tmp" "$nm_tool"
assert_missing_role RANLIB "$cc" "$ar_tool" "" "$tmp" "$nm_tool"
assert_missing_role NM "$cc" "$ar_tool" "$ranlib_tool" "$tmp" ""

# Historical four-argument archive-only callers remain supported.
whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp"

# The shared Libtool marker parser must reject missing, ambiguous, malformed,
# relative, and non-executable tool paths without erasing valid selections.
marker="$tmp/libtool-marker"
tool_path="$(command -v "$ar_tool")"
printf 'AR=%s|version unavailable\nARFLAGS=cr\n' "$tool_path" >"$marker"
test "$(whp_marker_required_tool "$marker" AR)" = "$tool_path"
test "$(whp_marker_required_value "$marker" ARFLAGS)" = cr

reject_marker()
{
    expected=$1
    if whp_marker_required_tool "$marker" AR >"$tmp/marker.out" 2>"$tmp/marker.err"; then
        printf 'error: invalid Libtool marker was accepted: %s\n' "$expected" >&2
        exit 1
    fi
    grep -Fq "$expected" "$tmp/marker.err"
}
: >"$marker"
reject_marker 'exactly one AR tool name (found 0)'
printf 'AR=|unknown\n' >"$marker"
reject_marker 'empty AR tool name'
printf 'AR=%s\n' "$tool_path" >"$marker"
reject_marker 'malformed AR tool identity'
printf 'AR=relative/ar|unknown\n' >"$marker"
reject_marker 'AR tool path is not absolute'
printf 'AR=%s|one\nAR=%s|two\n' "$tool_path" "$tool_path" >"$marker"
reject_marker 'exactly one AR tool name (found 2)'
printf 'AR=%s/missing-executable|unknown\n' "$tmp" >"$marker"
reject_marker 'AR tool is not executable'
printf 'AR=%s|version unavailable\nARFLAGS=\n' "$tool_path" >"$marker"
if whp_marker_required_value "$marker" ARFLAGS >"$tmp/flags.out" 2>"$tmp/flags.err"; then
    printf 'error: empty ARFLAGS marker value was accepted\n' >&2
    exit 1
fi
grep -Fq 'one nonempty ARFLAGS value' "$tmp/flags.err"

# The platform-native archive family should satisfy the capability contract.
whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp" "$nm_tool"

# A wrapper is intentionally accepted: AR identity is a capability contract,
# not an exact pathname/vendor contract.
real_ar="$(command -v "$ar_tool")"
cat > "$tmp/ar-wrapper" <<EOF
#!/bin/sh
exec "$real_ar" "\$@"
EOF
chmod +x "$tmp/ar-wrapper"
whp_archive_toolchain_smoke "$cc" "$tmp/ar-wrapper" "$ranlib_tool" "$tmp" "$nm_tool"

# RANLIB and NM wrappers are also judged by capability, not pathname.
real_ranlib="$(command -v "$ranlib_tool")"
cat > "$tmp/ranlib-wrapper" <<EOF
#!/bin/sh
exec "$real_ranlib" "\$@"
EOF
chmod +x "$tmp/ranlib-wrapper"
whp_archive_toolchain_smoke "$cc" "$ar_tool" "$tmp/ranlib-wrapper" "$tmp" "$nm_tool"

real_nm="$(command -v "$nm_tool")"
cat > "$tmp/nm-wrapper" <<EOF
#!/bin/sh
exec "$real_nm" "\$@"
EOF
chmod +x "$tmp/nm-wrapper"
whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp" "$tmp/nm-wrapper"

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

cat > "$tmp/ranlib-broken" <<'EOF'
#!/bin/sh
printf '%s\n' 'intentional ranlib failure' >&2
exit 24
EOF
chmod +x "$tmp/ranlib-broken"
if whp_archive_toolchain_smoke "$cc" "$ar_tool" "$tmp/ranlib-broken" "$tmp" "$nm_tool" \
    >"$tmp/broken-ranlib.out" 2>&1; then
    printf '%s\n' 'error: broken RANLIB wrapper passed the capability probe' >&2
    exit 1
fi
grep -Fq 'QEMU archive toolchain failed: index archive' "$tmp/broken-ranlib.out"

cat > "$tmp/nm-broken" <<'EOF'
#!/bin/sh
printf '%s\n' 'intentional nm failure' >&2
exit 25
EOF
chmod +x "$tmp/nm-broken"
if whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp" "$tmp/nm-broken" \
    >"$tmp/broken-nm.out" 2>&1; then
    printf '%s\n' 'error: broken NM wrapper passed the capability probe' >&2
    exit 1
fi
grep -Fq 'QEMU archive toolchain failed: inspect archive symbols' "$tmp/broken-nm.out"

# Exit status alone is insufficient: an NM that returns no symbols, or merely
# undefined symbols, must not pass the archive symbol-reader contract.
cat > "$tmp/nm-empty" <<'EOF'
#!/bin/sh
printf '%s\n' 'whp_archive_probe U'
EOF
chmod +x "$tmp/nm-empty"
if whp_archive_toolchain_smoke "$cc" "$ar_tool" "$ranlib_tool" "$tmp" "$tmp/nm-empty" \
    >"$tmp/empty-nm.out" 2>&1; then
    printf '%s\n' 'error: NM without a defined symbol passed the capability probe' >&2
    exit 1
fi
grep -Fq 'QEMU archive toolchain failed: verify archive symbols' "$tmp/empty-nm.out"

printf 'archive tool portability tests: passed\n'
