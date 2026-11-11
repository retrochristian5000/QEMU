#!/usr/bin/env bash
# Normalize Homebrew pkg-config output to upgrade-stable opt prefixes.
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

real_pkg_config="${WHP_REAL_PKG_CONFIG:-pkg-config}"
homebrew_prefix="${HOMEBREW_PREFIX:-}"

if [[ -z "$homebrew_prefix" ]] && command -v brew >/dev/null 2>&1; then
    homebrew_prefix="$(brew --prefix 2>/dev/null || true)"
fi

output="$("$real_pkg_config" "$@")"
if [[ -z "$output" ]]; then
    exit 0
fi

if [[ -z "$homebrew_prefix" ]]; then
    printf '%s\n' "$output"
    exit 0
fi

# Homebrew installs versioned kegs under Cellar but maintains /opt/<formula>
# as the stable symlink to the active keg, including keg-only formulae.
# Rewriting only Homebrew Cellar prefixes leaves system and custom paths alone.
printf '%s\n' "$output" | sed -E \
    "s#${homebrew_prefix}/Cellar/([^/[:space:]]+)/[^/[:space:]]+#${homebrew_prefix}/opt/\\1#g"
