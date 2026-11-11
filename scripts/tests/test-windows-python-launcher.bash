#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COPY="$TMP/copy"
mkdir -p "$COPY/scripts/whp-config" "$COPY/scripts/whp-build"
cp "$ROOT/build.sh" "$COPY/build.sh"
cp "$ROOT/scripts/whp-config/config.py" "$COPY/scripts/whp-config/config.py"
cp "$ROOT/scripts/whp-config/menuconfig.py" "$COPY/scripts/whp-config/menuconfig.py"
cp "$ROOT/scripts/whp-build/portable-build.py" "$COPY/scripts/whp-build/portable-build.py"
cp "$ROOT/scripts/whp-build/portable-build-entry.py" \
   "$COPY/scripts/whp-build/portable-build-entry.py"

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

menu_output="$(PATH="$FAKEBIN:$PATH" /bin/sh "$COPY/build.sh" menuconfig --dump)"
grep -Fq 'WHP QEMU Configuration' <<< "$menu_output" || \
    grep -Fq 'Build outputs' <<< "$menu_output"

printf 'WHP Windows Python launcher discovery: verified\n'
