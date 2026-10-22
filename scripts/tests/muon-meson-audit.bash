#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Muon is an advisory Meson linter/formatter, not QEMU's Meson build driver.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

muon="${MUON_BIN:-muon}"
mode="${1:-audit}"
scope="${2:-all}"
target="${3:-meson.build}"
report="${MUON_REPORT:-$root/muon-meson-report.txt}"
patch="${MUON_PATCH:-$root/muon-meson-cleanup.patch}"

case "$mode:$scope" in
    audit:all|audit:file|cleanup:all|cleanup:file) ;;
    *) printf 'error: usage: %s audit|cleanup all|file [tracked Meson path]\n' "$0" >&2; exit 2 ;;
esac

if ! command -v "$muon" >/dev/null 2>&1; then
    printf 'error: Muon executable not found: %s\n' "$muon" >&2
    exit 2
fi

tracked=()
while IFS= read -r -d '' file; do
    case "${file##*/}" in
        meson.build|meson_options.txt|meson.options)
            tracked+=("$file")
            ;;
    esac
done < <(git ls-files --cached -z)

if (( ${#tracked[@]} == 0 )); then
    printf '%s\n' 'error: no tracked Meson definitions found' >&2
    exit 2
fi

selected=()
if [[ "$scope" == all ]]; then
    selected=("${tracked[@]}")
else
    # Only existing, tracked Meson definitions may be formatted; no globs,
    # path traversal, generated files, or arbitrary workflow input paths.
    for file in "${tracked[@]}"; do
        if [[ "$file" == "$target" ]]; then
            selected=("$file")
            break
        fi
    done
    if (( ${#selected[@]} != 1 )); then
        printf 'error: not a tracked Meson definition: %s\n' "$target" >&2
        exit 2
    fi
fi

# Do not claim a legacy style mismatch is a parse error. The repository
# already has a separate, authoritative Meson parser/configuration gate.
: > "$report"
if [[ "$mode" == cleanup ]]; then
    : > "$patch"
fi
parse_errors=0
format_drift=0
format_errors=0
changed=0
for file in "${selected[@]}"; do
    # Current Muon dropped the old 'check' CLI command. A successful
    # stdout-only formatting pass verifies that Muon can parse this file;
    # Meson's own parser remains authoritative for language compatibility.
    if ! "$muon" fmt "$file" >/dev/null 2>>"$report"; then
        printf 'PARSE_ERROR %s\n' "$file" | tee -a "$report"
        parse_errors=$((parse_errors + 1))
        continue
    fi

    if "$muon" fmt -q "$file" >>"$report" 2>&1; then
        continue
    fi
    format_drift=$((format_drift + 1))
    printf 'FORMAT_DRIFT %s\n' "$file" | tee -a "$report"

    if [[ "$mode" == cleanup ]]; then
        if ! "$muon" fmt -i "$file" >>"$report" 2>&1 ||
           ! "$muon" fmt "$file" >/dev/null 2>>"$report" ||
           ! "$muon" fmt -q "$file" >>"$report" 2>&1; then
            printf 'FORMAT_ERROR %s\n' "$file" | tee -a "$report"
            format_errors=$((format_errors + 1))
        else
            changed=$((changed + 1))
        fi
    fi
done

if [[ "$mode" == cleanup ]]; then
    # Verify Meson's own parser still accepts the whole tree. A generated
    # patch is discarded if any definition becomes invalid.
    if [[ -n "${MESON_PYTHON:-}" ]]; then
        "$MESON_PYTHON" scripts/tests/check-meson-syntax.py >>"$report" 2>&1 || {
            printf '%s\n' 'error: Meson parser rejected the formatted tree' | tee -a "$report" >&2
            : > "$patch"
            exit 1
        }
    fi
    if ! git diff --check -- "${selected[@]}" >>"$report" 2>&1; then
        printf '%s\n' 'error: formatter introduced whitespace errors' | tee -a "$report" >&2
        : > "$patch"
        exit 1
    fi
    if (( parse_errors == 0 && format_errors == 0 )); then
        git diff --binary -- "${selected[@]}" > "$patch"
    else
        : > "$patch"
    fi
fi

total=${#selected[@]}
printf 'Muon %s: checked %s files; parse failures=%s; formatting drift=%s; formatting errors=%s; formatted=%s\n' \
    "$mode" "$total" "$parse_errors" "$format_drift" "$format_errors" "$changed" | tee -a "$report"
if [[ "$mode" == cleanup ]]; then
    if [[ -s "$patch" ]]; then
        printf 'Reviewable cleanup patch: %s\n' "$patch" | tee -a "$report"
    else
        printf '%s\n' 'No validated cleanup patch created.' | tee -a "$report"
    fi
fi

# Style drift is advisory until reviewed baseline normalization. Parsing and
# formatter failures are not advisory and must fail the workflow.
(( parse_errors == 0 && format_errors == 0 ))
