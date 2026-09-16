# Selectable QEMU C Standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent menuconfig choice for the top-level QEMU C standard and propagate it to Meson's `c_std` without silently downgrading unsupported compilers.

**Architecture:** Reuse the existing typed WHP `.whpconfig` option table and portable build planner. `QEMU_C_STANDARD` is validated as a choice and translated to one `-Dc_std=<value>` configure argument; QEMU configure already passes `-D...` options to Meson. Compatibility shims remain a policy boundary for future subsystem migration and do not fake unsupported C23 syntax.

**Tech Stack:** Python 3, WHP configuration/menu tools, QEMU configure, Meson built-in `c_std` option.

**Spec:** `docs/superpowers/specs/2026-09-16-selectable-c-standard-design.md`

## Global Constraints

- Supported values are exactly `gnu11`, `gnu17`, and `gnu23`.
- Initial default is `gnu11`.
- There is no `auto` C-standard value.
- The setting applies only to the top-level QEMU host C build.
- Do not inject `-std=` through CFLAGS or per-directory source sets.
- Do not silently downgrade the selected standard.
- Bundled subprojects keep their own declared C standards.
- Compatibility shims may cover equivalent APIs/macros/attributes but may not emulate syntax an older compiler cannot parse.

---

### Task 1: Configuration contract

**Files:**
- Modify: `scripts/whp-config/config.py`
- Test: `scripts/tests/test-whp-config.py`

**Interfaces:**
- Consumes: existing `Option` choice validation and `.whpconfig` persistence.
- Produces: `QEMU_C_STANDARD` value in the resolved WHP configuration.

- [ ] **Step 1: Write the failing configuration tests**

Add assertions that `QEMU_C_STANDARD` is a `Host features` choice with default `gnu11` and choices `('gnu11', 'gnu17', 'gnu23')`; verify `gnu23` persists and an invalid value is rejected.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 scripts/tests/test-whp-config.py`

Expected: failure because `QEMU_C_STANDARD` does not yet exist.

- [ ] **Step 3: Add the minimal option**

Add:

```python
Option(
    'QEMU_C_STANDARD',
    'Host features',
    'QEMU C language standard',
    'choice',
    'gnu11',
    ('gnu11', 'gnu17', 'gnu23'),
),
```

to `OPTIONS` near the other host compiler/build controls.

- [ ] **Step 4: Re-run the focused test and verify GREEN**

Run: `python3 scripts/tests/test-whp-config.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/whp-config/config.py scripts/tests/test-whp-config.py
git commit -m "build: add selectable QEMU C standard"
```

### Task 2: Meson propagation contract

**Files:**
- Modify: `scripts/whp-build/portable-build.py`
- Create: `scripts/tests/test-c-standard-config.py`

**Interfaces:**
- Consumes: `resolved_values()['QEMU_C_STANDARD']`.
- Produces: exactly one `-Dc_std=<value>` entry in the QEMU configure argument list.

- [ ] **Step 1: Write the failing propagation test**

Create a focused Python test that imports the WHP config/build modules, resolves a temporary/configured C-standard selection, obtains the QEMU configure argument list through the existing build-plan interface, and asserts:

```python
assert '-Dc_std=gnu11' in configure_args
assert configure_args.count('-Dc_std=gnu11') == 1
```

Repeat with an environment override of `gnu23` and assert exactly one `-Dc_std=gnu23`. Also assert no configure argument begins with `--extra-cflags=-std=`.

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 scripts/tests/test-c-standard-config.py`

Expected: failure because the portable build plan does not yet emit `-Dc_std=`.

- [ ] **Step 3: Add the minimal propagation**

At the point where `portable-build.py` constructs QEMU configure arguments, append:

```python
configure_args.append(f"-Dc_std={values['QEMU_C_STANDARD']}")
```

Keep this independent from `--extra-cflags=-O...` and all firmware/toolchain flags.

- [ ] **Step 4: Re-run the focused test and verify GREEN**

Run: `python3 scripts/tests/test-c-standard-config.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/whp-build/portable-build.py scripts/tests/test-c-standard-config.py
git commit -m "build: pass selected C standard to Meson"
```

### Task 3: Menu/documentation regression coverage

**Files:**
- Modify: `docs/devel/whp-build-orchestration.rst`
- Modify: `scripts/tests/test-whp-config.py` or `scripts/tests/test-c-standard-config.py` only if documentation/menu coverage needs a direct assertion.

**Interfaces:**
- Consumes: `QEMU_C_STANDARD` configuration contract.
- Produces: documented user-facing behavior and shim boundary.

- [ ] **Step 1: Add documentation assertions if existing WHP tests validate documented menu options**

Assert the documentation names `QEMU_C_STANDARD`, lists `gnu11`, `gnu17`, and `gnu23`, and states that unsupported selected dialects fail rather than silently downgrade.

- [ ] **Step 2: Run the focused test and verify RED if an assertion was added**

Run the specific WHP configuration test containing the documentation assertion.

Expected: failure until documentation is updated.

- [ ] **Step 3: Document the option and compatibility policy**

Explain that `./build.sh menuconfig` controls the top-level QEMU C dialect, the default remains GNU C11 during migration, GNU C23 is selectable for subsystem audits, subprojects retain their own standards, and compatibility shims cannot make a compiler parse unsupported C23 syntax.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
python3 scripts/tests/test-whp-config.py
python3 scripts/tests/test-c-standard-config.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/devel/whp-build-orchestration.rst scripts/tests/test-whp-config.py scripts/tests/test-c-standard-config.py
git commit -m "docs: document selectable C standard policy"
```

### Task 4: Final verification

**Files:**
- No production changes unless verification exposes a defect.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: evidence that the configuration path is internally consistent.

- [ ] **Step 1: Run focused tests**

```bash
python3 scripts/tests/test-whp-config.py
python3 scripts/tests/test-c-standard-config.py
```

Expected: both PASS.

- [ ] **Step 2: Run broader WHP build-config tests available in the checkout**

```bash
python3 scripts/tests/test-host-optimization.py
python3 scripts/tests/test-mold-config.py
```

Expected: PASS.

- [ ] **Step 3: Inspect generated configure arguments**

Confirm that `gnu11`, `gnu17`, and `gnu23` each produce exactly one matching `-Dc_std=` argument and never a `--extra-cflags=-std=` argument.

- [ ] **Step 4: Record build limitation honestly**

A full C23 QEMU compile is not part of this configuration feature verification. It begins the subsequent subsystem migration, starting with `hw/display`.
