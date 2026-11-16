#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The real root entry is safe for menuconfig --dump when source update
# is disabled. Avoid copying an incomplete bootstrap tree for this probe.
REAL_PYTHON="$(command -v python3)"
FAKEBIN="$TMP/fakebin"
mkdir -p "$FAKEBIN"

cat > "$FAKEBIN/uname" <<'EOF'
#!/bin/sh
case "${1:-}" in
    -s) printf '%s\n' 'MINGW64_NT-10.0-26100' ;;
    -m) printf '%s\n' 'x86_64' ;;
    *) printf '%s\n' 'MINGW64_NT-10.0-26100' ;;
esac
EOF

# Reproduce a common Windows installation shape: python/python3 aliases are
# present but unusable while the Windows Python launcher can locate the actual
# installed runtime.
for name in python3 python; do
    cat > "$FAKEBIN/$name" <<'EOF'
#!/bin/sh
exit 127
EOF
    chmod +x "$FAKEBIN/$name"
done

cat > "$FAKEBIN/py" <<EOF
#!/bin/sh
exec "$REAL_PYTHON" "\$@"
EOF
chmod +x "$FAKEBIN/uname" "$FAKEBIN/py"

menu_output="$(WHP_SOURCE_UPDATE=0 PATH="$FAKEBIN:$PATH" /bin/sh "$ROOT/build.sh" menuconfig --dump)"
grep -Fq 'WHP QEMU Configuration' <<< "$menu_output" || \
    grep -Fq 'Build outputs' <<< "$menu_output"

printf 'WHP Windows Python launcher discovery: verified\n'
