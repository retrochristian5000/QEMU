#!/bin/sh -e
#
# Helper script for the build process to apply entitlements

in_place=:
if [ "$1" = --install ]; then
  shift
  in_place=false
fi

DST="$1"
SRC="$2"
ICON="$3"
ENTITLEMENT="$4"

if $in_place; then
  trap 'rm -f "$DST.tmp"' exit
  cp -pPf "$SRC" "$DST.tmp"
  SRC="$DST.tmp"
else
  cd "$MESON_INSTALL_DESTDIR_PREFIX"
fi

# Rez and SetFile are legacy Xcode utilities and are not present in every
# Command Line Tools installation. Missing icon metadata must not prevent the
# actual emulator binary from being produced.
if command -v Rez >/dev/null 2>&1 && command -v SetFile >/dev/null 2>&1; then
  Rez -append "$ICON" -o "$SRC"
  SetFile -a C "$SRC"
else
  echo "warning: Rez/SetFile unavailable; skipping legacy QEMU icon metadata" >&2
fi

if test -n "$ENTITLEMENT"; then
  if ! command -v codesign >/dev/null 2>&1; then
    echo "error: codesign is required to apply QEMU entitlements" >&2
    exit 1
  fi
  codesign --entitlements "$ENTITLEMENT" --force -s - "$SRC"
  codesign --verify --strict "$SRC"
fi

mv -f "$SRC" "$DST"
trap '' exit
