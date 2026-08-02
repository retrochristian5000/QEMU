Meson-owned OpenBIOS bootstrap
==============================

The WHP macOS build treats OpenBIOS as a firmware output in QEMU's Meson and
Ninja graph.  The older ``builder.sh`` pre-configuration firmware invocation is
disabled by the macOS wrapper, preventing two independent parts of the build
from owning ``openbios-ppc``.

Build graph
-----------

``scripts/macos-builder.bash`` writes a shell-quoted configuration file at::

  BUILD_DIR/.whp-openbios-meson.env

``pc-bios/meson.build`` detects that file while configuring QEMU and defines the
``whp-openbios-ppc`` custom target.  Its output is::

  BUILD_DIR/pc-bios/openbios-ppc

The target runs ``scripts/meson-build-openbios.sh``.  That adapter owns this
sequence:

#. select or bootstrap the PowerPC ELF toolchain;
#. validate that all required prefixed tools exist;
#. build OpenBIOS with the selected cross-toolchain;
#. copy and validate the firmware at Meson's declared output path.

The custom target is part of the default graph when ``ppc-softmmu`` is selected.
It is marked stale deliberately: the adapter runs on each requested build, while
the underlying toolchain and OpenBIOS scripts use content and configuration
stamps to avoid expensive work when nothing changed.  This also means changes
to the generated configuration file are consumed without requiring a Meson
reconfiguration.

Source modes
------------

Release archives remain the default source policy::

  ./build.sh

To build binutils and GCC from their official Git repositories instead::

  POWERPC_TOOLCHAIN_SOURCE_MODE=git \
  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  ./build.sh

The official-Git adapter currently defaults to the maintained
``binutils_2.46-branch`` and ``releases/gcc-16`` branches.  It resolves each
branch to a full commit, exports a clean tree, creates commit-specific archives,
and records the result in::

  POWERPC_TOOLCHAIN_DIR/.whp-official-git-sources

For reproducible Git-source builds, pin both commits explicitly::

  POWERPC_TOOLCHAIN_SOURCE_MODE=git \
  POWERPC_BINUTILS_GIT_COMMIT=<40-digit-commit> \
  POWERPC_GCC_GIT_COMMIT=<40-digit-commit> \
  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  ./build.sh

A Git checkout differs from a release archive.  The adapter requires Bison and
Flex, runs ``contrib/gcc_update --touch`` on the GCC export, and removes the
GDB-only directories from the combined binutils-gdb export.  The PowerPC
bootstrap still validates canonical build, host, and target triplets, host-tool
versus target-tool routing, the installed sysroot, PowerPC ELF class, and
big-endian output.

Direct target
-------------

After QEMU has been configured, the firmware edge can be requested directly::

  gmake -C BUILD_DIR whp-openbios-ppc

A normal ``all`` build also requests it for the WHP ``ppc-softmmu`` profile.
The persistent PowerPC toolchain and source cache remain outside the disposable
QEMU Meson tree, so a clean QEMU reconfiguration does not discard them.
