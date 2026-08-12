# OpenBIOS tool provenance hardening

## Goal

Prevent Homebrew or any other ambient `PATH` entry from silently replacing tools that can change PowerPC OpenBIOS firmware output, while continuing to allow Homebrew for normal host-side build dependencies.

## Trust model

Tools are divided into two classes.

### Host dependencies

Examples: `git`, `cmake`, `ninja`, `xsltproc`, `pkg-config`, GNU Make, and other build-host utilities.

These may come from native Homebrew or the host operating system. The build may record their resolved path/version when they materially affect reproducibility, but they are not required to live in the WHP firmware tool directory.

### Firmware-shaping or firmware-validation tools

Examples: PowerPC compiler, assembler, linker, archive tools, target strip, `toke`, and the selected ELF inspection tool.

These must not be selected implicitly from ambient `PATH` when WHP bootstrapping is enabled. Project-controlled tools are selected by absolute path under the configured firmware/toolchain directories. External replacements remain possible only through explicit user overrides.

## OpenBIOS changes

1. `toke`
   - If `OPENBIOS_TOKE` is explicitly set, validate and use it.
   - Otherwise use the pinned WHP fcode-utils checkout/build under `OPENBIOS_TOOLS_DIR`.
   - Do not probe `PATH` for an arbitrary `toke` first.

2. PowerPC cross toolchain
   - If `OPENBIOS_CROSS_COMPILE` is explicitly set, validate that prefix and treat the choice as intentional.
   - If it is unset and `BOOTSTRAP_POWERPC_TOOLCHAIN=1`, bootstrap/select the project-controlled toolchain under `POWERPC_TOOLCHAIN_DIR` directly.
   - If bootstrapping is disabled and no explicit prefix is supplied, fail instead of scanning `PATH` for `powerpc-*` prefixes.

3. ELF reader
   - Continue preferring the project-built `llvm-readelf` under `POWERPC_TOOLCHAIN_DIR/llvm/bin`.
   - `OPENBIOS_READELF` remains the explicit override.
   - GNU prefixed `readelf` may remain as a compatibility fallback only where the selected non-Clang toolchain explicitly provides it.

4. Provenance visibility
   - Resolve firmware-shaping tools to absolute executable paths before use where practical.
   - Print the selected tool paths during OpenBIOS setup/build so an unexpected external tool is visible immediately.
   - Persist explicit firmware tool selections in the generated OpenBIOS environment/config stamp when they affect rebuild identity.

## Non-goals

- Do not remove native Homebrew from the macOS host `PATH`.
- Do not ban Homebrew-provided host dependencies.
- Do not replace assembler, linker, archive utilities, or strip with LLVM in this change.
- Do not change the PowerPC ABI, compiler target triple, OpenBIOS linker script, or firmware layout.

## Error handling

- Missing project-controlled firmware tools are hard errors once that lane is selected.
- An explicit external override is accepted only if its executable/prefix validates.
- No silent fallback from a missing project-controlled firmware tool to an ambient Homebrew/toolchain executable.

## Validation

The implementation should verify:

- `build-openbios.sh` no longer performs implicit `command -v toke` selection.
- `build-openbios.sh` no longer automatically scans `PATH` for PowerPC cross prefixes when no explicit override is supplied.
- the bootstrapped Clang lane still selects the WHP `powerpc-elf-` compatibility prefix.
- explicit `OPENBIOS_TOKE` and `OPENBIOS_CROSS_COMPILE` overrides continue to work.
- `llvm-readelf` remains selected from the project LLVM install in the Clang lane.
- shell syntax checks pass for each changed script.
- existing host Homebrew dependency behavior remains unchanged.
