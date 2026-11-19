#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCHEMA="$SCRIPT_DIR/menu-options.def"
CONFIG=${1:-.whpconfig}
if [ "$#" -gt 0 ]; then
    shift
fi

[ -f "$SCHEMA" ] || {
    printf 'error: WHP shell menu schema is missing: %s\n' "$SCHEMA" >&2
    exit 2
}

WORK="${TMPDIR:-/tmp}/whp-menuconfig.$$"
WORK_NEW="$WORK.new"
SAVE_TMP="${CONFIG}.tmp.$"
menu_filter=
umask 077
trap 'rm -f "$WORK" "$WORK_NEW" "$SAVE_TMP"' 0 1 2 3 15

if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$WORK"
else
    {
        printf '%s\n' '# WHP QEMU portable user configuration'
        printf '%s\n' '# Minimal shell fallback file; omitted settings use repository defaults.'
        printf '%s\n' 'WHP_CONFIG_VERSION=3'
    } > "$WORK"
fi

get_value()
{
    key=$1
    awk -v wanted="$key" '
        index($0, wanted "=") == 1 {
            value = substr($0, length(wanted) + 2)
            found = 1
        }
        END {
            if (found) print value
        }
    ' "$WORK"
}

get_schema_line()
{
    wanted=$1
    awk -F '|' -v wanted="$wanted" '
        $0 !~ /^#/ && NF >= 5 {
            count++
            if (count == wanted) {
                print
                exit
            }
        }
    ' "$SCHEMA"
}

set_value()
{
    key=$1
    value=$2
    awk -v wanted="$key" '
        index($0, wanted "=") == 1 { next }
        { print }
    ' "$WORK" > "$WORK_NEW"
    printf '%s=%s\n' "$key" "$value" >> "$WORK_NEW"
    mv "$WORK_NEW" "$WORK"
}

# The POSIX fallback shares the Python model's one-time retirement mapping.
# Migrate only the scratch copy. An unsaved quit leaves .whpconfig untouched.
migrate_retired_cache()
{
    old=$(get_value BOOTSTRAP_SCCACHE)
    [ -n "$old" ] || return 0
    current=$(get_value COMPILER_CACHE)
    case "$old" in
        y)
            case "$current" in
                ''|auto|sccache|managed-sccache)
                    set_value COMPILER_CACHE managed-sccache ;;
                *)
                    printf 'error: BOOTSTRAP_SCCACHE=y conflicts with COMPILER_CACHE=%s\n' \
                        "$current" >&2
                    return 1 ;;
            esac ;;
        n) ;;
        *)
            printf 'error: legacy BOOTSTRAP_SCCACHE must be y or n: %s\n' \
                "$old" >&2
            return 1 ;;
    esac
    awk '/^BOOTSTRAP_SCCACHE=/{next} {print}' "$WORK" > "$WORK_NEW"
    mv "$WORK_NEW" "$WORK"
}

migrate_retired_cache || exit 2

render_menu()
{
    # Keep option numbers stable across filtered and unfiltered views.
    # The schema is data; only AWK interprets its fields.
    awk -v filter="$menu_filter" '
        BEGIN { search = tolower(filter) }
        FNR == NR {
            if ($0 ~ /^[A-Z][A-Z0-9_]*=/) {
                pos = index($0, "=")
                key = substr($0, 1, pos - 1)
                values[key] = substr($0, pos + 1)
            }
            next
        }
        $0 !~ /^#/ && NF {
            count = split($0, field, "|")
            if (count < 5) next
            key = field[1]
            section = field[2]
            label = field[3]
            default_value = field[5]
            group = field[7]
            item++
            # A checked all-target selector replaces the individual rows;
            # their saved values are never changed.
            if (values["BUILD_QEMU_SYSTEM_ALL"] == "y" &&
                key ~ /^BUILD_QEMU_SYSTEM_(I386|PPC|SPARC)$/) {
                next
            }
            if (values["BOOTSTRAP_NATIVE_LLVM"] != "y" &&
                key ~ /^NATIVE_LLVM_/) {
                next
            }
            if (search != "" &&
                index(tolower(key " " section " " label " " group), search) == 0) {
                next
            }
            if (section != previous_section) {
                printf "\n[%s]\n", section
                previous_section = section
                previous_group = ""
            }
            if (group != "" && group != previous_group) {
                if (group == "System emulators") {
                    mode = values["BUILD_QEMU_SYSTEM_ALL"] == "y" ? "collapsed" : "expanded"
                    printf "  %s (%s)\n", group, mode
                } else if (group == "Native LLVM bootstrap") {
                    mode = values["BOOTSTRAP_NATIVE_LLVM"] == "y" ? "expanded" : "collapsed"
                    printf "  %s (%s)\n", group, mode
                } else {
                    printf "  %s\n", group
                }
                previous_group = group
            } else if (group == "") {
                previous_group = ""
            }
            value = (key in values) ? values[key] : default_value
            printf "  %2d) %-28s %-28s %s\n", item, label, key, value
            shown++
        }
        END {
            if (search != "" && shown == 0) {
                printf "No options match: %s\n", filter
            }
        }
    ' "$WORK" "$SCHEMA"
}

