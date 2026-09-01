#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/scripts" "$TMP/fakebin" "$TMP/build"
cp "$ROOT/build.sh" "$TMP/build.sh"

cat > "$TMP/fake-python" <<'EOF'
#!/bin/sh
case "${1:-}" in
    -c)
        exit 0
        ;;
    *portable-build-entry.py)
        if [ "${2:-}" = --print-build-dir ]; then
            printf '%s\n' "$WHP_TEST_BUILD_DIR"
            exit 0
        fi
        ;;
esac
exit 2
EOF
chmod +x "$TMP/fake-python"

cat > "$TMP/scripts/bootstrap-python.sh" <<'EOF'
#!/bin/sh
set -eu
: > "$WHP_TEST_BOOTSTRAP_MARKER"
printf '%s\n' "$WHP_TEST_FAKE_PYTHON"
EOF
chmod +x "$TMP/scripts/bootstrap-python.sh"

cat > "$TMP/fakebin/uname" <<'EOF'
#!/bin/sh
case "${1:-}" in
    -s) printf 'Linux\n' ;;
    -m) printf 'x86_64\n' ;;
    *) printf 'Linux\n' ;;
esac
EOF
chmod +x "$TMP/fakebin/uname"
ln -s "$(command -v dirname)" "$TMP/fakebin/dirname"

marker="$TMP/python-bootstrap.called"
output="$({
    /usr/bin/env -i \
        PATH="$TMP/fakebin" \
        HOME="$TMP" \
        WHP_BUILD_BASH=/bin/bash \
        WHP_SHELL_PROBE_ONLY=1 \
        WHP_TEST_BUILD_DIR="$TMP/build" \
        WHP_TEST_BOOTSTRAP_MARKER="$marker" \
        WHP_TEST_FAKE_PYTHON="$TMP/fake-python" \
        /bin/sh "$TMP/build.sh"
} 2>&1)" || {
    printf '%s\n' "$output" >&2
    printf 'error: public build entry did not fall back to bundled Python\n' >&2
    exit 1
}

[[ -f "$marker" ]] || {
    printf 'error: bundled Python bootstrap helper was not called\n' >&2
    exit 1
}
grep -Fq 'WHP build shell:' <<< "$output"

printf 'bundled Python fallback test: passed\n'
