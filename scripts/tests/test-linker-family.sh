#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Distinguish GNU BFD/gold, ELF LLD, Mach-O LLD, and Apple ld without
# replacing any selected host linker or changing global developer tools.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/ld.sh
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-linker-family.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

selected=$(/bin/sh "$seed" --print-ld) || exit 1
[ -x "$selected" ] || exit 1
check=$(WHP_LD_SEED="$selected" /bin/sh "$seed" --check) || exit 1
case "$check" in
    "WHP native linker seed: $selected (family: "*')') ;;
    *) printf 'error: linker check omitted family: %s\n' "$check" >&2; exit 1 ;;
esac
[ "$(WHP_LD_SEED="$selected" /bin/sh "$seed" --print-ld)" = "$selected" ]

# Each fixture delegates actual relocatable links to the validated host ld.
# Only version, flavor and help text are simulated: strings are diagnostic,
# and actual ability to link a native object remains mandatory.
cat > "$tmp/driver" <<'EOF'
#!/bin/sh
case "${0##*/}" in
    fake-gnu-bfd) flavour=gnu-bfd ;;
    fake-gnu-gold) flavour=gnu-gold ;;
    fake-llvm-elf|fake-llvm-ignored|fake-llvm-supported) flavour=llvm-elf ;;
    ld64.lld) flavour=llvm-macho ;;
    fake-apple) flavour=apple-macho ;;
    *) flavour=unknown ;;
esac
case "${1:-}" in
    --version)
        case "$flavour" in
            gnu-bfd) printf 'GNU ld (GNU Binutils) 2.44\n' ;;
            gnu-gold) printf 'GNU gold (GNU Binutils) 2.44\n' ;;
            llvm-*) printf 'LLD 22.0.0 (compatible with GNU linkers)\n' ;;
            apple-macho) exit 1 ;;
            *) printf 'vendor linker 1.0\n' ;;
        esac
        exit 0 ;;
    -v)
        if [ "$flavour" = apple-macho ]; then
            printf '@(#)PROGRAM:ld PROJECT:ld-1115.7.3\n' >&2
            exit 0
        fi
        printf 'other linker\n'
        exit 0 ;;
    --help)
        case "${0##*/}" in
            fake-llvm-ignored)
                printf '  --plugin=<value> Ignored for compatibility with GNU linkers\n'
                ;;
            fake-llvm-supported)
                printf '  --plugin=<value> Use a plugin in the linking process\n'
                ;;
            *) printf 'linker help\n' ;;
        esac
        exit 0 ;;
esac
if [ -n "${WHP_TEST_LD_CAPTURE:-}" ]; then
    printf '%s\n' "$@" > "$WHP_TEST_LD_CAPTURE"
    exit 0
fi
exec "$WHP_TEST_REAL_LD" "$@"
EOF
chmod +x "$tmp/driver"
for name in fake-gnu-bfd fake-gnu-gold fake-llvm-elf fake-llvm-ignored \
    fake-llvm-supported ld64.lld fake-apple fake-unknown; do
    cp "$tmp/driver" "$tmp/$name"
done
export WHP_TEST_REAL_LD="$selected"

for entry in \
    fake-gnu-bfd:gnu-bfd \
    fake-gnu-gold:gnu-gold \
    fake-llvm-elf:llvm-elf \
    ld64.lld:llvm-macho \
    fake-apple:apple-macho \
    fake-unknown:unknown; do
    name=${entry%%:*}
    expected=${entry#*:}
    actual=$(WHP_LD_SEED="$tmp/$name" /bin/sh "$seed" --check) || {
        printf 'error: simulated %s native relocatable linker failed\n' "$name" >&2
        exit 1
    }
    [ "$actual" = "WHP native linker seed: $tmp/$name (family: $expected)" ] || {
        printf 'error: linker family mismatch: wanted %s; received %s\n' "$expected" "$actual" >&2
        exit 1
    }
done

# Build-machine overrides must not silently override one another.
WHP_LD_SEED="$selected" LD_FOR_BUILD="$tmp/fake-gnu-bfd" \
    /bin/sh "$seed" --print-ld >"$tmp/selection.out" 2>"$tmp/selection.err"
[ "$(cat "$tmp/selection.out")" = "$selected" ]
grep -Fq 'WHP_LD_SEED overrides conflicting LD_FOR_BUILD' "$tmp/selection.err"

# Older ELF LLD ignores GNU LTO plugin requests; fail rather than appear to
# load one. Test both spellings with and without an =value.
for option in --plugin=/tmp/missing-plugin.so -plugin=/tmp/missing-plugin.so \
    --plugin -plugin; do
    if WHP_LD_SEED="$tmp/fake-llvm-ignored" \
        WHP_TEST_LD_CAPTURE="$tmp/forwarded" \
        /bin/sh "$seed" "$option" "$tmp/object.o" \
            >"$tmp/ignored.out" 2>"$tmp/ignored.err"; then
        printf 'error: ignored LLVM plugin was accepted: %s\n' "$option" >&2
        exit 1
    fi
    [ ! -s "$tmp/ignored.out" ]
    grep -Fq 'LLVM ELF linker ignores GNU -plugin option' "$tmp/ignored.err"
done

# Do not overblock LLD versions which explicitly support the plugin, or
# GNU BFD which can handle the option itself. Preserve argument order.
for name in fake-llvm-supported fake-gnu-bfd; do
    WHP_LD_SEED="$tmp/$name" WHP_TEST_LD_CAPTURE="$tmp/forwarded" \
        /bin/sh "$seed" --plugin=/tmp/plugin.so "$tmp/object.o"
    [ "$(cat "$tmp/forwarded")" = \
        "$(printf '%s\n' '--plugin=/tmp/plugin.so' "$tmp/object.o")" ] || {
        printf 'error: plugin option was not forwarded for %s\n' "$name" >&2
        exit 1
    }
done

printf '%s\n' 'WHP GNU/LLVM/Apple native linker family diagnostics: verified'
