# Build Variable Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the WHP build-system environment surface so one build decision has one public variable.

**Architecture:** Preserve role boundaries (QEMU host, build-machine tools, firmware target) while removing aliases and user-overridable values that are already derived. Keep provenance, source-mode, compiler-mode, and explicit force-rebuild controls because they represent distinct decisions.

**Tech Stack:** POSIX shell, GNU Bash, QEMU configure/Meson/Ninja, OpenBIOS bootstrap scripts.

## Global Constraints

- Work on `master`; do not create a branch.
- Incremental builds remain the default.
- Do not weaken host/target tool isolation.
- Do not remove provenance/source-selection variables.
- Do not claim native macOS build success without a native build result.

---

### Task 1: Collapse shell selection

**Files:**
- Modify: `build.sh`
- Modify: `scripts/macos-builder.sh`
- Modify: `scripts/macos-builder.bash`
- Modify: `scripts/bootstrap-powerpc-clang.sh`

**Interfaces:**
- Consumes: `WHP_BUILD_BASH`
- Produces: normalized `CONFIG_SHELL`

- [ ] Remove `QEMU_CONFIG_SHELL` as a build knob.
- [ ] Remove `TOOLCHAIN_CONFIG_SHELL` from the Clang orchestrator; use `CONFIG_SHELL` locally.
- [ ] Preserve GNU Bash validation and clean-shell execution.
- [ ] Verify repository search no longer finds these names in the edited active path.

### Task 2: Derive macOS host architecture

**Files:**
- Modify: `scripts/whp-build/prepare-build.bash`
- Modify: `scripts/whp-build/prepare-sources.bash`
- Modify: `scripts/whp-build/configure.bash`
- Modify: `docs/devel/macos-build.rst`

**Interfaces:**
- Consumes: detected `HOST_ARCH`
- Produces: internal host architecture used for paths, flags, and probes

- [ ] Stop accepting `MACOS_HOST_ARCH` from the environment.
- [ ] Use detected `HOST_ARCH` for build directory, architecture flags, Homebrew selection, and verifier inputs.
- [ ] Remove `MACOS_HOST_ARCH` from the configuration identity and user-facing override documentation.
- [ ] Preserve Rosetta control through `MACOS_ALLOW_ROSETTA`.

### Task 3: Remove OpenBIOS host-tool aliases from the public path

**Files:**
- Modify: `scripts/macos-builder.sh`
- Modify: `scripts/whp-build/prepare-sources.bash`
- Modify: `scripts/whp-build/configure-openbios.bash`

**Interfaces:**
- Consumes: `CC_FOR_BUILD`, `CXX_FOR_BUILD`, `STRIP_FOR_BUILD`
- Produces: OpenBIOS environment file with resolved build-machine tools

- [ ] Remove `OPENBIOS_HOSTCC`, `OPENBIOS_HOSTCXX`, and `OPENBIOS_HOSTSTRIP` overrides from the integrated build path.
- [ ] Resolve OpenBIOS host tools directly from the build-machine tool variables.
- [ ] Preserve the generated OpenBIOS environment keys required by the firmware build script.

### Task 4: Verification

**Files:**
- Inspect all modified files and repository search results.

- [ ] Confirm removed public aliases have no active integrated-build references.
- [ ] Confirm `CONFIG_SHELL`, `HOST_ARCH`, `CC_FOR_BUILD`, `CXX_FOR_BUILD`, and `STRIP_FOR_BUILD` remain connected through the expected stages.
- [ ] Check GitHub status for the final commit.
- [ ] Report native-build verification as pending unless CI or a native runner proves it.
