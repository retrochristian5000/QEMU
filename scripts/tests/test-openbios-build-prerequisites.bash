#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/whp-build/gnu-make.bash"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/openbios-prerequisites.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/bin" "$scratch/tool dir"

cat > "$scratch/bin/make" <<'SH'
#!/bin/sh
printf '%s\n' 'bmake-20200710'
SH
chmod +x "$scratch/bin/make"
cat > "$scratch/bin/gmake" <<'SH'
#!/bin/sh
printf '%s\n' 'GNU Make 4.4.1'
SH
chmod +x "$scratch/bin/gmake"

resolved="$(PATH="$scratch/bin" whp_find_gnu_make)"
[[ "$resolved" == "$scratch/bin/gmake" ]]

rm -f "$scratch/bin/gmake"
if PATH="$scratch/bin" whp_find_gnu_make >/dev/null 2>&1; then
    printf 'error: BSD make was accepted as GNU Make\n' >&2
    exit 1
fi

cat > "$scratch/tool dir/make" <<'SH'
#!/bin/sh
printf '%s\n' 'GNU Make 3.82'
SH
chmod +x "$scratch/tool dir/make"
resolved="$(whp_resolve_gnu_make "$scratch/tool dir/make")"
[[ "$resolved" == "$scratch/tool dir/make" ]]

python3 - "$ROOT/scripts/whp-build/portable-build.py" "$scratch" <<'PY'
import importlib.util
import os
import pathlib
import sys

module_path = pathlib.Path(sys.argv[1])
scratch = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('whp_portable_build_test', module_path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for name in ('NINJA_CMD', 'NINJA', 'MAKE_CMD', 'MAKE'):
    os.environ.pop(name, None)
os.environ['PATH'] = str(scratch / 'bin')

bsd_make = scratch / 'bin' / 'make'
gnu_make = scratch / 'bin' / 'gmake'
gnu_make.write_text('#!/bin/sh\nprintf "%s\\n" "GNU Make 4.4.1"\n', encoding='utf-8')
gnu_make.chmod(0o755)
assert module.select_runner() == [str(gnu_make)]

gnu_make.unlink()
try:
    module.select_runner()
except RuntimeError as exc:
    assert 'GNU Make' in str(exc)
else:
    raise AssertionError('portable runner accepted BSD make')

os.environ['MAKE_CMD'] = str(bsd_make)
try:
    module.select_runner()
except RuntimeError as exc:
    assert 'GNU Make' in str(exc)
else:
    raise AssertionError('portable runner accepted explicit BSD make')
PY

for script in \
    "$ROOT/scripts/build-openbios.sh" \
    "$ROOT/scripts/meson-build-openbios.sh"; do
    grep -Fq 'https://github.com/retrochristian5000/fcode-utils.git' "$script"
    grep -Fq '1815c48e38e1e126564cf61b43a5f29a22cac696' "$script"
done

printf 'OpenBIOS build prerequisites: verified\n'
