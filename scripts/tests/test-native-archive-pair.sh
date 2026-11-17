#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native LLVM archive provider wiring, without rebuilding LLVM or fetching data.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
selector="$root/scripts/whp-build/native-archive-pair.sh"
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-archive-pair.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

unset WHP_AR_SEED AR_FOR_BUILD WHP_RANLIB_SEED RANLIB_FOR_BUILD
unset WHP_GNU_AR_SEED WHP_LLVM_AR_SEED WHP_LLVM_RANLIB_SEED
unset WHP_NATIVE_LLVM_ARCHIVE_PROVIDER
real_cc=$(/bin/sh "$root/seeds/cc.sh" --print-seed)
real_ar=$(/bin/sh "$root/seeds/ar.sh" --print-seed)
real_ranlib=$(WHP_AR_SEED="$real_ar" /bin/sh "$root/seeds/ranlib.sh" --print-seed)

# Native is the exact existing generic pair and remains supported without
# detecting a GNU or LLVM executable on the runner.
native=$(WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=native /bin/sh "$selector" "$real_cc" \
    2>"$tmp/native.err") || exit 1
[ "$native" = "$(printf '%s\n%s' "$real_ar" "$real_ranlib")" ]
grep -Fq 'provider: native' "$tmp/native.err"

# Unknown compilers do not trigger arbitrary preference or source bootstraps.
cat > "$tmp/unknown-cc" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'Some other compiler 1.0'
    exit 0
fi
exit 12
SH
chmod +x "$tmp/unknown-cc"
[ "$(/bin/sh "$selector" "$tmp/unknown-cc" 2>"$tmp/unknown.err")" = "$native" ]

# On any POSIX runner, model a GNU-labelled *native-capable* pair using
# wrappers around its tested native tools. Version identity alone is not
# enough: both archive admission probes still run.
mkdir "$tmp/gnu"
cat > "$tmp/gnu/ar" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'GNU ar (GNU Binutils) 2.44'
    exit 0
fi
exec "$WHP_TEST_NATIVE_AR" "$@"
SH
cat > "$tmp/gnu/ranlib" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' "GNU ranlib (GNU Binutils) ${WHP_TEST_RANLIB_VERSION:-2.44}"
    exit 0
fi
exec "$WHP_TEST_NATIVE_RANLIB" "$@"
SH
chmod +x "$tmp/gnu/ar" "$tmp/gnu/ranlib"
export WHP_TEST_NATIVE_AR="$real_ar"
export WHP_TEST_NATIVE_RANLIB="$real_ranlib"

gnu=$(WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=gnu \
    WHP_GNU_AR_SEED="$tmp/gnu/ar" /bin/sh "$selector" "$real_cc" \
    2>"$tmp/gnu.err") || exit 1
[ "$gnu" = "$(printf '%s\n%s' "$tmp/gnu/ar" "$tmp/gnu/ranlib")" ]
grep -Fq 'provider: gnu' "$tmp/gnu.err"

# In auto, an explicit specialized request must not be hidden by generic ar.
[ "$(WHP_GNU_AR_SEED="$tmp/gnu/ar" /bin/sh "$selector" "$real_cc" \
    2>"$tmp/gnu-auto.err")" = "$gnu" ]
grep -Fq 'provider: gnu' "$tmp/gnu-auto.err"

# A GCC-compatible bootstrap must prefer the specialist automatically even
# when no specialized override was supplied. The fixture is first on PATH,
# but admission still validates its actual archive and index operations.
cat > "$tmp/gcc-version" <<'SH'
#!/bin/sh
[ "${1:-}" = --version ] || exit 1
printf '%s\n' 'gcc (GCC) 14.2.0'
SH
chmod +x "$tmp/gcc-version"
automatic_gnu=$(PATH="$tmp/gnu:$PATH" /bin/sh "$selector" "$tmp/gcc-version" \
    2>"$tmp/gcc-auto.err") || exit 1
grep -Fq 'provider: gnu' "$tmp/gcc-auto.err"
case "$automatic_gnu" in
    *"$tmp/gnu/ar"*) ;;
    *)
        # A valid installed GNU Binutils pair may precede PATH on macOS.
        [ -x "${automatic_gnu%%'
'*}" ] || exit 1 ;;
esac

# Different Binutils releases are rejected even if both tools can index
# an ordinary native object; a forced provider must never fall back.
if WHP_TEST_RANLIB_VERSION=2.45 \
   WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=gnu WHP_GNU_AR_SEED="$tmp/gnu/ar" \
   /bin/sh "$selector" "$real_cc" >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: mixed GNU Binutils versions were accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'GNU ar/ranlib releases disagree' "$tmp/err"

# An invalid explicit specialist request is a hard error, not an implicit
# generic provider selection.
if WHP_GNU_AR_SEED="$tmp/missing" /bin/sh "$selector" "$real_cc" \
    >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: missing explicit GNU provider fell back to native' >&2
    exit 1
fi
grep -Fq 'required GNU archive/indexer pair failed admission' "$tmp/err"

if WHP_GNU_AR_SEED="$tmp/gnu/ar" WHP_AR_SEED="$real_ar" \
    /bin/sh "$selector" "$real_cc" >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: conflicting generic/specialized archive seeds were accepted' >&2
    exit 1
fi
grep -Fq 'generic and specialized archive overrides conflict' "$tmp/err"

if WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=bad /bin/sh "$selector" "$real_cc" \
    >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: invalid archive provider was accepted' >&2
    exit 1
fi
grep -Fq 'invalid WHP_NATIVE_LLVM_ARCHIVE_PROVIDER' "$tmp/err"

# A symlinked entrypoint must find the original checkout's seeds.
ln -s "$selector" "$tmp/selector-link"
[ "$(WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=native \
    /bin/sh "$tmp/selector-link" "$real_cc" 2>"$tmp/link.err")" = "$native" ]

# On a real installed LLVM pair, the forced specialized branch must work;
# if no coherent pair is installed, forcing LLVM must reject it instead.
if llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed 2>/dev/null) &&
   llvm_ranlib=$(WHP_LLVM_AR_SEED="$llvm_ar" \
       /bin/sh "$root/seeds/llvm-ranlib.sh" --print-seed 2>/dev/null); then
    pair=$(WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=llvm WHP_LLVM_AR_SEED="$llvm_ar" \
        /bin/sh "$selector" "$real_cc" 2>"$tmp/llvm.err") || exit 1
    [ "$pair" = "$(printf '%s\n%s' "$llvm_ar" "$llvm_ranlib")" ]
    grep -Fq 'provider: llvm' "$tmp/llvm.err"
else
    if WHP_NATIVE_LLVM_ARCHIVE_PROVIDER=llvm /bin/sh "$selector" "$real_cc" \
        >"$tmp/out" 2>"$tmp/err"; then
        printf '%s\n' 'error: unavailable LLVM archive pair was accepted' >&2
        exit 1
    fi
    grep -Fq 'required LLVM archive/indexer pair failed admission' "$tmp/err"
fi

printf '%s\n' 'native LLVM archive provider selection: PASS'
