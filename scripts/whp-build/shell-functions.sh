#!/bin/sh
# Shared POSIX-shell policy helpers for the WHP build bootstrap.
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Keep this module dependency-free: build.sh and host-tools.sh may source it
# before GNU Bash or other managed host tools are available.

# Resolve a command's parent directory without an external dirname process.
# Callers pass executable file paths, not paths ending in a slash.
whp_command_dir()
(
    case "$1" in
        */*) whp_dir=${1%/*}; [ -n "$whp_dir" ] || whp_dir=/ ;;
        *) whp_dir=. ;;
    esac
    printf '%s\n' "$whp_dir"
)

# Shared rollback guard for pre-Python bootstrap and standalone shell lanes.
# A gitlink is a reproducibility baseline, not permission to rewind an
# initialized checkout containing newer descendant commits.
whp_git_submodule_prepare()
(
    whp_parent=$1
    whp_path=$2
    whp_git=${3:-git}
    whp_access=${4:-online}
    case "$whp_path" in
        ""|/*|../*|*/../*|*/..) printf 'error: invalid submodule path: %s\n' "$whp_path" >&2; return 1 ;;
    esac
    whp_target="$whp_parent/$whp_path"
    if [ -L "$whp_target" ]; then
        printf 'error: refusing symlinked submodule %s\n' "$whp_path" >&2
        return 1
    fi
    whp_entry=$("$whp_git" -C "$whp_parent" ls-tree HEAD -- "$whp_path") || return 1
    set -- $whp_entry
    if [ "${1:-}" != 160000 ] || [ "${2:-}" != commit ]; then
        printf 'error: missing gitlink: %s\n' "$whp_path" >&2
        return 1
    fi
    whp_pin=$3
    if [ ! -e "$whp_target/.git" ]; then
        if [ "$whp_access" = offline ]; then
            printf 'error: submodule %s is missing in offline mode\n' "$whp_path" >&2
            return 1
        fi
        "$whp_git" -C "$whp_parent" submodule update --init --depth 1 -- "$whp_path" || return 1
    else
        whp_top=$("$whp_git" -C "$whp_target" rev-parse --show-toplevel) || return 1
        whp_actual_top=$(CDPATH= cd -- "$whp_target" && pwd -P) || return 1
        # Git and the shell may spell the same root differently (logical
        # symlink, /var vs /private/var, or a relocated submodule gitfile).
        # Compare physical worktree locations, not raw path strings. A genuine
        # different root must still fail before any checkout/ancestry action.
        whp_top_physical=$(CDPATH= cd -- "$whp_top" && pwd -P) || {
            printf 'error: %s has an inaccessible Git worktree: %s\n' \
                "$whp_path" "$whp_top" >&2
            return 1
        }
        if [ "$whp_top_physical" != "$whp_actual_top" ]; then
            printf 'error: %s has an unexpected Git worktree (Git: %s; expected: %s)\n' \
                "$whp_path" "$whp_top_physical" "$whp_actual_top" >&2
            return 1
        fi
        whp_current=$("$whp_git" -C "$whp_target" rev-parse HEAD) || return 1
        if [ "$whp_current" != "$whp_pin" ]; then
            if ! "$whp_git" -C "$whp_target" cat-file -e "$whp_pin^{commit}" 2>/dev/null; then
                if [ "$whp_access" = offline ]; then
                    printf 'error: pin history missing for offline submodule %s\n' "$whp_path" >&2
                    return 1
                fi
                "$whp_git" -C "$whp_target" fetch --no-tags --no-recurse-submodules origin "$whp_pin" || return 1
            fi
            if "$whp_git" -C "$whp_target" merge-base --is-ancestor "$whp_pin" "$whp_current"; then
                printf 'WHP submodule: preserving newer %s at %s (pin %s)\n' \
                    "$whp_path" "$whp_current" "$whp_pin" >&2
                return 0
            fi
            # Depth-one Git clones can hide the ancestry of a newer tip.
            # Recover only missing history, never switch a branch or HEAD.
            # Keep the fetch bounded for very large LLVM/Python repositories.
            if [ "$whp_access" != offline ] &&
               [ "$("$whp_git" -C "$whp_target" rev-parse --is-shallow-repository)" = true ] &&
               ! "$whp_git" -C "$whp_target" merge-base --is-ancestor "$whp_current" "$whp_pin"; then
                for whp_deepen in 64 256 1024; do
                    "$whp_git" -C "$whp_target" fetch "--deepen=$whp_deepen" \
                        --no-tags --no-recurse-submodules origin "$whp_current" || return 1
                    if "$whp_git" -C "$whp_target" merge-base --is-ancestor "$whp_pin" "$whp_current"; then
                        printf 'WHP submodule: preserved newer shallow checkout %s at %s (pin %s)\n' \
                            "$whp_path" "$whp_current" "$whp_pin" >&2
                        return 0
                    fi
                    if "$whp_git" -C "$whp_target" merge-base --is-ancestor "$whp_current" "$whp_pin"; then
                        break
                    fi
                done
            fi
            if ! "$whp_git" -C "$whp_target" merge-base --is-ancestor "$whp_current" "$whp_pin"; then
                printf 'error: %s is divergent or history is incomplete; refusing checkout (deepen Git history if shallow)\n' "$whp_path" >&2
                return 1
            fi
            if [ -n "$("$whp_git" -C "$whp_target" status --porcelain --untracked-files=all)" ]; then
                printf 'error: %s has local edits; refusing checkout\n' "$whp_path" >&2
                return 1
            fi
            if "$whp_git" -C "$whp_target" symbolic-ref -q HEAD >/dev/null 2>&1; then
                printf 'error: %s has an attached branch; refusing checkout\n' "$whp_path" >&2
                return 1
            fi
            "$whp_git" -C "$whp_parent" submodule update --init --no-fetch -- "$whp_path" || return 1
        fi
    fi
    whp_current=$("$whp_git" -C "$whp_target" rev-parse HEAD) || return 1
    if [ "$whp_current" != "$whp_pin" ]; then
        printf 'error: %s did not reach pinned commit %s\n' "$whp_path" "$whp_pin" >&2
        return 1
    fi
)


