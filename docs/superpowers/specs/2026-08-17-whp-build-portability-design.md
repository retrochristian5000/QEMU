# WHP Build Portability Design

Date: 2026-08-17
Status: Approved design
Scope: WHP-owned build wrapper and integration policy around QEMU

## Goal

The WHP build layer must preserve QEMU's host-build envelope instead of narrowing it by default.

The central invariant is:

> If core QEMU can build on a host with its documented prerequisites, the WHP public build path must not fail solely because an optional WHP feature, desktop/audio integration, firmware helper, installation path, or shell-specific helper is unavailable.

WHP features may add capabilities. They must not make an otherwise viable QEMU host unbuildable unless the user explicitly requests a feature whose prerequisites are missing.

## Supported-host policy

The WHP wrapper follows QEMU's supported host policy rather than maintaining a smaller private host list. In particular, the wrapper must remain viable on QEMU-supported Linux, macOS, FreeBSD, NetBSD, OpenBSD, and 64-bit Windows/MinGW via MSYS2, while avoiding assumptions that unnecessarily block comparable unlisted hosts.

Host detection in the WHP layer is used only for WHP policy that genuinely differs by host. QEMU's own configure/Meson detection remains authoritative for whether QEMU itself supports the host CPU, OS, compiler, and accelerator combination.

## Architecture

### 1. Public launcher

`build.sh` remains a small POSIX `/bin/sh` entry point.

Its responsibilities are limited to:

- locating a supported Python interpreter;
- loading the portable WHP user configuration;
- preserving explicit environment overrides;
- selecting the portable WHP build driver;
- invoking host-specific adapters only when the selected configuration requires them.

The public launcher must not require GNU Bash merely to perform a core QEMU build.

### 2. Portable orchestration core

A lightweight Python driver owns host-neutral orchestration. Python is chosen because QEMU already requires Python 3.9 or newer, so this does not add a new baseline runtime beyond QEMU's own build requirements.

The portable core owns:

- option resolution;
- `auto` / `enabled` / `disabled` state handling;
- build-directory and install-prefix defaults;
- CPU-count detection;
- subprocess argument construction without shell word splitting;
- capability probing for optional WHP features;
- configure argument assembly;
- generic build execution;
- generic artifact verification;
- dispatch to optional Bash adapters.

It must not duplicate QEMU's full host-OS or host-CPU support tables.

### 3. Bash feature adapters

Existing Bash-heavy functionality remains isolated behind feature boundaries instead of being rewritten merely for stylistic portability.

Bash remains acceptable for:

- OpenBIOS build integration;
- PowerPC LLVM toolchain bootstrap;
- GNU PowerPC compatibility bootstrap;
- macOS SDK/compiler policy;
- macOS GTK environment repair;
- firmware-specific validation.

These helpers are invoked only when the selected feature requires them. Missing Bash is therefore a feature-level limitation, not a core-QEMU build failure.

## Option semantics

Optional features use a three-state model where appropriate:

- `auto`: use the feature when prerequisites are available; otherwise skip it cleanly;
- `y`: require the feature and fail with a precise feature-specific error if prerequisites are missing;
- `n`: disable the feature and do not probe or prepare its prerequisites.

Boolean-only options remain only where absence cannot reasonably degrade into a valid build.

The first options to adopt three-state semantics are:

- `BUILD_OPENBIOS`;
- `BOOTSTRAP_POWERPC_TOOLCHAIN`;
- optional host UI/audio integrations where QEMU already supports autodetection.

## Core build defaults

### Installation

Compilation is the default operation. Installation is opt-in.

- `INSTALL` defaults to `0` / disabled.
- `PREFIX=auto` resolves to a user-writable location such as `$HOME/.local/whp-qemu` when a usable home directory exists.
- If no usable home directory exists, the fallback prefix is build-local and writable by the current user.
- No normal non-root build defaults to `/emulator` or another root-owned top-level path.

An explicit user `PREFIX` always wins.

### UI and audio

