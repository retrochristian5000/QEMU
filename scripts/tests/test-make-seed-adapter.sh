#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Test native GNU Make seed validation without building the managed Make fork.
set -eu
root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P)
seed="$root/seeds/make.sh"

test "$(/bin/sh "$seed" --whp-make-adapter-probe)" = whp-qemu-make-seed-adapter
selected=$(/bin/sh "$seed" --print-seed)
test -n "$selected"
test "$(/bin/sh "$seed" --check)" = "WHP native GNU Make seed: $selected"
test "$(/bin/sh "$seed" -s -f - whp-check <<'MAKEFILE'
whp-check:
	@printf 'native-make-ok\n'
MAKEFILE
)" = native-make-ok

if WHP_MAKE_SEED=/bin/false /bin/sh "$seed" --print-seed >/dev/null 2>&1; then
    printf '%s\n' 'error: invalid explicit GNU Make seed was accepted' >&2
    exit 1
fi
if WHP_MAKE_SEED="$seed" /bin/sh "$seed" --print-seed >/dev/null 2>&1; then
    printf '%s\n' 'error: recursive GNU Make adapter was accepted' >&2
    exit 1
fi

tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-make-seed.XXXXXX")
trap 'rm -rf -- "$tmp"' 0
cat > "$tmp/banner-only" <<'FAKE'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'GNU Make 99.0'
    exit 0
fi
exit 1
FAKE
chmod +x "$tmp/banner-only"
if WHP_MAKE_SEED="$tmp/banner-only" /bin/sh "$seed" --print-seed >/dev/null 2>&1; then
    printf '%s\n' 'error: banner-only GNU Make was accepted' >&2
    exit 1
fi
printf '%s\n' 'Native GNU Make seed selection and recipe execution: verified'
