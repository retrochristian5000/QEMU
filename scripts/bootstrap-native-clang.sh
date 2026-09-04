#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_name=${0##*/}
bash_name=${script_name%.sh}.bash
bash_runner=${WHP_BUILD_BASH:-}
if [ -z "$bash_runner" ]; then
    bash_runner=$(command -v bash 2>/dev/null || true)
fi
if [ -z "$bash_runner" ]; then
    printf 'error: GNU Bash is required for %s\n' "$script_name" >&2
    exit 1
fi
exec "$bash_runner" "$script_dir/$bash_name" "$@"
