#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGE="$ROOT/scripts/bootstrap-powerpc-llvm-mc.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

toolchain="$tmp/toolchain"
work="$tmp/work"
mkdir -p "$toolchain/llvm/bin" "$work"

cat > "$toolchain/llvm/bin/clang" <<'CLANG'
#!/usr/bin/env bash
set -euo pipefail
out=""
while (( $# > 0 )); do
    case "$1" in
        -o)
            out="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
[[ -n "$out" ]] || { echo 'fake clang: missing -o' >&2; exit 2; }
: > "$out"
CLANG
chmod +x "$toolchain/llvm/bin/clang"

# Model an ELF reader that keeps writing after the first matching header line.
# grep -q is allowed to close its input early; under pipefail the producer must
# not become the assembler stage's exit status (SIGPIPE is 128 + 13 = 141).
cat > "$toolchain/llvm/bin/llvm-readelf" <<'READELF'
#!/usr/bin/env bash
exec python3 - <<'PY'
import signal
import sys
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
sys.stdout.write("  Class:                             ELF32\n")
sys.stdout.write("  Data:                              2's complement, big endian\n")
sys.stdout.write("  Machine:                           PowerPC\n")
for _ in range(20000):
    sys.stdout.write("  padding: assembler qualification output\n")
PY
READELF
chmod +x "$toolchain/llvm/bin/llvm-readelf"

set +e
output="$(
    POWERPC_TOOLCHAIN_DIR="$toolchain" \
    POWERPC_TOOLCHAIN_WORK_DIR="$work" \
        bash "$STAGE" 2>&1
)"
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
    printf '%s\n' \
        "error: LLVM MC assembler qualification failed with status $status" \
        "$output" >&2
    exit 1
fi

[[ -x "$toolchain/bin/powerpc-elf-as" ]]
grep -Fq 'ASSEMBLER=clang-integrated-mc' "$toolchain/.whp-powerpc-as"
grep -Fq 'OBJECT_ABI=ELF32-powerpc-big-endian' "$toolchain/.whp-powerpc-as"

printf 'PowerPC LLVM MC pipefail qualification: verified\n'
