PowerPC Clang and LLD migration
===============================

Scope
-----

The LLVM migration lane now replaces both the 32-bit PowerPC OpenBIOS target
compiler and the final OpenBIOS linker.  Clang produces target objects and LLD
performs the final ELF link.  GNU ``as`` and the remaining archive/symbol/strip
utilities stay on the existing pinned binutils release for later one-by-one
migration.  QEMU's host compiler is unchanged.

On macOS, ``scripts/meson-build-openbios.sh`` selects the Clang lane by
default.  Other hosts retain the GCC lane unless
``POWERPC_TOOLCHAIN_COMPILER=clang`` is set explicitly.

LLVM source ownership
---------------------

The WHP LLVM fork is a QEMU git submodule at
``toolchains/llvm-project``.  The QEMU gitlink is the LLVM revision pin, so
there is no independent LLVM remote or second commit pin to keep in sync.
The legacy compiler foundation may materialize a sparse local build cache from
the submodule, but that cache is derived from the gitlink and is not a source
revision authority.  The submodule follows ``retrochristian5000/LLVM`` and is
shallow by default.

To initialize it manually::

  git submodule update --init toolchains/llvm-project

The Clang bootstrap initializes the submodule automatically when networking is
allowed.  ``POWERPC_LLVM_GIT_OFFLINE=1`` requires the submodule to be present
already.  Tracked LLVM changes must be committed before the toolchain build,
and the checked-out LLVM commit must match the QEMU gitlink.  To test a
different LLVM revision, commit it in the LLVM fork and advance the QEMU
submodule pointer; do not add a competing bootstrap commit pin.

Compatibility boundary
----------------------

OpenBIOS continues to consume a GNU-style ``powerpc-elf-`` prefix.  The Clang
bootstrap installs ``powerpc-elf-gcc`` as a compatibility wrapper around the
WHP Clang binary and installs ``powerpc-elf-ld`` as a symlink to the WHP
``ld.lld`` binary.

The wrapper targets ``powerpc-none-elf`` and forces
``-fno-integrated-as``.  Its private ``-B`` directory therefore routes
assembly to the retained GNU ``powerpc-elf-as`` but routes linking to LLD.
The old GNU BFD linker is retained only as
``libexec/powerpc-clang-gnu/ld.bfd`` for controlled A/B comparisons; normal
OpenBIOS linking does not select it.

OpenBIOS also carries several GCC-only options.  The compatibility driver
removes only the options that Clang does not accept in this lane:

* ``-mcall-sysv-noeabi``;
* ``-msdata=none``;
* ``-G0``;
* ``-Wbuiltin-declaration-mismatch``;
* ``-Wmaybe-uninitialized``; and
* ``-Wno-maybe-uninitialized``.

LLD validation
--------------

The base bootstrap builds the PowerPC-only LLVM/Clang foundation from a local
cache derived from the submodule.  The outer bootstrap then builds LLD from the
full submodule checkout against that LLVM install.  It requires ``clang``,
``ld.lld``, and ``llvm-readelf`` before publishing the linker routing.

In addition to the compiler smoke object, the bootstrap performs a firmware
layout smoke link using the OpenBIOS-critical GNU linker interface:
``--warn-common``, ``-z noexecstack``, ``-N``, ``-T``, and
``--whole-archive``.  The test uses ``OUTPUT_FORMAT(elf32-powerpc)`` and
``OUTPUT_ARCH(powerpc:common)`` and rejects LLD unless it produces:

* ELF32, big-endian PowerPC ``ET_EXEC``;
* entry point ``0xfff00100``;
* the vector base at ``0xfff00000``;
* the hard-reset code at ``0xfffffffc``;
* no ``PT_INTERP`` or ``PT_DYNAMIC``; and
* load segments that stay inside and cover the 1 MiB Power Mac PROM window.

Source policy
-------------

The Clang/LLD lane still retains release binutils for GNU ``as`` and the
remaining utilities, so it requires ``POWERPC_TOOLCHAIN_SOURCE_MODE=release``
(the default).  The existing GCC release and GCC Git bootstrap paths remain
available as controls.

To force the GCC control lane::

  POWERPC_TOOLCHAIN_COMPILER=gcc \
  bash scripts/meson-build-openbios.sh CONFIG_FILE OUTPUT

To force a rebuild of the Clang/LLD toolchain lane::

  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/bootstrap-powerpc-clang.sh

Validation boundary
-------------------

The existing GitHub Actions macOS QEMU job currently sets both
``BUILD_OPENBIOS=0`` and ``BOOTSTRAP_POWERPC_TOOLCHAIN=0``.  A green result
from that job validates the macOS QEMU host build, not the Clang/LLD firmware
lane.

The linker migration is therefore considered fully validated only after a
machine runs the Clang/LLD bootstrap, passes its compiler and PROM-layout
smoke checks, builds OpenBIOS, passes the existing OpenBIOS ELF validation,
and boots the resulting firmware under the intended QEMU PowerPC machine.
