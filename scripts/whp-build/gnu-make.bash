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

    printf '%s\n' "$whp_make_resolved"
)

whp_find_gnu_make()
(
    for whp_make_candidate in gmake make; do
        if whp_make_resolved=$(whp_resolve_gnu_make "$whp_make_candidate"); then
            printf '%s\n' "$whp_make_resolved"
            return 0
        fi
    done
    return 1
)
