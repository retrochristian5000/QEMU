# LLVM Heavy-Hitter Build Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce repeat PowerPC LLVM/Clang/LLD build latency while adding low-cost release hardening and an opt-in assertion-checked accuracy profile.

**Architecture:** Keep the existing persistent CMake/Ninja build directories and PowerPC-only distribution. Add a fast-hardened CMake policy to the base LLVM bootstrap, propagate output-affecting accuracy settings into the LLD stage, and keep link-pool scheduling out of semantic toolchain markers.

**Tech Stack:** Bash, CMake, Ninja, LLVM/Clang/LLD, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-08-19-llvm-heavy-hitters-design.md`

## Global Constraints

- Work directly on `master`; never generate branches.
- Preserve the existing PowerPC-only target and distribution components.
- Keep `POWERPC_LLVM_CXX_OPTIMIZATION=-O1` as the default incremental C++ optimization policy.
- Do not enable LLVM dylib linking or LLVM's built-in ccache mode in this pass.
- Do not claim a complete LLVM build passes without an observed full build or hosted CI result.

---

### Task 1: Add a heavy-hitter regression guard

**Files:**
- Create: `scripts/tests/test-powerpc-llvm-heavy-hitters.bash`

**Interfaces:**
- Consumes: `scripts/bootstrap-powerpc-clang-base.sh`, `scripts/bootstrap-powerpc-clang-core.sh`
- Produces: source-policy assertions for the fast-hardened and accuracy profiles

- [ ] **Step 1: Write the failing test**

Require the base bootstrap to contain:

```bash
LLVM_ACCURACY_CHECKS="${POWERPC_LLVM_ACCURACY_CHECKS:-0}"
LLVM_LINK_JOBS="${POWERPC_LLVM_LINK_JOBS:-2}"
-DLLVM_APPEND_VC_REV=OFF
-DCLANG_ENABLE_STATIC_ANALYZER=OFF
-DLLVM_UNREACHABLE_OPTIMIZE=OFF
-DLLVM_PARALLEL_LINK_JOBS="$LLVM_LINK_JOBS"
-DLLVM_ENABLE_ASSERTIONS="$llvm_enable_assertions"
-DLLVM_OPTIMIZED_TABLEGEN="$llvm_optimized_tablegen"
```

Require the semantic marker to record the accuracy profile but not link-job scheduling. Require the LLD bootstrap to read and apply the same assertion mode.

- [ ] **Step 2: Run the guard against the pre-change source**

Run:

```bash
bash scripts/tests/test-powerpc-llvm-heavy-hitters.bash
```

Expected: non-zero because the new profile variables and CMake flags do not yet exist.

- [ ] **Step 3: Commit the red regression**

```bash
git add scripts/tests/test-powerpc-llvm-heavy-hitters.bash
git commit -m "test: guard LLVM heavy-hitter build policy"
```

### Task 2: Implement the base LLVM fast-hardened and accuracy profiles

**Files:**
- Modify: `scripts/bootstrap-powerpc-clang-base.sh`

**Interfaces:**
- Consumes: `POWERPC_LLVM_ACCURACY_CHECKS=0|1`, `POWERPC_LLVM_LINK_JOBS=<positive integer>`
- Produces: CMake args and marker fields `LLVM_ACCURACY_CHECKS`, `LLVM_ENABLE_ASSERTIONS`, `LLVM_OPTIMIZED_TABLEGEN`

- [ ] **Step 1: Validate the new knobs**

Use exact 0/1 validation for accuracy checks and positive-integer validation for link jobs.

- [ ] **Step 2: Derive CMake booleans**

```bash
llvm_enable_assertions=OFF
llvm_optimized_tablegen=OFF
if [[ "$LLVM_ACCURACY_CHECKS" == 1 ]]; then
    llvm_enable_assertions=ON
    llvm_optimized_tablegen=ON
fi
```

- [ ] **Step 3: Add the fast-hardened CMake flags**

Add:

```bash
-DLLVM_APPEND_VC_REV=OFF
-DCLANG_ENABLE_STATIC_ANALYZER=OFF
-DLLVM_UNREACHABLE_OPTIMIZE=OFF
-DLLVM_PARALLEL_LINK_JOBS="$LLVM_LINK_JOBS"
-DLLVM_ENABLE_ASSERTIONS="$llvm_enable_assertions"
-DLLVM_OPTIMIZED_TABLEGEN="$llvm_optimized_tablegen"
```

- [ ] **Step 4: Update the semantic marker**

Bump `BOOTSTRAP_SCHEMA` and record the accuracy/assertion/TableGen mode. Do not record `LLVM_LINK_JOBS` because it is scheduling-only.

- [ ] **Step 5: Run the regression guard**

```bash
bash scripts/tests/test-powerpc-llvm-heavy-hitters.bash
```

Expected: still non-zero until the LLD propagation is implemented.

### Task 3: Propagate the accuracy profile into standalone LLD

**Files:**
- Modify: `scripts/bootstrap-powerpc-clang-core.sh`

**Interfaces:**
- Consumes: base marker `LLVM_ENABLE_ASSERTIONS`, `LLVM_OPTIMIZED_TABLEGEN`
- Produces: matching standalone LLD CMake configuration and marker fingerprint

- [ ] **Step 1: Read accuracy fields from the completed base marker**

Parse `LLVM_ENABLE_ASSERTIONS` and `LLVM_OPTIMIZED_TABLEGEN`; fail if either is absent.

- [ ] **Step 2: Pass the assertion mode to LLD**

Add the matching `-DLLVM_ENABLE_ASSERTIONS=<ON|OFF>` to the LLD CMake configuration. Keep TableGen out of standalone LLD unless the standalone project consumes it.

- [ ] **Step 3: Record the assertion mode in the LLD marker**

Bump `LLD_SCHEMA` and add `LLVM_ENABLE_ASSERTIONS=<ON|OFF>`. Continue to exclude link-job scheduling from semantic markers.

- [ ] **Step 4: Run the regression guard**

```bash
bash scripts/tests/test-powerpc-llvm-heavy-hitters.bash
```

Expected: exit 0 with `PowerPC LLVM heavy-hitter policy: verified`.

### Task 4: Add CI and verify the final diff

**Files:**
- Create: `.github/workflows/powerpc-llvm-heavy-hitters.yml`

**Interfaces:**
- Consumes: the regression shell
- Produces: hosted source-policy guard on `master`

- [ ] **Step 1: Add a focused workflow**

Use Ubuntu 24.04, checkout, `bash -n` for the test and both bootstrap scripts, then execute the regression test. Trigger only on the two bootstrap scripts, the regression, and the workflow.

- [ ] **Step 2: Fresh verification**

Run or reproduce:

```bash
bash -n scripts/bootstrap-powerpc-clang-base.sh
bash -n scripts/bootstrap-powerpc-clang-core.sh
bash -n scripts/tests/test-powerpc-llvm-heavy-hitters.bash
bash scripts/tests/test-powerpc-llvm-heavy-hitters.bash
```

- [ ] **Step 3: Review the commit range**

Verify the effective diff contains only the design/plan, regression/workflow, and the two bootstrap scripts. Confirm no submodule pointer changed.

- [ ] **Step 4: Report residual gap**

If no full LLVM build or hosted workflow run is observable, report verification as partial and do not infer a complete-build pass.
