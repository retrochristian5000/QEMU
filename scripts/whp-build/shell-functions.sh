# Shared POSIX-shell policy helpers for the WHP build bootstrap.
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Keep this module dependency-free: build.sh and host-tools.sh may source it
# before GNU Bash or other managed host tools are available.

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
