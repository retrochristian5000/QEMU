#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/whp-zsh-entry.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

FAKE_BIN="$TMP/bin"
ZSH_LOG="$TMP/zsh.log"
mkdir -p "$FAKE_BIN"

cat > "$FAKE_BIN/uname" <<'EOF'
#!/bin/sh
case "${1:-}" in
    -s) printf 'Darwin\n' ;;
    -m) printf 'arm64\n' ;;
    *) printf 'Darwin\n' ;;
esac
EOF

cat > "$FAKE_BIN/zsh" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$TEST_ZSH_LOG"
if [ "${1:-}" = -f ] && [ "${2:-}" = -c ]; then
    ZSH_VERSION=5.9
    export ZSH_VERSION
    exec /bin/sh -c "$3"
fi
printf 'error: zsh entry was not started with -f\n' >&2
exit 1
EOF
chmod +x "$FAKE_BIN/uname" "$FAKE_BIN/zsh"

run_probe()
{
    local shell_policy="$1"
    PATH="$FAKE_BIN:$PATH" \
    TEST_ZSH_LOG="$ZSH_LOG" \
    WHP_BUILD_SHELL="$shell_policy" \
    WHP_SHELL_PROBE_ONLY=1 \
    /bin/sh "$ROOT/build.sh"
}

: > "$ZSH_LOG"
zsh_probe="$(run_probe zsh)"
grep -Fq 'WHP orchestration shell: zsh' <<< "$zsh_probe"
grep -Fq 'WHP build shell:' <<< "$zsh_probe"
grep -Fq 'CONFIG_SHELL: /bin/bash' <<< "$zsh_probe"
grep -Fq -- '-f -c' "$ZSH_LOG"

: > "$ZSH_LOG"
auto_probe="$(run_probe auto)"
grep -Fq 'WHP orchestration shell: zsh' <<< "$auto_probe"
grep -Fq -- '-f -c' "$ZSH_LOG"

: > "$ZSH_LOG"
bash_probe="$(run_probe bash)"
grep -Fq 'WHP orchestration shell: bash' <<< "$bash_probe"
grep -Fq 'CONFIG_SHELL: /bin/bash' <<< "$bash_probe"
[[ ! -s "$ZSH_LOG" ]]

portable_probe="$(run_probe portable)"
grep -Fq 'portable Python core' <<< "$portable_probe"

invalid_output="$TMP/invalid-output"
if run_probe fish >"$invalid_output" 2>&1; then
    printf 'error: invalid WHP_BUILD_SHELL value was accepted\n' >&2
    exit 1
fi
grep -Fq 'WHP_BUILD_SHELL must be auto, bash, zsh, or portable' "$invalid_output"

printf 'macOS zsh entry policy: verified\n'