The generic non-macOS path must not unconditionally add `--enable-gtk` or `--enable-pa`.

For optional UI/audio backends:

- `auto` means leave the feature to QEMU/Meson autodetection unless WHP has a host-specific reason to probe it first;
- `y` adds the explicit QEMU enable option and missing dependencies are fatal;
- `n` adds the explicit disable option.

macOS Cocoa, CoreAudio, GTK, and PulseAudio follow the same semantic rule even if macOS-specific preparation remains in an adapter.

### Compiler flags

The WHP layer must not inject broad default compiler flags such as `-g0 -pipe -w` into every host build.

User-provided flags are preserved. QEMU/Meson defaults remain authoritative unless a WHP feature has a narrowly documented requirement.

Feature-specific flags must be scoped to that feature and must not leak into firmware or build-machine toolchains.

## OpenBIOS behavior

`BUILD_OPENBIOS=auto` is non-fatal to the core QEMU build.

In `auto` mode, the driver may enable OpenBIOS integration when its prerequisites are available. Missing Bash, unavailable firmware bootstrap prerequisites, unavailable writable source state, or another OpenBIOS-only prerequisite causes the feature to be skipped with a concise diagnostic, not a core build failure.

`BUILD_OPENBIOS=y` is strict. If OpenBIOS cannot be prepared, configuration stops with a precise OpenBIOS error.

`BUILD_OPENBIOS=n` performs no OpenBIOS source preparation, toolchain bootstrap, or firmware validation.

The existing LLVM-only Clang lane remains the default firmware compiler lane when OpenBIOS is enabled. The explicit GNU compatibility lane remains available.

## PowerPC toolchain bootstrap behavior

Toolchain bootstrap is feature-scoped rather than a universal prerequisite.

In `auto` mode:

1. prefer a valid explicitly supplied cross toolchain;
2. otherwise use an already prepared WHP toolchain if valid;
3. otherwise bootstrap only if the selected firmware lane and its host prerequisites are viable;
4. otherwise decline the optional firmware feature cleanly.

In `y` mode, inability to bootstrap is fatal.

In `n` mode, no bootstrap is attempted.

## Source-tree mutation policy

Routine builds must not require writes to tracked source directories.

The current generated PPC preset must no longer be written to `configs/devices/ppc-softmmu/whp-user.mak` as a normal build side effect.

Policy:

- when WHP device selections match tracked defaults, use the tracked preset directly;
- custom generated configuration lives under the build directory or another generated-data location;
- if QEMU's `--with-devices-ARCH=NAME` interface requires a source-tree file for a custom preset, the implementation must either use an equivalent build-local mechanism or make the source mutation an explicit compatibility fallback, never the silent normal path;
- read-only source trees must remain valid for ordinary core builds.

## Host tools and job count

Portable host mechanics move to Python where possible.

CPU-count selection uses Python's `os.cpu_count()` with a minimum fallback of one job. The wrapper does not depend on `nproc` or a particular `sysctl` spelling for correctness.

GNU Make remains required only where QEMU or a selected WHP helper actually requires it. Tool selection should prefer an explicitly configured command, then a suitable discovered implementation.

No host tool is considered globally mandatory merely because one optional WHP feature uses it.

## Configuration data flow

`.whpconfig` remains the user-owned portable policy file.

Precedence is:

1. explicit one-run environment variables;
2. saved `.whpconfig` values;
3. host-neutral WHP defaults;
4. QEMU/Meson autodetection for features left as `auto`.

The Python configuration layer remains responsible for validating and rendering saved values.

Generated files, signatures, manifests, and feature probes belong under `BUILD_DIR` unless they are intentionally user-owned configuration.

## Error model

Errors are classified by scope.

### Core-QEMU error

A missing prerequisite that QEMU itself requires for the requested build remains fatal.

### Explicit-feature error

If the user selected `y`, missing prerequisites are fatal and the message names the feature and the missing prerequisite.

### Auto-feature decline

If the user selected `auto`, missing optional prerequisites produce a concise notice and the feature is disabled for that build.