dump_menu()
{
    render_menu
}

reset_known_values()
{
    awk '
        FNR == NR {
            if ($0 !~ /^#/ && NF) {
                split($0, field, "|")
                known[field[1]] = 1
            }
            next
        }
        {
            pos = index($0, "=")
            key = pos ? substr($0, 1, pos - 1) : ""
            if (!(key in known)) print
        }
    ' "$SCHEMA" "$WORK" > "$WORK_NEW"
    mv "$WORK_NEW" "$WORK"
}

# A non-Python menu must catch the same established build conflicts.
# Let users edit an invalid old file, but never save it unchanged.
menu_value_or_default()
{
    value=$(get_value "$1")
    if [ -n "$value" ]; then
        printf '%s\n' "$value"
    else
        printf '%s\n' "$2"
    fi
}

validate_saved_configuration()
{
    tsan=$(menu_value_or_default QEMU_TSAN n)
    asan=$(menu_value_or_default QEMU_ASAN n)
    ubsan=$(menu_value_or_default QEMU_UBSAN n)
    lto=$(menu_value_or_default QEMU_HOST_LTO auto)
    lto_mode=$(menu_value_or_default QEMU_HOST_LTO_MODE auto)
    if [ "$tsan" = y ] && { [ "$asan" = y ] || [ "$ubsan" = y ]; }; then
        printf '%s\n' \
            'Cannot save: QEMU_TSAN=y conflicts with QEMU_ASAN=y or QEMU_UBSAN=y' >&2
        return 1
    fi
    if [ "$lto" = n ] && [ "$lto_mode" != auto ]; then
        printf 'Cannot save: QEMU_HOST_LTO_MODE=%s conflicts with QEMU_HOST_LTO=n\n' \
            "$lto_mode" >&2
        return 1
    fi
    if [ "$(menu_value_or_default BOOTSTRAP_NATIVE_LLVM n)" = y ] &&
       [ "$(menu_value_or_default NATIVE_LLVM_ASAN_AUTO_DEBUG n)" = y ]; then
        lldb=$(menu_value_or_default NATIVE_LLVM_ENABLE_LLDB auto)
        llvm_asan=$(menu_value_or_default NATIVE_LLVM_VALIDATE_ASAN auto)
        if [ "$lldb" = n ]; then
            printf '%s\n' \
                'Cannot save: native LLVM ASan auto-debug requires LLDB=auto or y' >&2
            return 1
        fi
        if [ "$llvm_asan" = n ]; then
            printf '%s\n' \
                'Cannot save: native LLVM ASan auto-debug requires ASan validation=auto or y' >&2
            return 1
        fi
    fi
    for job_key in NATIVE_LLVM_LINK_JOBS NATIVE_LLVM_COMPILE_JOBS NATIVE_LLVM_TABLEGEN_JOBS; do
        job_value=$(menu_value_or_default "$job_key" auto)
        case "$job_value" in
            auto) ;;
            0)
                if [ "$job_key" = NATIVE_LLVM_LINK_JOBS ]; then
                    printf '%s\n' 'Cannot save: NATIVE_LLVM_LINK_JOBS must be positive or auto' >&2
                    return 1
                fi ;;
            *[!0-9]*|'')
                printf 'Cannot save: %s must be auto or a nonnegative integer\n' "$job_key" >&2
                return 1 ;;
            0*)
                printf 'Cannot save: %s must not contain leading zeroes\n' "$job_key" >&2
                return 1 ;;
        esac
    done
}

save_config()
{
    validate_saved_configuration || return 1
    config_dir=$(dirname -- "$CONFIG")
    mkdir -p "$config_dir"
    cp "$WORK" "$SAVE_TMP"
    mv "$SAVE_TMP" "$CONFIG"
}

