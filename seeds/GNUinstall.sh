#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional GNU coreutils install; generic install.sh remains independent.
set -eu
marker=whp-qemu-gnu-install-seed-adapter
case "${1:-}" in
  --whp-gnu-install-adapter-probe|--whp-install-adapter-probe)
    printf '%s\n' "$marker"; exit 0 ;;
esac

# Locate this seed even if reached through a symlink.
entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
  depth=$((depth + 1))
  [ "$depth" -le 16 ] || { printf '%s\n' 'error: GNU install symlink loop' >&2; exit 1; }
  link=$(readlink "$entry") || exit 1
  case "$link" in
    /*) entry=$link ;;
    *) entry=$(dirname "$entry")/$link ;;
  esac
done
seed_dir=$(CDPATH= cd -P -- "$(dirname "$entry")" && pwd -P) || exit 1

gnu_install_resolve() (
  requested=$1
  [ -n "$requested" ] || exit 1
  case "$requested" in
    */*) candidate=$requested ;;
    *[[:space:]]*) exit 1 ;;
    *) candidate=$(command -v "$requested" 2>/dev/null) || exit 1 ;;
  esac
  [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
  case "$candidate" in
    /*) ;;
    */*) candidate=$(CDPATH= cd -P -- "$(dirname "$candidate")" && pwd -P)/$(basename "$candidate") || exit 1 ;;
    *) exit 1 ;;
  esac
  identity=$("$candidate" --whp-install-adapter-probe 2>/dev/null || true)
  case "$identity" in
    whp-qemu-install-seed-adapter|"$marker") exit 1 ;;
  esac
  identity=$("$candidate" --whp-gnu-install-adapter-probe 2>/dev/null || true)
  [ "$identity" != "$marker" ] || exit 1
  banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
  first=$(printf '%s\n' "$banner" | sed -n '1p')
  case "$first" in
    'install (GNU coreutils) '*|'ginstall (GNU coreutils) '*) ;;
    *) exit 1 ;;
  esac
  printf '%s\n' "$candidate"
)

gnu_install_probe() (
  candidate=$1
  # Reuse the native seed's directory, copy, mode and replacement checks.
  WHP_INSTALL_SEED="$candidate" WHP_INSTALL_LOCKED=0 \
    /bin/sh "$seed_dir/install.sh" --print-seed >/dev/null || exit 1
  tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-gnu-install.XXXXXX") || exit 1
  trap 'rm -rf -- "$tmp"' 0
  trap 'exit 1' 1 2 3 15
  printf '%s\n' whp-gnu-install > "$tmp/source"
  "$candidate" -D -m 0755 "$tmp/source" "$tmp/deep/bin/tool" >/dev/null 2>&1 || exit 1
  [ -x "$tmp/deep/bin/tool" ] || exit 1
  [ "$(cat "$tmp/deep/bin/tool")" = whp-gnu-install ] || exit 1
  "$candidate" --compare -m 0644 "$tmp/source" "$tmp/deep/bin/data" >/dev/null 2>&1 || exit 1
  [ -f "$tmp/deep/bin/data" ] && [ ! -x "$tmp/deep/bin/data" ] || exit 1
  [ "$(cat "$tmp/deep/bin/data")" = whp-gnu-install ] || exit 1
  "$candidate" --compare -m 0644 "$tmp/source" "$tmp/deep/bin/data" >/dev/null 2>&1 || exit 1
)

gnu_install_admit() {
  selected=$(gnu_install_resolve "$1") || return 1
  if [ "${probe:-yes}" = yes ]; then
    gnu_install_probe "$selected" || {
      printf 'error: GNU install functional probe failed: %s\n' "$selected" >&2
      return 1
    }
  fi
  printf '%s\n' "$selected"
}

gnu_install_select() {
  # Never inherit WHP_INSTALL_SEED or Autotools INSTALL.
  if [ -n "${WHP_GNU_INSTALL_SEED:-}" ]; then
    gnu_install_admit "$WHP_GNU_INSTALL_SEED" && return 0
    printf 'error: WHP_GNU_INSTALL_SEED is not a working GNU coreutils install: %s\n' \
      "$WHP_GNU_INSTALL_SEED" >&2
    return 1
  fi

  if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    provider=${WHP_MACOS_DEPENDENCY_PROVIDER:-auto}
    case "$provider" in
      homebrew|auto)
        if binary=$(/bin/sh "$seed_dir/brew.sh" --formula-bin coreutils ginstall 2>/dev/null); then
          gnu_install_admit "$binary" && return 0
        fi
        if [ "$provider" = homebrew ] ||
           [ -n "${HOMEBREW_PREFIX:-}${WHP_BREW_SEED:-}${WHP_HOMEBREW_BREW:-}" ]; then
          printf '%s\n' 'error: selected Homebrew has no usable coreutils ginstall' >&2
          return 1
        fi ;;
    esac
    case "$provider" in
      macports|auto)
        binary=${MACPORTS_PREFIX:-/opt/local}/bin/ginstall
        gnu_install_admit "$binary" && return 0
        if [ "$provider" = macports ]; then
          printf 'error: selected MacPorts has no usable GNU install: %s\n' "$binary" >&2
          return 1
        fi ;;
      system)
        for binary in /usr/bin/install /bin/install; do
          gnu_install_admit "$binary" && return 0
        done
        printf '%s\n' 'error: no GNU install in selected system provider' >&2
        return 1 ;;
    esac
  fi
  for binary in ginstall install /usr/bin/install; do
    gnu_install_admit "$binary" && return 0
  done
  printf '%s\n' 'error: no installed GNU coreutils install passed validation (optional seed)' >&2
  return 1
}

case "${1:-}" in
  --print-candidate) probe=no; gnu_install_select ;;
  --print-seed|--print-gnu-install) probe=yes; gnu_install_select ;;
  --check)
    probe=yes
    selected=$(gnu_install_select) || exit 1
    printf 'WHP GNU install seed: %s (GNU coreutils; native modes, -D and --compare verified)\n' "$selected" ;;
  *)
    # Do not repeat temporary-file probes for every forwarded invocation.
    probe=no
    selected=$(gnu_install_select) || exit 1
    exec "$selected" "$@" ;;
esac
