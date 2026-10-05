#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/scripts/whp-build" "$TMP/fakebin" "$TMP/build"
cp "$ROOT/build.sh" "$TMP/build.sh"

# Keep this fixture intentionally small, but provide the seed adapters and
# sourced bootstrap modules that build.sh must traverse before it can prove the
# bundled-Python fallback boundary.
cat > "$TMP/sed.sh" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --print-seed ]; then
    printf '/bin/sed\\n'
    exit 0
fi
exec /bin/sed "$@"
EOF
chmod +x "$TMP/sed.sh"

cat > "$TMP/cc.sh" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --print-cc ]; then
    printf '/usr/bin/cc\\n'
    exit 0
fi
exit 2
EOF
chmod +x "$TMP/cc.sh"

cat > "$TMP/scripts/whp-build/gnu-make.bash" <<'EOF'
whp_resolve_gnu_make()
{
    return 1
}

whp_find_gnu_make()
{
    return 1
}
EOF

cat > "$TMP/scripts/whp-build/host-tools.sh" <<'EOF'
# No managed host tools are needed for this fallback-boundary fixture.
EOF

cat > "$TMP/scripts/whp-build/host-libraries.sh" <<'EOF'
whp_prepare_qemu_host_libraries()
{
    :
}
EOF

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
    *config.py)
        # The shell probe only needs an empty configuration environment.
        exit 0
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