# The Python menu refuses unexpected extra arguments; keep the POSIX
# fallback equally strict instead of silently ignoring malformed calls.
if [ "$#" -gt 1 ]; then
    printf 'error: shell menuconfig accepts only --dump: %s\\n' "$*" >&2
    exit 2
fi

case "${1:-}" in
    --dump)
        dump_menu
        exit 0
        ;;
    "")
        ;;
    *)
        printf 'error: unsupported shell menuconfig argument: %s\n' "$1" >&2
        exit 2
        ;;
esac

dirty=0
while :; do
    printf '\nWHP QEMU Configuration — POSIX shell fallback\n'
    printf 'File: %s\n' "$CONFIG"
    if [ -n "$menu_filter" ]; then
        printf 'Filter: %s (a=show all)\n' "$menu_filter"
    fi
    render_menu
    printf '\nEnter option number, f=filter, a=all, s=save, r=defaults, q=quit: '
    if ! IFS= read -r action; then
        exit 0
    fi

    case "$action" in
        f|F)
            printf 'Filter by option name, label, group or section (empty=all): '
            IFS= read -r menu_filter || exit 0
            continue
            ;;
        a|A)
            menu_filter=
            continue
            ;;
        s|S)
            if save_config; then
                dirty=0
                printf 'Saved %s\n' "$CONFIG"
            fi
            continue
            ;;
        r|R)
            reset_known_values
            dirty=1
            printf 'Repository defaults loaded in memory; press s to save.\n'
            continue
            ;;
        q|Q)
            if [ "$dirty" = 1 ]; then
                printf 'Discard unsaved changes? [y/N]: '
                IFS= read -r answer || answer=
                case "$answer" in
                    y|Y|yes|YES) exit 0 ;;
                    *) continue ;;
                esac
            fi
            exit 0
            ;;
        ''|*[!0-9]*)
            printf 'Invalid selection: %s\n' "$action" >&2
            continue
            ;;
    esac

    line=$(get_schema_line "$action")
    if [ -z "$line" ]; then
        printf 'No option numbered %s\n' "$action" >&2
        continue
    fi

    # A schema row is data, not a shell command line. Unquoted
    # "set -- $line" also expands pathname globs from labels and groups.
    # read performs IFS field splitting without executing glob expansion.
    IFS='|' read -r key section label kind default_value choices group <<EOF
$line
EOF

    case "$key" in
        NATIVE_LLVM_*)
            if [ "$(menu_value_or_default BOOTSTRAP_NATIVE_LLVM n)" != y ]; then
                printf '%s\n' \
                    'Native LLVM options are collapsed; enable BOOTSTRAP_NATIVE_LLVM first.' >&2
                continue
            fi
            ;;
        BUILD_QEMU_SYSTEM_I386|BUILD_QEMU_SYSTEM_PPC|BUILD_QEMU_SYSTEM_SPARC)
            if [ "$(menu_value_or_default BUILD_QEMU_SYSTEM_ALL n)" = y ]; then
                printf '%s\n' \
                    'Individual emulator targets are collapsed; disable BUILD_QEMU_SYSTEM_ALL first.' >&2
                continue
            fi
            ;;
    esac

    current=$(get_value "$key")
    if [ -z "$current" ]; then
        current=$default_value
    fi

    case "$kind" in
        bool)
            case "$current" in
                y) new_value=n ;;
                n) new_value=y ;;
                *) new_value=$default_value ;;
            esac
            ;;
        choice)
            new_value=$(awk -v choices="$choices" -v current="$current" -v default_value="$default_value" '
                BEGIN {
                    count = split(choices, item, ",")
                    for (i = 1; i <= count; i++) {
                        if (item[i] == current) {
                            print item[(i % count) + 1]
                            exit
                        }
                    }
                    print default_value
                }
            ')
            ;;
        string)
            printf '%s [%s]: ' "$label" "$current"
            IFS= read -r new_value || new_value=
            if [ -z "$new_value" ]; then
                new_value=$current
            fi
            ;;
        *)
            printf 'error: unsupported option kind for %s: %s\n' "$key" "$kind" >&2
            exit 2
            ;;
    esac

    set_value "$key" "$new_value"
    dirty=1
    printf 'Changed %s: %s -> %s\n' "$label" "$current" "$new_value"
done
