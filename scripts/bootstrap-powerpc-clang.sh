#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Keep the established Clang + LLD bootstrap intact, then run the assembler
# migration as its own independently validated stage.  This preserves GNU as
# until LLVM IAS has passed its qualification test.
bash "$SCRIPT_DIR/bootstrap-powerpc-clang-core.sh"
bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-as.sh"
