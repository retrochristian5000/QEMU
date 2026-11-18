#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an existing native Perl for the pre-Autotools bootstrap.
# Perl is a root dependency, not a tool that this adapter builds.
set -eu

# Isolate the native Perl seed from local modules and injected startup code.
# This only modifies the adapter child, not its calling shell.
unset PERL5LIB PERLLIB PERL5OPT PERL5DB PERL_LOCAL_LIB_ROOT PERL_MM_OPT PERL_MB_OPT

marker=whp-qemu-perl-seed-adapter
if [ "${1:-}" = --whp-perl-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

perl_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        *[[:space:]]*) exit 1 ;;
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-perl-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1

    # Version and execution, not a plausible --version banner: the Automake
    # maintainer tree requires Perl >= 5.6 and uses core strict/warnings.
    result=$("$candidate" -e 'use 5.006; use strict; use warnings; print "whp-perl-ok\n";' 2>/dev/null) || exit 1
    [ "$result" = whp-perl-ok ] || exit 1

    printf '%s\n' "$candidate"
)

# Autoconf/autom4te and Automake/aclocal load more than strict/warnings.
# Keep this second, consumer-specific check outside the root --print-seed path:
# Perl's own source bootstrap must remain independent of Autotools modules.
perl_check_autotools()
(
    candidate=$1
    result=$("$candidate" -e '
        use 5.006;
        use strict;
        use warnings;
        use Config;

        # Modules imported by the pinned Autoconf and Automake scripts.
        for my $module (qw(
            Carp Class::Struct Cwd Data::Dumper Errno Exporter Fcntl
            File::Basename File::Compare File::Copy File::Find File::Path
            File::Spec File::Temp File::stat Getopt::Long IO::File POSIX
            Text::ParseWords constant
        )) {
            (my $filename = $module) =~ s{::}{/}g;
            $filename .= ".pm";
            eval { require $filename; 1 } or
                die "WHP Autotools Perl module $module: $@";
        }

        # Automake loads these when Perl Config enables its threaded mode.
        # Non-threaded Perl must not be rejected for lacking them.
        if ($Config::Config{useithreads}) {
            for my $module (qw(threads Thread::Queue)) {
                (my $filename = $module) =~ s{::}{/}g;
                $filename .= ".pm";
                eval { require $filename; 1 } or
                    die "WHP threaded Autotools Perl module $module: $@";
            }
        }
        print "whp-perl-autotools-ok\n";
    ' 2>&1) || {
        printf 'error: Autotools Perl module preflight failed: %s\n%s\n' \
            "$candidate" "$result" >&2
        exit 1
    }
    [ "$result" = whp-perl-autotools-ok ] || {
        printf 'error: unexpected Autotools Perl module result: %s: %s\n' \
            "$candidate" "$result" >&2
        exit 1
    }
)

perl_select()
{
    # An explicit choice is authoritative. Do not fall back to PATH when it
    # is absent, malformed, too old, or is this adapter.
    for variable in WHP_PERL_SEED PERL; do
        case "$variable" in
            WHP_PERL_SEED) requested=${WHP_PERL_SEED:-} ;;
            PERL) requested=${PERL:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(perl_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not select usable Perl >= 5.6: %s\n' "$variable" "$requested" >&2
        return 1
    done

    for candidate in perl /usr/bin/perl; do
        if selected=$(perl_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable native Perl >= 5.6 for Autotools bootstrap' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-perl) perl_select ;;
    --print-autotools-seed)
        selected=$(perl_select) || exit 1
        perl_check_autotools "$selected" || exit 1
        printf '%s\n' "$selected" ;;
    --check)
        selected=$(perl_select) || exit 1
        printf 'WHP Perl seed: %s\n' "$selected" ;;
    *)
        selected=$(perl_select) || exit 1
        exec "$selected" "$@" ;;
esac
