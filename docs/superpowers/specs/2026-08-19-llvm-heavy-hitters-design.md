# LLVM Heavy-Hitter Build Tuning Design

## Goal

Reduce repeat LLVM/Clang/LLD build latency without weakening the PowerPC-only toolchain contract, while adding low-cost correctness hardening and an explicit higher-checking profile.

## Scope

The existing QEMU PowerPC LLVM bootstrap remains the integration point. Do not restructure the LLVM fork, add branches, replace Ninja/CMake, or broaden enabled targets/projects.

## Fast-hardened default

- Keep the existing PowerPC-only target and focused distribution components.
- Disable VCS revision embedding with `LLVM_APPEND_VC_REV=OFF`; the exact LLVM gitlink stays recorded in the WHP toolchain marker, so provenance is preserved without forcing broad relinks after LLVM revision changes.
- Disable the Clang static analyzer with `CLANG_ENABLE_STATIC_ANALYZER=OFF`; OpenBIOS/QEMU cross-compilation does not use `--analyze`, and normal Clang parsing/code generation remain available.
- Set `LLVM_UNREACHABLE_OPTIMIZE=OFF` so an reached `llvm_unreachable()` becomes a deterministic trap rather than optimizer undefined behavior in release builds.
- Bound heavyweight Ninja link concurrency separately from compile concurrency. Expose `POWERPC_LLVM_LINK_JOBS`, defaulting to 2, and feed it to `LLVM_PARALLEL_LINK_JOBS`. Treat it as scheduling policy, not a semantic toolchain-marker input.

## Accuracy profile

Expose `POWERPC_LLVM_ACCURACY_CHECKS=0|1`, default 0. When enabled:

- build Release with `LLVM_ENABLE_ASSERTIONS=ON`;
- enable `LLVM_OPTIMIZED_TABLEGEN=ON` so TableGen runs optimized even though assertions are enabled;
- record the accuracy profile in the semantic toolchain marker so changing it intentionally invalidates the installed compiler once;
- propagate the same assertion setting into the focused standalone LLD build to avoid LLVM/LLD ABI-check mismatches.

Do not enable `LLVM_ENABLE_EXPENSIVE_CHECKS`; that is a separate high-cost validation lane, not an everyday compiler build setting.

## Deferred heavy hitters

Do not enable `LLVM_LINK_LLVM_DYLIB`/`LLVM_BUILD_LLVM_DYLIB` in this pass because it changes runtime deployment and loader behavior. Do not enable LLVM's built-in ccache mode because its default sloppiness includes time-macro handling; cache acceleration needs a separate correctness audit.

## Tests

Add a source-policy regression that requires the fast-hardened CMake flags, validates the two new environment knobs, verifies scheduling-only link jobs are absent from semantic markers, and checks the accuracy profile is propagated into both LLVM and standalone LLD configuration. Add a narrow GitHub Actions workflow for the regression.

## Success criteria

1. Normal builds keep assertions off but gain VCS-relocation avoidance, analyzer pruning, deterministic unreachable traps, and bounded link parallelism.
2. `POWERPC_LLVM_ACCURACY_CHECKS=1` enables Release assertions plus optimized TableGen in both base LLVM and LLD.
3. Changing `POWERPC_LLVM_LINK_JOBS` does not invalidate installed toolchain markers.
4. Existing PowerPC-only target/distribution and incremental C++ optimization policies remain intact.
