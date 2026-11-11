#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

if git -C "$ROOT" grep -n -F 'g_autoptr(Error)' -- \
    '*.c' '*.h' '*.m' '*.mm' \
    ':(exclude)include/qapi/error.h'; then
    printf '%s\n' \
        'error: QEMU Error objects must not use g_autoptr(Error).' \
        'Use Error * and explicit error_free()/error_free_or_abort() ownership.' >&2
    exit 1
fi

printf 'QEMU Error autoptr guard: passed\n'