An auto-feature decline must not be reported as a generic QEMU configure failure.

## Artifact verification

Generic builds receive generic verification:

- requested binary exists;
- binary is executable where appropriate;
- version command succeeds when supported;
- artifact manifest records the selected targets and produced outputs.

PowerPC-specific checks remain conditional on an actual `qemu-system-ppc` request.

When PPC is built, preserve the existing stronger checks for:

- `powermac3_1` registration;
- `mac99` registration;
- OpenBIOS artifact presence and checksum when OpenBIOS was enabled.

PPC-specific validation must not define success for unrelated target builds.

## CI and regression coverage

CI must exercise the WHP public path rather than validating only upstream `configure` on non-macOS hosts.

Required coverage includes:

- Linux build through `./build.sh`;
- macOS build through `./build.sh`;
- Windows/MSYS2 wrapper smoke coverage when practical in GitHub Actions;
- configuration-policy tests that simulate BSD-like host capability combinations without assuming GNU userland tools;
- a no-Bash core-QEMU path test;
- missing GTK in `auto` mode;
- missing PulseAudio in `auto` mode;
- missing OpenBIOS prerequisites in `auto` mode;
- strict OpenBIOS failure in `y` mode;
- non-root default prefix and `INSTALL=0` behavior;
- read-only-source or no-source-mutation coverage for a normal build path;
- explicit environment override precedence;
- retained PowerPC machine-profile verification.

The CI target matrix may still use direct upstream configure builds as an additional QEMU regression lane, but those jobs do not substitute for wrapper coverage.

## Compatibility and migration

Existing `.whpconfig` files must be migrated without silently changing explicit user intent.

When configuration schema changes introduce `auto` values:

- explicit legacy `y` remains enabled;
- explicit legacy `n` remains disabled;
- absence of a value receives the new portable default;
- obsolete generated-source files are ignored or cleaned only when safe;
- old environment overrides remain recognized during a bounded compatibility period if removing them would break an established invocation.

The implementation should bump the WHP configuration schema when stored value semantics change.

## Non-goals

This portability pass does not:

- rewrite QEMU's upstream configure or Meson host detection;
- broaden QEMU's supported host architecture policy beyond upstream;
- rewrite OpenBIOS internals;
- rewrite the LLVM or GNU PowerPC toolchains;
- alter guest ABIs or QEMU machine definitions;
- remove the existing macOS validation work;
- force every WHP helper to POSIX shell;
- make every optional WHP feature available on every host.

## Implementation boundaries

The implementation should stay focused on the public build layer and feature gating.

Expected areas of change include:

- `build.sh`;
- `scripts/whp-config/config.py` and menu handling;
- a new or expanded portable Python build driver;
- `scripts/whp-build/*` as adapters or compatibility modules;
- OpenBIOS dispatch boundaries;
- generated PPC device configuration placement;
- post-build verification;
- `.github/workflows/ci.yml` and focused build-policy tests.

Existing specialized firmware/toolchain scripts should be retained when they remain correct behind the new capability boundary.

## Success criteria

The design is complete when all of the following are true:

1. A host capable of building requested core QEMU targets is not rejected merely because Bash or an optional WHP dependency is missing.
2. Non-macOS builds no longer force `/emulator`, automatic installation, GTK, or PulseAudio.
3. Optional WHP features distinguish `auto`, explicit enable, and explicit disable behavior.
4. OpenBIOS/toolchain bootstrap failures in `auto` mode do not poison a viable core QEMU build.
5. Explicitly requested unavailable features fail early with precise diagnostics.
6. Routine builds do not require tracked source-tree mutation.
7. User compiler and linker flags are not overwritten by broad WHP defaults.
8. Linux CI exercises the public wrapper path, and portability-policy tests cover non-GNU and missing-feature cases.
9. Existing macOS hardening and PowerPC machine verification remain intact when those paths are selected.
10. Direct upstream QEMU build behavior remains available as an independent regression/control lane.
