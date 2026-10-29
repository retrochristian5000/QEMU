#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Shared native compiler probes; sourced only by compiler adapters.

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-cc-adapter-probe 2>/dev/null || true)
    case "$marker" in
        whp-qemu-cc-seed-adapter|whp-qemu-cxx-seed-adapter) return 0 ;;
    esac
    return 1
}

# Report genuine compiler failures only for explicit choices or selected
# Apple defaults; keep exploratory PATH discovery quiet.
resolve_executable()
(
    value=$1
    report=${2:-quiet}
    if [ -z "$value" ]; then
        [ "$report" = report ] && printf 'error: empty build compiler selection\n' >&2
        exit 1
    fi
    if [ -x "$value" ]; then
        candidate=$value
    else
        case "$value" in
            */*|*[[:space:]]*)
                [ "$report" = report ] &&
                    printf 'error: compiler path is not executable: %s\n' "$value" >&2
                exit 1 ;;
        esac
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
        [ "$report" = report ] &&
            printf 'error: build compiler cannot be found or executed: %s\n' "$value" >&2
        exit 1
    fi
    if is_self "$candidate"; then
        [ "$report" = report ] &&
            printf 'error: compiler selection loops into WHP adapter: %s\n' "$candidate" >&2
        exit 1
    fi
    if version_output=$("$candidate" --version 2>&1); then
        :
    else
        code=$?
        if [ "$report" = report ]; then
            printf 'error: compiler --version failed (exit %s): %s\n' "$code" "$candidate" >&2
            [ -z "$version_output" ] || printf '%s\n' "$version_output" >&2
        fi
        exit 1
    fi
    printf '%s\n' "$candidate"
)

compiler_runs_native()
(
    language=$1
    compiler=$2
    report=${3:-quiet}
    # A PID-only directory can outlive a killed bootstrap. Keep retried and
    # concurrent probes separate without leaking temporary output on success.
    if tmp_dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-cc-seed.XXXXXX"); then
        :
    else
        [ "$report" = report ] &&
            printf 'error: cannot create native compiler probe directory under %s\n' \
                "${TMPDIR:-/tmp}" >&2
        exit 1
    fi
    trap 'rm -rf -- "$tmp_dir"' 0
    trap 'exit 1' HUP INT TERM
    output=$tmp_dir/probe
    log=$tmp_dir/output.log
    case "$language" in
        c)
            src=$tmp_dir/probe.c
            printf '%s\n' 'int main(void) { return 0; }' > "$src" || exit 1
            ;;
        c++)
            src=$tmp_dir/probe.cc
            printf '%s\n' 'int main() { return 0; }' > "$src" || exit 1
            ;;
        *)
            [ "$report" = report ] &&
                printf 'error: unsupported native compiler language: %s\n' "$language" >&2
            exit 1 ;;
    esac
    if [ "$language" = c++ ]; then
        if "$compiler" -std=c++17 "$src" -o "$output" > "$log" 2>&1; then
            :
        else
            code=$?
            if [ "$report" = report ]; then
                printf 'error: native C++17 compile/link probe failed (exit %s): %s\n' "$code" "$compiler" >&2
                printf '  arguments: -std=c++17 probe.cc -o probe\n' >&2
                cat "$log" >&2
            fi
            exit 1
        fi
    else
        if "$compiler" "$src" -o "$output" > "$log" 2>&1; then
            :
        else
            code=$?
            if [ "$report" = report ]; then
                printf 'error: native C compile/link probe failed (exit %s): %s\n' "$code" "$compiler" >&2
                printf '  arguments: probe.c -o probe\n' >&2
                cat "$log" >&2
            fi
            exit 1
        fi
    fi
    if "$output" > "$log" 2>&1; then
        :
    else
        code=$?
        if [ "$report" = report ]; then
            printf 'error: native %s executable probe failed (exit %s): %s\n' \
                "$language" "$code" "$compiler" >&2
            cat "$log" >&2
        fi
        exit 1
    fi
)

try_compiler()
(
    language=$1
    value=$2
    report=${3:-quiet}
    candidate=$(resolve_executable "$value" "$report") || exit 1
    compiler_runs_native "$language" "$candidate" "$report" || exit 1
    printf '%s\n' "$candidate"
)
