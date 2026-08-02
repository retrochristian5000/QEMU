Native Apple Silicon toolchain bootstrap
========================================

The PowerPC firmware toolchain is a cross-compiler with three independent
machine identities:

* ``build``: the machine performing the build;
* ``host``: the machine that runs ``powerpc-elf-gcc`` and GNU binutils; and
* ``target``: ``powerpc-elf``, the architecture emitted for OpenBIOS.

On a native Apple Silicon build, both build and host are
``aarch64-apple-darwin<kernel>``.  The target remains ``powerpc-elf``.  The
word ``aarch64`` is the GNU canonical CPU name; Apple tools and ``uname`` may
instead report ``arm64``.

The bootstrap normalizes ``arm64-apple-darwin`` to
``aarch64-apple-darwin`` and passes the resulting value explicitly through
both ``--build`` and ``--host``.  The binutils and GCC copies of
``config.sub`` must accept the exact identities before compilation begins.
This prevents a host-name mismatch from surfacing later as a generic
unsupported-configuration failure.

The short target alias has a different rule.  GNU ``config.sub`` canonicalizes
``powerpc-elf`` as ``powerpc-unknown-elf``.  The bootstrap accepts that
canonical identity while retaining ``powerpc-elf`` as the configure argument
and installed program prefix.

Darwin host flags
-----------------

The host-side binutils and GCC programs are Mach-O executables.  They require
the selected Apple SDK and process architecture even though their output is
PowerPC ELF.

For native Apple Silicon the bootstrap supplies Apple Clang with the
equivalent of::

  -arch arm64
  -isysroot <SDKROOT>
  -mmacosx-version-min=<MACOSX_DEPLOYMENT_TARGET>

Apple Clang is the default host compiler for both integrated and direct
bootstrap entry points.  An explicitly selected Darwin GNU GCC receives the
SDK and deployment-target flags but not ``-arch``.  FSF GCC produces the
single Darwin architecture for which it was configured, so the bootstrap
checks its canonical host triplet and generated Mach-O slice instead.

These flags are recorded separately as ``TOOLCHAIN_HOST_CFLAGS``,
``TOOLCHAIN_HOST_CXXFLAGS``, ``TOOLCHAIN_HOST_CPPFLAGS``, and
``TOOLCHAIN_HOST_LDFLAGS``.  Supplying the SDK flags to ``CPPFLAGS`` is
important when the Xcode Clang path is invoked directly: Autoconf runs
standalone preprocessing tests which otherwise do not inherit ``CFLAGS``.
The bootstrap also carries the flags directly on ``CC_FOR_BUILD`` and
``CXX_FOR_BUILD`` because GCC prerequisites such as GMP run build-compiler
link probes without their normal flag variables.  They are not QEMU target
flags and are not passed to ``powerpc-elf-gcc`` when compiling OpenBIOS.

Before downloading source archives, the bootstrap links a C program and a
C++11 program with the effective host policy.  On Darwin, ``lipo`` must report
an ``arm64`` slice for a native Apple Silicon build or ``x86_64`` for an
intentional Rosetta build.

Pinned zlib on current Apple SDKs
---------------------------------

The pinned binutils 2.44 and GCC 14.2 release trees include zlib 1.1.4.  Its
legacy ``TARGET_OS_MAC`` compatibility macro replaces ``fdopen`` before
current Apple SDK headers declare that function.  On Darwin, both configure
stages therefore use ``--with-system-zlib`` and link their host tools to the
SDK ``libz``.  This is an SDK dependency, not Homebrew package discovery, and
the choice is recorded in the bootstrap marker.

Configure shell
---------------

Nested binutils and GCC configure scripts run with an explicit shell::

  CONFIG_SHELL=/bin/bash
  SHELL=/bin/bash

Override this with ``TOOLCHAIN_CONFIG_SHELL`` only when another known-good
POSIX shell is required.  The selected shell path is part of the toolchain
cache marker.

Target-tool selection
---------------------

After binutils passes its PowerPC assembly and relocatable-link smoke test, the
GCC build environment binds ``AS_FOR_TARGET``, ``LD_FOR_TARGET``,
``AR_FOR_TARGET``, ``NM_FOR_TARGET``, and the other target utilities to the
staged ``powerpc-elf-*`` programs.

This prevents Apple or Homebrew tools found later in ``PATH`` from being
mistaken for the target assembler or linker.  The staged paths are used only
during construction; the installed compiler continues to locate tools under
its final prefix.

LTO is disabled for this bootstrap.  OpenBIOS does not require GCC's linker
plugin, and excluding it avoids adding a second host-linker integration path
to the minimal firmware compiler.

Rebuild command
---------------

Use the normal macOS wrapper and force a new schema-6 toolchain::

  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/macos-builder.sh

For an intentional Intel build under Rosetta::

  arch -x86_64 env \
  MACOS_ALLOW_ROSETTA=1 \
  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/macos-builder.sh

A failure during ``validating host compiler and SDK`` is a macOS host problem.
A failure during binutils or GCC configuration should be investigated in the
stage-specific build directory printed by the bootstrap.
