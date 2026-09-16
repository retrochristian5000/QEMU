# Selectable QEMU C Standard Design

## Goal

Make the QEMU host C language standard a persistent WHP build-profile choice while preserving deterministic builds and allowing carefully scoped compatibility shims for older compilers and C libraries.

## Configuration model

Add `QEMU_C_STANDARD` to the existing WHP `.whpconfig` option table as a validated choice under `Host features`.

Supported values initially are:

- `gnu11`
- `gnu17`
- `gnu23`

The initial default remains `gnu11` so the repository does not silently change dialect before subsystem audits are complete. Users can select `gnu23` immediately for migration testing. There is deliberately no `auto` value: identical source/configuration should not silently select different language standards on different hosts.

Environment overrides continue to use the existing `.whpconfig` precedence and validation path.

## Build propagation

`QEMU_C_STANDARD` is the single WHP source of truth for the QEMU host C dialect.

`portable-build.py` translates the selected value into the Meson built-in project option by appending:

`-Dc_std=<selected-value>`

to QEMU's configure invocation. QEMU's configure already passes `-D...` arguments through to Meson, so no compiler flag injection is needed.

Do not add `-std=` to `CFLAGS`, per-directory Meson source sets, firmware builds, bootstrap compilers, or third-party subprojects.

## Scope boundary

The selection applies to the top-level QEMU project only. Bundled subprojects that declare their own C standard remain authoritative for themselves until audited independently.

Objective-C, C++, Rust, firmware, and cross-toolchain language standards are outside this setting.

## Compatibility-shim policy

Retrocomputing users may intentionally build with older compilers. Compatibility support is allowed when it preserves the selected dialect's semantics without lying about compiler capabilities.

Rules:

1. If `QEMU_C_STANDARD=gnu23` is selected, the selected C compiler must actually accept GNU C23. The build must fail clearly if it cannot parse that language standard.
2. Do not silently downgrade `gnu23` to `gnu17` or `gnu11`.
3. Shims may provide missing library facilities, attributes, typedef conveniences, or helper macros where equivalent behavior can be implemented safely.
4. Shims must not attempt to emulate syntax the compiler cannot parse.
5. Prefer existing QEMU/GLib portability abstractions before adding a new shim.
6. Every new shim requires a capability test and a narrow scope; compiler-version guesses are a fallback only when no feature test is possible.
7. Shims must not change guest-visible ABI, device layout, migration format, wire format, or host pointer semantics.

## Migration strategy

Use `gnu23` through menuconfig while auditing subsystems, beginning with `hw/display`. Fix genuine C23 incompatibilities and shared-header blockers incrementally. Once the major QEMU host-code subsystems and supported host compilers are clean, changing the default from `gnu11` to `gnu23` becomes a separate deliberate change.

## Tests

Add focused tests that prove:

- `QEMU_C_STANDARD` exists in the WHP menu with exactly the supported values and `gnu11` default.
- valid values persist through `.whpconfig` parsing.
- invalid values are rejected.
- environment overrides are normalized/validated through the existing configuration path.
- the portable build plan emits exactly one `-Dc_std=<value>` argument for the selected standard.
- the C-standard choice does not inject `-std=` into generic CFLAGS or alter subproject configuration.

## Non-goals

- Upgrading all QEMU sources to C23 in this change.
- Rewriting third-party subprojects to C23.
- Providing a fake C23 mode for compilers that cannot parse C23.
- Selecting a dialect automatically from compiler version.
