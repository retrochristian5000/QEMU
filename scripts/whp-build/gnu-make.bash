# GNU Make discovery shared by the WHP QEMU and OpenBIOS build paths.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_resolve_gnu_make()
{
    local requested="${1:-}"
    local resolved
    local version

    [[ -n "$requested" ]] || return 1
    if [[ "$requested" == */* ]]; then
        resolved="$requested"
    else
        resolved="$(command -v "$requested" 2>/dev/null || true)"
    fi
    [[ -n "$resolved" && -x "$resolved" ]] || return 1

    version="$(LC_ALL=C "$resolved" --version 2>/dev/null || true)"
    version="${version%%$'\n'*}"
    [[ "$version" == GNU\ Make\ * ]] || return 1

    printf '%s\n' "$resolved"
}

whp_find_gnu_make()
{
    local candidate
    local resolved

    for candidate in gmake make; do
        if resolved="$(whp_resolve_gnu_make "$candidate")"; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done
    return 1
}
