#!/usr/bin/env bash
# Regression: macOS external Homebrew prefixes are flexible; ABI boundaries
# and explicit manager selection remain authoritative.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="$ROOT"
source "$ROOT/scripts/whp-build/prepare-build.bash"
source "$ROOT/scripts/macos-build-hygiene.bash"

# Conventional same-arch, and nonconventional custom prefixes are accepted.
whp_validate_homebrew_prefix_for_arch /opt/homebrew arm64 0
whp_validate_homebrew_prefix_for_arch /usr/local x86_64 0
whp_validate_homebrew_prefix_for_arch "/Volumes/External Drive/brew" arm64 0
whp_validate_homebrew_prefix_for_arch /srv/homebrew x86_64 0

# Opposite architecture defaults must not become an implicit provider.
if whp_validate_homebrew_prefix_for_arch /usr/local arm64 0 2>/dev/null; then
    printf '%s\n' 'error: arm64 admitted the Intel conventional Homebrew prefix' >&2
    exit 1
fi
if whp_validate_homebrew_prefix_for_arch /opt/homebrew x86_64 0 2>/dev/null; then
    printf '%s\n' 'error: x86_64 admitted the Apple Silicon conventional Homebrew prefix' >&2
    exit 1
fi
whp_validate_homebrew_prefix_for_arch /usr/local arm64 1
whp_validate_homebrew_prefix_for_arch /opt/homebrew x86_64 1
if whp_validate_homebrew_prefix_for_arch relative/homebrew arm64 0 2>/dev/null; then
    printf '%s\n' 'error: a relative Homebrew prefix was admitted' >&2
    exit 1
fi

# Use a deliberately synthetic arm64 hostname. The test is runnable under
# Linux CI and on native macOS without changing or installing any tool.
(
    uname() {
        case "${1:-}" in
            -m) printf 'arm64\n' ;;
            -s) printf 'Darwin\n' ;;
            *) command uname "$@" ;;
        esac
    }
    HOMEBREW_PREFIX="/Volumes/External Drive/brew"
    WHP_BREW_SEED="/Volumes/External Drive/brew/bin/brew"
    WHP_MACOS_DEPENDENCY_PROVIDER=homebrew
    PATH=/usr/bin:/bin
    sanitize_macos_build_environment
    [[ "$HOMEBREW_PREFIX" == "/Volumes/External Drive/brew" ]]
    [[ "$WHP_BREW_SEED" == "/Volumes/External Drive/brew/bin/brew" ]]
)
(
    uname() {
        case "${1:-}" in
            -m) printf 'arm64\n' ;;
            *) command uname "$@" ;;
        esac
    }
    HOMEBREW_PREFIX=/usr/local
    WHP_MACOS_DEPENDENCY_PROVIDER=auto
    PATH=/usr/bin:/bin
    sanitize_macos_build_environment
    # Hygiene may remove opposite-arch PATH entries, but must not hide the
    # explicitly requested incompatible prefix from the validation layer.
    [[ "$HOMEBREW_PREFIX" == /usr/local ]]
)
printf '%s\n' 'macOS custom Homebrew prefix and provider isolation: PASS'
