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

    for whp_tool in "$whp_cc" "$whp_ar" "$whp_ranlib"; do
        [ -n "$whp_tool" ] || {
            printf 'error: archive-tool smoke received an empty tool name\n' >&2
            return 1
        }
        case "$whp_tool" in
            *' '*)
                printf 'error: archive-tool smoke requires one executable per tool: %s\n' \
                    "$whp_tool" >&2
                return 1
                ;;
        esac
        command -v "$whp_tool" >/dev/null 2>&1 || {
            printf 'error: archive-tool executable is unavailable: %s\n' \
                "$whp_tool" >&2
            return 1
        }
    done

    # NM is optional for callers that only need archive creation. Native LLVM
    # consumers pass it explicitly so the probe also qualifies symbol reading.
    if [ -n "$whp_nm" ]; then
        case "$whp_nm" in
            *[[:space:]]*)
                printf 'error: archive-tool smoke requires one executable for NM: %s\n' \
                    "$whp_nm" >&2
                return 1
                ;;
        esac
        command -v "$whp_nm" >/dev/null 2>&1 || {
            printf 'error: archive-tool NM executable is unavailable: %s\n' \
                "$whp_nm" >&2
            return 1
        }
    fi

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
        "  RANLIB=$whp_ranlib" >&2
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
