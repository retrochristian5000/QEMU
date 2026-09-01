#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

submodule_name='toolchains/python-runtime'
[[ "$(git config -f .gitmodules --get "submodule.${submodule_name}.path" || true)" == "$submodule_name" ]]
[[ "$(git config -f .gitmodules --get "submodule.${submodule_name}.url" || true)" == 'https://github.com/retrochristian5000/Python.git' ]]
[[ "$(git config -f .gitmodules --get "submodule.${submodule_name}.branch" || true)" == main ]]

gitlink="$(git ls-tree HEAD -- "$submodule_name")"
read -r gitlink_mode gitlink_type expected_revision gitlink_path <<< "$gitlink"
if [[ "$gitlink_mode" != 160000 || "$gitlink_type" != commit ||
      ! "$expected_revision" =~ ^[0-9a-f]{40}$ ||
      "$gitlink_path" != "$submodule_name" ]]; then
    printf 'error: Python runtime is not registered as a pinned gitlink: %s\n' \
        "${gitlink:-<missing>}" >&2
    exit 1
fi

git submodule update --init --depth 1 "$submodule_name"
actual_revision="$(git -C "$submodule_name" rev-parse HEAD)"
[[ "$actual_revision" == "$expected_revision" ]] || {
    printf 'error: Python gitlink mismatch: %s != %s\n' \
        "$actual_revision" "$expected_revision" >&2
    exit 1
}

cache_root="${RUNNER_TEMP:-$(mktemp -d)}/whp-python-bootstrap"
rm -rf "$cache_root"

python_path="$(
    WHP_PYTHON_BOOTSTRAP_DIR="$cache_root" JOBS="${JOBS:-2}" \
        /bin/sh scripts/bootstrap-python.sh
)"
[[ -x "$python_path" ]] || {
    printf 'error: bundled Python bootstrap returned a non-executable: %s\n' \
        "$python_path" >&2
    exit 1
}
"$python_path" -c '
from pathlib import Path
import ensurepip
import sys
import tomllib
import venv
assert sys.version_info >= (3, 9)
assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve(), (sys.prefix, sys.argv[1])
' "$cache_root"

marker="$cache_root/.whp-python-runtime"
[[ -f "$marker" ]]
grep -Eq '^BOOTSTRAP_CC=.+$' "$marker"
grep -Eq '^BOOTSTRAP_CC_VERSION=.+$' "$marker"

python_path_reused="$(
    WHP_PYTHON_BOOTSTRAP_DIR="$cache_root" JOBS="${JOBS:-2}" \
        /bin/sh scripts/bootstrap-python.sh
)"
[[ "$python_path_reused" == "$python_path" ]] || {
    printf 'error: bundled Python cache path changed: %s != %s\n' \
        "$python_path_reused" "$python_path" >&2
    exit 1
}

printf 'real bundled Python bootstrap test: passed (%s)\n' "$python_path"
