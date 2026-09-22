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
SAVE_TMP="${CONFIG}.tmp.$$"
umask 077
trap 'rm -f "$WORK" "$WORK_NEW" "$SAVE_TMP"' 0 1 2 3 15

if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$WORK"
else
    {
        printf '%s\n' '# WHP QEMU portable user configuration'
        printf '%s\n' '# Minimal shell fallback file; omitted settings use repository defaults.'
        printf '%s\n' 'WHP_CONFIG_VERSION=2'
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

render_menu()
{
    awk '
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
            if (section != previous_section) {
                printf "\n[%s]\n", section
                previous_section = section
                previous_group = ""
            }
            if (group != "" && group != previous_group) {
                printf "  %s\n", group
                previous_group = group
            } else if (group == "") {
                previous_group = ""
            }
            value = (key in values) ? values[key] : default_value
            item++
            printf "  %2d) %-28s %-28s %s\n", item, label, key, value
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

save_config()
{
    config_dir=$(dirname -- "$CONFIG")
    mkdir -p "$config_dir"
    cp "$WORK" "$SAVE_TMP"
    mv "$SAVE_TMP" "$CONFIG"
}

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
    render_menu
    printf '\nEnter option number, s=save, r=defaults, q=quit: '
    if ! IFS= read -r action; then
        exit 0
    fi

    case "$action" in
        s|S)
            save_config
            dirty=0
            printf 'Saved %s\n' "$CONFIG"
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

    old_ifs=$IFS
    IFS='|'
    set -- $line
    IFS=$old_ifs
    key=$1
    section=$2
    label=$3
    kind=$4
    default_value=$5
    choices=$6

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
