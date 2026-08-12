PowerPC Clang compiler migration
================================

Scope
-----

The first LLVM migration step deliberately changes only the compiler used for
32-bit PowerPC OpenBIOS target objects.  It does not replace the PowerPC GNU
assembler, linker, archive tools, ELF inspection tools, or the QEMU host
compiler.

On macOS, ``scripts/meson-build-openbios.sh`` now selects the Clang lane by
default.  Other hosts retain the GCC lane unless
``POWERPC_TOOLCHAIN_COMPILER=clang`` is set explicitly.

The Clang lane is implemented by ``scripts/bootstrap-powerpc-clang.sh``.  It
builds the same pinned GNU binutils release used by the existing release
bootstrap, then builds Clang from the WHP LLVM fork with only the PowerPC LLVM
target enabled.  The default LLVM source is pinned to commit
``e7dd336e0f7884c34108a1e722205a16c3f5307b`` from
``retrochristian5000/LLVM``.

Compatibility boundary
----------------------

OpenBIOS currently discovers and invokes a GNU-style ``powerpc-elf-`` prefix.
Changing that interface at the same time as the compiler would mix two
independent migrations.  The Clang bootstrap therefore installs a temporary
compatibility driver at ``powerpc-elf-gcc``.  That file is a wrapper around the
pinned WHP Clang binary; it is not GNU GCC.

The wrapper targets ``powerpc-none-elf`` and forces
``-fno-integrated-as``.  A private ``-B`` tool directory routes assembly back
to the retained ``powerpc-elf-as``.  Final OpenBIOS linking continues to use
``powerpc-elf-ld`` directly, as before.

OpenBIOS also carries several GCC-only options.  The compatibility driver
removes only the options that Clang does not accept in this lane:

* ``-mcall-sysv-noeabi``;
* ``-msdata=none``;
* ``-G0``;
* ``-Wbuiltin-declaration-mismatch``;
* ``-Wmaybe-uninitialized``; and
* ``-Wno-maybe-uninitialized``.

The bootstrap then compiles a PowerPC smoke object and rejects the toolchain if
that object is not 32-bit big-endian PowerPC or if Clang creates ``.sdata`` or
``.sbss`` sections.  It also checks Clang's reported assembler path so an
integrated-assembler change cannot be mistaken for a compiler-only result.

Source policy
-------------

The Clang migration lane intentionally keeps release binutils.  It therefore
requires ``POWERPC_TOOLCHAIN_SOURCE_MODE=release`` (the default).  The existing
GCC release and GCC Git bootstrap paths remain available as controls.

To force the old compiler lane::

  POWERPC_TOOLCHAIN_COMPILER=gcc \
  bash scripts/meson-build-openbios.sh CONFIG_FILE OUTPUT

To rebuild only the new compiler/toolchain lane directly::

  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/bootstrap-powerpc-clang.sh

The LLVM source can be overridden for controlled testing with
``POWERPC_LLVM_GIT_URL``, ``POWERPC_LLVM_GIT_REF``, and
``POWERPC_LLVM_GIT_COMMIT``.  A changed compiler revision changes the toolchain
marker and invalidates the cached installation.

Validation boundary
-------------------

The existing GitHub Actions macOS QEMU job currently sets both
``BUILD_OPENBIOS=0`` and ``BOOTSTRAP_POWERPC_TOOLCHAIN=0``.  A green result from
that job therefore validates the macOS QEMU host build, not this PowerPC Clang
firmware lane.

Until a separate firmware-toolchain CI job is intentionally added, the
compiler migration is considered validated only after a macOS build completes
the Clang bootstrap, the compiler/binutils smoke checks, the OpenBIOS build,
and the existing OpenBIOS ELF validation.  Do not treat unrelated macOS CI
success as evidence that the firmware compiler migration passed.
