#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Hermetic dedicated clang-cpp selection; no target compiler or LLVM build.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-clang-cpp.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

# A dedicated frontend may preprocess but need not compile or link.
native=$(/bin/sh "$root/seeds/cc.sh" --print-cc) || exit 1
mock="$tmp/clang-cpp"
cat > "$mock" <<'MOCK'
#!/bin/sh
case "${1:-}" in
    --version) printf 'clang-cpp test driver\n'; exit 0 ;;
esac
case " $* " in
    *' -E '*) exec "$WHP_TEST_NATIVE_CC" "$@" ;;
esac
printf '%s\n' 'error: clang-cpp was used without preprocessing mode' >&2
exit 1
MOCK
chmod +x "$mock"
export WHP_TEST_NATIVE_CC="$native"

selected=$(WHP_CLANG_CPP_SEED="$mock" /bin/sh "$root/seeds/clang-cpp.sh" --print-seed) || exit 1
[ "$selected" = "$mock" ]
WHP_CLANG_CPP_SEED="$mock" /bin/sh "$root/seeds/clang-cpp.sh" --check >/dev/null

# cpp.sh must accept preprocessing-only drivers without a native link test.
selected=$(WHP_CPP_SEED="$mock" /bin/sh "$root/seeds/cpp.sh" --print-seed) || exit 1
[ "$selected" = "$mock" ]
output=$(printf '#define WHP_CPP_DEDICATED 827\nWHP_CPP_DEDICATED\n' |
    WHP_CPP_SEED="$mock" WHP_CPP_LOCKED=1 \
    /bin/sh "$root/seeds/cpp.sh" -P -x c -) || exit 1
[ "$output" = 827 ]

# A broken explicit dedicated preprocessor must fail rather than fall back.
cat > "$mock" <<'BROKEN'
#!/bin/sh
if [ "${1:-}" = --version ]; then printf 'clang-cpp broken\n'; exit 0; fi
exit 1
BROKEN
chmod +x "$mock"
if WHP_CLANG_CPP_SEED="$mock" /bin/sh "$root/seeds/clang-cpp.sh" --print-seed \
    >"$tmp/bad.out" 2>"$tmp/bad.err"; then
    printf '%s\n' 'error: broken dedicated preprocessor passed admission' >&2
    exit 1
fi
[ ! -s "$tmp/bad.out" ]

printf '%s\n' 'WHP dedicated clang-cpp seed: verified'