# Read one Libtool bootstrap marker entry without constructing a sed program.
# A missing, duplicate, or invalid producer tool must never silently turn into
# an empty build variable. Marker tool identities use PATH|version.
whp_marker_required_tool()
(
    whp_marker_file=$1
    whp_marker_key=$2
    whp_marker_seen=0
    whp_marker_identity=

    if [ ! -r "$whp_marker_file" ]; then
        printf 'error: Libtool marker is unreadable: %s\n' "$whp_marker_file" >&2
        return 1
    fi
    while IFS= read -r whp_marker_line || [ -n "$whp_marker_line" ]; do
        case "$whp_marker_line" in
            "$whp_marker_key"=*)
                whp_marker_seen=$((whp_marker_seen + 1))
                whp_marker_identity=${whp_marker_line#*=}
                ;;
        esac
    done < "$whp_marker_file"
    if [ "$whp_marker_seen" -ne 1 ]; then
        printf 'error: Libtool marker needs exactly one %s tool name (found %s): %s\n' \
            "$whp_marker_key" "$whp_marker_seen" "$whp_marker_file" >&2
        return 1
    fi
    case "$whp_marker_identity" in
        *'|'*) whp_marker_path=${whp_marker_identity%%|*} ;;
        *)
            printf 'error: Libtool marker has malformed %s tool identity: %s\n' \
                "$whp_marker_key" "$whp_marker_identity" >&2
            return 1
            ;;
    esac
    if [ -z "$whp_marker_path" ]; then
        printf 'error: Libtool marker has an empty %s tool name\n' \
            "$whp_marker_key" >&2
        return 1
    fi
    case "$whp_marker_path" in
        /*) ;;
        *)
            printf 'error: Libtool marker %s tool path is not absolute: %s\n' \
                "$whp_marker_key" "$whp_marker_path" >&2
            return 1
            ;;
    esac
    if [ ! -f "$whp_marker_path" ] || [ ! -x "$whp_marker_path" ]; then
        printf 'error: Libtool marker %s tool is not executable: %s\n' \
            "$whp_marker_key" "$whp_marker_path" >&2
        return 1
    fi
    printf '%s\n' "$whp_marker_path"
)

whp_marker_required_value()
(
    whp_marker_file=$1
    whp_marker_key=$2
    whp_marker_seen=0
    whp_marker_value=

    if [ ! -r "$whp_marker_file" ]; then
        printf 'error: Libtool marker is unreadable: %s\n' "$whp_marker_file" >&2
        return 1
    fi
    while IFS= read -r whp_marker_line || [ -n "$whp_marker_line" ]; do
        case "$whp_marker_line" in
            "$whp_marker_key"=*)
                whp_marker_seen=$((whp_marker_seen + 1))
                whp_marker_value=${whp_marker_line#*=}
                ;;
        esac
    done < "$whp_marker_file"
    if [ "$whp_marker_seen" -ne 1 ] || [ -z "$whp_marker_value" ]; then
        printf 'error: Libtool marker needs one nonempty %s value: %s\n' \
            "$whp_marker_key" "$whp_marker_file" >&2
        return 1
    fi
    printf '%s\n' "$whp_marker_value"
)

whp_archive_toolchain_smoke()
(
    whp_cc=${1:-}
    whp_ar=${2:-}
    whp_ranlib=${3:-}
    whp_work_root=${4:-${TMPDIR:-/tmp}}
    whp_nm=${5:-}

    # Fifth argument omitted: legacy archive-only qualification. Fifth
    # argument explicitly supplied: NM is mandatory even if the value is
    # empty, so a broken caller cannot silently skip symbol verification.
    whp_nm_required=0
    if [ "$#" -ge 5 ]; then
        whp_nm_required=1
    fi

    for whp_tool_role in CC AR RANLIB NM; do
        case "$whp_tool_role" in
            CC) whp_tool=$whp_cc ;;
            AR) whp_tool=$whp_ar ;;
            RANLIB) whp_tool=$whp_ranlib ;;
            NM)
                [ "$whp_nm_required" = 1 ] || continue
                whp_tool=$whp_nm
                ;;
        esac
        if [ -z "$whp_tool" ]; then
            printf 'error: archive-tool smoke requires a nonempty %s executable\n' \
                "$whp_tool_role" >&2
            return 1
        fi
        case "$whp_tool" in
            *[[:space:]]*)
                printf 'error: archive-tool smoke requires one executable for %s: %s\n' \
                    "$whp_tool_role" "$whp_tool" >&2
                return 1
                ;;
        esac
        if ! command -v "$whp_tool" >/dev/null 2>&1; then
            printf 'error: archive-tool %s executable is unavailable: %s\n' \
                "$whp_tool_role" "$whp_tool" >&2
            return 1
        fi
    done

    mkdir -p "$whp_work_root" || return 1
    whp_probe_dir=$(mktemp -d "$whp_work_root/.whp-ar-smoke.XXXXXX") || return 1
    trap 'rm -rf "$whp_probe_dir"' 0 HUP INT TERM
    whp_log="$whp_probe_dir/probe.log"

    cat > "$whp_probe_dir/member.c" <<'EOF'
int whp_archive_probe(void) { return 0; }
EOF

    if ! "$whp_cc" -c "$whp_probe_dir/member.c" \
        -o "$whp_probe_dir/member.o" >"$whp_log" 2>&1; then
        whp_stage='compile archive member'
    elif ! "$whp_ar" cr "$whp_probe_dir/libwhp-ar-smoke.a" \
        "$whp_probe_dir/member.o" >"$whp_log" 2>&1; then
        whp_stage='create archive'
    elif ! "$whp_ranlib" "$whp_probe_dir/libwhp-ar-smoke.a" \
        >"$whp_log" 2>&1; then
        whp_stage='index archive'
    elif ! "$whp_ar" t "$whp_probe_dir/libwhp-ar-smoke.a" \
        >"$whp_log" 2>&1; then
        whp_stage='read archive table'
    elif [ -n "$whp_nm" ] &&
         ! "$whp_nm" -P -g "$whp_probe_dir/libwhp-ar-smoke.a" \
            >"$whp_log" 2>&1; then
        whp_stage='inspect archive symbols'
    elif [ -n "$whp_nm" ] &&
         ! grep -Eq '(^|[[:space:]])_?whp_archive_probe[[:space:]]+T([[:space:]]|$)' \
            "$whp_log"; then
        whp_stage='verify archive symbols'
    else
        return 0
    fi

    printf '%s\n' \
        "error: QEMU archive toolchain failed: $whp_stage" \
        "  CC=$whp_cc" \
        "  AR=$whp_ar" \
        "  RANLIB=$whp_ranlib" \
        "  NM=${whp_nm:-<not requested>}" >&2
    if [ -s "$whp_log" ]; then
        sed 's/^/  /' "$whp_log" >&2
    fi
    return 1
)

whp_normalize_auto_switch()
(
    whp_switch_name=${1:-}
    whp_switch_value=${2:-}

    case "$whp_switch_value" in
        y) whp_switch_value=1 ;;
        n) whp_switch_value=0 ;;
        auto|0|1) ;;
        *)
            printf 'error: %s must be auto, 0, or 1\n' "$whp_switch_name" >&2
            return 1
            ;;
    esac

    printf '%s\n' "$whp_switch_value"
)

whp_require_auto_switch()
(
    whp_switch_name=${1:-}
    whp_switch_value=${2:-}

    case "$whp_switch_value" in
        auto|0|1) ;;
        *)
            printf 'error: %s must be auto, 0, or 1\n' "$whp_switch_name" >&2
            return 1
            ;;
    esac

    printf '%s\n' "$whp_switch_value"
)

whp_require_binary_switch()
(
    whp_switch_name=${1:-}
    whp_switch_value=${2:-}

    case "$whp_switch_value" in
        0|1) ;;
        *)
            printf 'error: %s must be 0 or 1\n' "$whp_switch_name" >&2
            return 1
            ;;
    esac

    printf '%s\n' "$whp_switch_value"
)
