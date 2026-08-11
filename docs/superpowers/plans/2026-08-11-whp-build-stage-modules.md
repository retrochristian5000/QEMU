# WHP Build Stage Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the WHP build-stage monolith into focused modules without changing public build behavior.

**Architecture:** Keep `scripts/whp-build/stages.bash` as the stable loader and move each existing public stage, unchanged, into one responsibility-specific sourced module. Extend preflight and focused tests so missing modules or broken loader contracts fail before a build starts.

**Tech Stack:** GNU Bash 3.2+, QEMU shell build wrappers, GitHub Actions YAML, QEMU checkpatch.

## Global Constraints

- `build.sh` and `builder.sh` remain the only public build entry points.
- Stage order remains prepare build, prepare sources, configure, build targets, post-build verification.
- Existing environment variables, configure arguments, and defaults do not change.
- New module files remain mode `100644` and are sourced, not executed.
- No branch creation; publish only a verified non-forced fast-forward to `master`.

---

### Task 1: Characterize the stage-loader contract

**Files:**
- Create: `scripts/tests/test-whp-build-stage-loading.bash`

**Interfaces:**
- Consumes: `SOURCE_DIR`, `scripts/whp-build/stages.bash`.
- Produces: a focused check for `whp_prepare_build`, `whp_prepare_sources`, `whp_configure_build`, and `whp_build_targets`.

- [ ] **Step 1: Add the characterization test**

Source the current loader in a clean Bash process and use `declare -F` to
require each public stage function.  Reject unexpected executable bits on the
loader and implementation modules.

- [ ] **Step 2: Run the test against the monolith**

Run: `bash scripts/tests/test-whp-build-stage-loading.bash`

Expected: PASS, establishing the public loader behavior before file movement.

### Task 2: Split the stage implementation

**Files:**
- Modify: `scripts/whp-build/stages.bash`
- Create: `scripts/whp-build/prepare-build.bash`
- Create: `scripts/whp-build/prepare-sources.bash`
- Create: `scripts/whp-build/configure.bash`
- Create: `scripts/whp-build/build-targets.bash`

**Interfaces:**
- Consumes: the exact existing function bodies and shared shell variables.
- Produces: the same four public functions through the stable loader path.

- [ ] **Step 1: Move functions by responsibility**

Move helpers plus `whp_prepare_build` to `prepare-build.bash`, then move the
remaining three stage functions to their correspondingly named modules.  Do
not change function bodies during the move.

- [ ] **Step 2: Turn `stages.bash` into the ordered loader**

Retain its Bash and `SOURCE_DIR` guards, then source the four modules using
absolute paths beneath `$SOURCE_DIR/scripts/whp-build`.

- [ ] **Step 3: Re-run the characterization test**

Run: `bash scripts/tests/test-whp-build-stage-loading.bash`

Expected: PASS with all four functions loaded from the new structure.

### Task 3: Make preflight and documentation match the structure

**Files:**
- Modify: `scripts/whp-build/preflight.bash`
- Modify: `docs/devel/shell-build-policy.rst`
- Modify: `docs/devel/whp-build-orchestration.rst`
- Modify: `docs/devel/openbios-meson-bootstrap.rst`

**Interfaces:**
- Consumes: the new module list.
- Produces: early syntax validation and accurate developer documentation.

- [ ] **Step 1: Register every module in preflight**

Add the four new non-executable Bash modules to `bash_scripts` so a missing or
invalid file fails before the build begins.

- [ ] **Step 2: Update documentation references**

Describe `stages.bash` as the compatibility loader and name the focused module
that owns each stage.

- [ ] **Step 3: Run wrapper checks**

Run:

```bash
bash scripts/tests/test-whp-build-stage-loading.bash
bash scripts/tests/test-macos-sdk-selection.bash
WHP_SHELL_PROBE_ONLY=1 ./build.sh
```

Expected: all commands exit 0.

### Task 4: Repair source hygiene and verify publication

**Files:**
- Modify: `hw/i386/x86-16bit.c`
- Modify: `tests/qtest/x86-16bit-test.c`

**Interfaces:**
- Consumes: QEMU's SPDX header convention.
- Produces: checkpatch-compliant headers without executable-code changes.

- [ ] **Step 1: Replace license boilerplate with SPDX identifiers**

Use the license identifiers established by neighboring QEMU machine and qtest
files; do not edit executable statements.

- [ ] **Step 2: Run fresh static verification**

Run checkpatch on the cleanup commit, `git diff --check`, parse
`.github/workflows/ci.yml`, and syntax-check all wrapper scripts.

- [ ] **Step 3: Commit and publish**

Commit the reviewed cleanup, fetch remote `master`, require the verified
parent, publish with `force: false`, synchronize the local ref, and inspect the
hosted Linux and macOS CI results.
