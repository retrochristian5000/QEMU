# WHP Build Stage Modules Design

## Goal

Make the WHP build wrapper easier to understand and maintain by replacing the
single 515-line `scripts/whp-build/stages.bash` implementation with focused
stage modules.  This is a structural refactor: `build.sh`, `builder.sh`, their
environment variables, stage order, configure arguments, and build results
must remain unchanged.

## Structure

`scripts/whp-build/stages.bash` remains the compatibility loader used by
`builder.sh` and existing tests.  It sources four implementation modules in
execution order:

- `prepare-build.bash` owns host/toolchain policy and `whp_prepare_build`.
- `prepare-sources.bash` owns submodule, compiler-probe, and OpenBIOS setup.
- `configure.bash` owns the configuration identity manifest and configure run.
- `build-targets.bash` owns compilation and optional installation.

Helpers stay with the only stage that consumes them.  All modules execute in
the same Bash process, preserving the current shared-variable contract.

## Compatibility and Failure Handling

The loader validates that it is running in GNU Bash and that `SOURCE_DIR` is
set before it sources any module.  Each module remains non-executable and is
loaded only through `stages.bash`.  A missing or syntactically invalid module
must fail during the existing preflight rather than partway through a build.

The two C files added with the 16-bit x86 target will also receive the QEMU
SPDX header form required by `checkpatch`; no executable C statements change.

## Verification

A focused shell test will source the loader and assert that the four public
stage functions are available.  Existing SDK-selection coverage will exercise
`whp_prepare_build` through the loader.  The complete build-wrapper syntax
preflight, shell probe, workflow YAML parse, checkpatch, and diff checks must
all pass.  Hosted CI remains the compilation and native macOS evidence because
this local environment lacks QEMU's GLib development dependencies.

## Non-goals

- No changes to build defaults, platform policy, dependencies, or targets.
- No split of `.github/workflows/ci.yml` in this pass.
- No redesign of OpenBIOS bootstrap or post-build artifact validation.
- No changes to 8086/8088 emulation semantics.
