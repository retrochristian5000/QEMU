#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Reuse the already-pinned LLVM submodule as the compiler source cache.  This
# avoids asking a local Git repository for partial-clone filtering before the
# established Clang + LLD bootstrap validates and builds that exact revision.
bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-source-cache.sh"

# Keep the established Clang + LLD bootstrap intact, then run the assembler
# migration as its own independently validated stage.  GNU as remains the
# private A/B oracle until LLVM IAS passes qualification and is published.
bash "$SCRIPT_DIR/bootstrap-powerpc-clang-core.sh"
bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-as.sh"
