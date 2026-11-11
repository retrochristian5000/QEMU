# GNU Make discovery shared by WHP bootstrap and artifact build paths.
# The implementation is POSIX-sh compatible because build.sh needs it before
# GNU Bash is guaranteed to be available.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_resolve_gnu_make()
(
    whp_make_requested=${1:-}
    [ -n "$whp_make_requested" ] || return 1

    case "$whp_make_requested" in
        */*) whp_make_resolved=$whp_make_requested ;;
        *)
            whp_make_resolved=$(command -v "$whp_make_requested" 2>/dev/null || true)
            ;;
    esac
    [ -n "$whp_make_resolved" ] && [ -x "$whp_make_resolved" ] || return 1

    whp_make_version=$(LC_ALL=C "$whp_make_resolved" --version 2>/dev/null || true)
    case "$whp_make_version" in
        "GNU Make "*) ;;
        *) return 1 ;;
    esac

    # A version banner is not proof that a Make implementation can run
    # recipes. This small stdin makefile avoids source checkout or downloads.
    whp_make_result=$(
        printf 'whp-seed-check:\n\t@printf "whp-gnu-make-ok\\n"\n' |
            LC_ALL=C MAKEFLAGS= MFLAGS= GNUMAKEFLAGS= \
                "$whp_make_resolved" --no-print-directory -s -f - \
                whp-seed-check 2>/dev/null
    ) || return 1
    [ "$whp_make_result" = whp-gnu-make-ok ] || return 1

    printf '%s\n' "$whp_make_resolved"
)

whp_find_gnu_make()
(
    # GNU Make is needed before the macOS dependency provider adds Homebrew
    # to PATH. Probe the native Homebrew prefix directly, without exposing its
    # other tools to the early bootstrap. Never cross Rosetta architectures.
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        case "$(uname -m 2>/dev/null || true)" in
            arm64|aarch64) whp_make_brew_prefix=/opt/homebrew ;;
            x86_64) whp_make_brew_prefix=/usr/local ;;
            *) whp_make_brew_prefix= ;;
        esac
        if [ -n "$whp_make_brew_prefix" ]; then
            for whp_make_candidate in \
                "$whp_make_brew_prefix/bin/gmake" \
                "$whp_make_brew_prefix/opt/make/bin/gmake"; do
                if whp_make_resolved=$(whp_resolve_gnu_make "$whp_make_candidate"); then
                    printf '%s\n' "$whp_make_resolved"
                    return 0
                fi
            done
        fi
    fi
    for whp_make_candidate in gmake make; do
        if whp_make_resolved=$(whp_resolve_gnu_make "$whp_make_candidate"); then
            printf '%s\n' "$whp_make_resolved"
            return 0
        fi
    done
    return 1
)
