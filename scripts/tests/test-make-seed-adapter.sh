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

# Preserve GNU Make's bootstrap seed even when host-tools.sh promotes a newer
# Make. CMake invokes --print-make and must receive the promoted MAKE_CMD,
# rather than WHP_MAKE_SEED (which must remain suitable for Make->Make).
WHP_MAKE_TEST_BACKING=$selected
export WHP_MAKE_TEST_BACKING
for stage in bootstrap promoted; do
    cat > "$tmp/$stage-make" <<'WRAPPER'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf 'GNU Make %s\n' "${0##*/}"
    exit 0
fi
exec "$WHP_MAKE_TEST_BACKING" "$@"
WRAPPER
    chmod +x "$tmp/$stage-make"
done
bootstrap_make="$tmp/bootstrap-make"
promoted_make="$tmp/promoted-make"
selected_seed=$(WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD="$promoted_make" \
    MAKE="$promoted_make" /bin/sh "$seed" --print-seed)
test "$selected_seed" = "$bootstrap_make"
selected_active=$(WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD="$promoted_make" \
    MAKE="$promoted_make" /bin/sh "$seed" --print-make)
test "$selected_active" = "$promoted_make"
# Make's regular exec path must agree with the CMake-facing active selector.
make_output=$(WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD="$promoted_make" \
    MAKE="$promoted_make" /bin/sh "$seed" --version)
test "$make_output" = 'GNU Make promoted-make'
# An explicit broken promoted Make must not silently fall back to the seed.
if WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD=/bin/false \
    /bin/sh "$seed" --print-make > "$tmp/active-out" 2> "$tmp/active-error"; then
    printf '%s\n' 'error: invalid active GNU Make was accepted' >&2
    exit 1
fi
test ! -s "$tmp/active-out"
grep -Fq 'invalid active GNU Make MAKE_CMD' "$tmp/active-error"
test "$(WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD=/bin/false \
    /bin/sh "$seed" --print-seed)" = "$bootstrap_make"
# Without a promoted command, --print-make may still use the original seed.
test "$(WHP_MAKE_SEED="$bootstrap_make" MAKE_CMD= MAKE= \
    /bin/sh "$seed" --print-make)" = "$bootstrap_make"

# CMake's source bootstrap expects MAKE to build and execute a native C test.
cat > "$tmp/Makefile" <<'MAKEFILE'
cmake-make-check: cmake-make-check.c
	$(CC) cmake-make-check.c -o cmake-make-check
MAKEFILE
cat > "$tmp/cmake-make-check.c" <<'CSOURCE'
#include <stdio.h>
int main(void) { printf("cmake-make-accepted\n"); return 0; }
CSOURCE
(
    cd "$tmp"
    # Use the exact executable returned to ensure-cmake.py by --print-make.
    "$selected_active" -j 2 CC="${CC_FOR_BUILD:-cc}" cmake-make-check >/dev/null
    test "$(./cmake-make-check)" = cmake-make-accepted
)
printf '%s\n' 'Native GNU Make seed, promotion and CMake handoff: verified'
