# Shared POSIX-shell policy helpers for the WHP build bootstrap.
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Keep this module dependency-free: build.sh and host-tools.sh may source it
# before GNU Bash or other managed host tools are available.

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
