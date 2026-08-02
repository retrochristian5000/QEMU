PowerPC cross-toolchain bootstrap
================================

The WHP PowerPC firmware build can bootstrap a small ``powerpc-elf`` GNU
cross-toolchain for OpenBIOS.  The bootstrap is deliberately narrower than a
normal GCC installation: it builds the binutils programs needed by firmware,
then a freestanding C compiler without target operating-system headers or
runtime libraries.

The implementation is in ``scripts/bootstrap-powerpc-toolchain.sh``.  This
document records the source, environment, and ``configure`` contract so that
future fixes do not remove an option merely because it appears redundant.

Build stages
------------

The dependency order is intentional::

  download and verify binutils
  extract binutils
  configure, build, and stage binutils
  assemble and relocatably link a PowerPC smoke object
  download and verify GCC
  extract GCC and download its pinned prerequisites
  configure, build, and stage GCC
  compile and inspect a PowerPC smoke object
  atomically install the completed toolchain

GCC is not downloaded or prepared until staged binutils has passed its smoke
test.  This keeps a binutils failure from being hidden behind a GCC download,
prerequisite, or configuration error.

Source-tree and Autotools policy
--------------------------------

The bootstrap consumes release archives, not development checkouts.  Release
archives already contain generated ``configure`` scripts and ``Makefile.in``
files.  A normal bootstrap therefore does not require Autoconf or Automake.

GCC 14 uses these versions when generated build files are deliberately
regenerated:

* Autoconf 2.69;
* Automake 1.15.1; and
* a suitable GNU M4.

GCC's build macros enforce the exact Autoconf version.  Using a newer Homebrew
Autoconf is not automatically safe merely because its version number is
higher.  Automake is needed only for directories whose ``Makefile.am`` is
being changed; much of GCC does not use Automake and maintains
``Makefile.in`` directly.

Consequently:

* do not run ``autoreconf`` over the GCC or binutils release trees;
* do not touch ``configure.ac``, ``aclocal.m4``, ``Makefile.am``, or generated
  outputs during an ordinary bootstrap;
* preserve archive timestamps when extracting the sources;
* treat an attempted Autoconf or Automake invocation as evidence that a
  generated-file dependency was disturbed; and
* use the release-specific Autotools versions only in a separate,
  intentionally managed regeneration workflow.

The bootstrap sets ``MAKEINFO=true`` because building Texinfo documentation is
not required to produce the firmware toolchain.  This is separate from
Autoconf and Automake: suppressing documentation generation must not be used
to conceal regeneration of build-system files.

Shell policy
------------

GCC recommends a working POSIX shell or GNU Bash for configuration.  Some
shell implementations have correctness or severe performance problems in
nested target configuration.  On macOS, use Bash explicitly when diagnosing
configuration problems::

  CONFIG_SHELL=/bin/bash \
  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/bootstrap-powerpc-toolchain.sh

``zsh`` should not be used as ``CONFIG_SHELL``.  The interactive shell from
which the wrapper is launched is not proof that all generated configure
scripts will use that shell.

Package-discovery isolation
---------------------------

The cross-toolchain is a build-machine dependency, not a QEMU host-library
consumer.  It must not inherit QEMU's Homebrew package search path.

During binutils and GCC configuration and compilation the bootstrap removes:

* ``PKG_CONFIG_PATH``;
* ``PKG_CONFIG_LIBDIR``; and
* ``PKG_CONFIG_SYSROOT_DIR``.

On Darwin, the selected SDK, deployment target, and (for Clang) architecture
are supplied consistently through host ``CFLAGS``, ``CXXFLAGS``,
``CPPFLAGS``, and ``LDFLAGS``.  The explicit ``CPPFLAGS`` matter because old
Autoconf probes preprocess headers separately instead of inheriting
``CFLAGS``.  The nested ``CC_FOR_BUILD`` and ``CXX_FOR_BUILD`` commands also
carry these flags because GCC prerequisites such as GMP perform link probes
without adding the outer build flags.

``TOOLCHAIN_PKG_CONFIG`` defaults to ``false``.  This prevents optional host
libraries from being selected merely because a matching ``.pc`` file appears
under ``/opt/homebrew`` or ``/usr/local``.  Any future dependency that truly
requires ``pkg-config`` must be enabled explicitly and recorded in the
bootstrap marker.

On Darwin, the one intentional host-library exception is the ``libz`` shipped
with the selected Apple SDK.  The pinned binutils 2.44 and GCC 14.2 trees
bundle zlib 1.1.4, whose old ``TARGET_OS_MAC`` compatibility macro conflicts
with current SDK declarations.  Both configure stages use
``--with-system-zlib`` on Darwin; no Homebrew search path is introduced.

Binutils configure contract
---------------------------

The bootstrap configures binutils with the following effective policy::

  --target=powerpc-elf
  --prefix=<toolchain directory>
  --disable-gdb
  --disable-gdbserver
  --disable-gprofng
  --disable-gold
  --disable-nls
  --disable-shared
  --disable-sim
  --disable-werror
  --enable-static
  --with-system-zlib        [Darwin only]
  --without-zstd

``--target=powerpc-elf``
  Builds programs that generate PowerPC ELF objects while running on the
  current macOS or other build machine.  This is distinct from QEMU's
  ``ppc-softmmu`` target and from the host architecture.

``--prefix``
  Gives the final logical installation prefix.  Installation first uses
  ``DESTDIR`` staging, after which the complete tree is moved into place
  atomically.

``--disable-gdb`` and ``--disable-gdbserver``
  Exclude debuggers that are not needed to assemble or link OpenBIOS.

``--disable-gprofng``
  Excludes the profiling tool and its additional host-side dependencies.

``--disable-gold``
  Builds the traditional BFD linker only.  Gold is unnecessary for this
  firmware toolchain and is not the linker path exercised by OpenBIOS.

``--disable-nls``
  Avoids a gettext dependency and produces stable English diagnostics.

``--disable-shared`` and ``--enable-static``
  Keep binutils support libraries local to the staged toolchain rather than
  introducing runtime dependencies on a particular Homebrew prefix.

``--disable-sim``
  Excludes the GNU target simulator.  QEMU provides the system emulator; the
  bootstrap needs only object-production tools.

``--disable-werror``
  Prevents warnings emitted by a newer Apple Clang from becoming fatal while
  compiling an older, pinned binutils release.  It does not disable warnings
  themselves.

``--without-zstd``
  Prevents automatic discovery of Homebrew ``libzstd`` through
  ``pkg-config``.  Compressed debug-section support is not required for
  OpenBIOS firmware objects.

``--with-system-zlib`` on Darwin
  Uses the selected SDK's maintained ``libz`` for host tools instead of the
  incompatible legacy copy bundled with the pinned release.

After installation, the bootstrap requires ``as``, ``ar``, ``ld``, ``nm``,
``objcopy``, ``objdump``, ``readelf``, ``strip``, and ``ranlib``.  It then
assembles a PowerPC function, performs a relocatable link with ``ld -r``, and
checks the resulting ELF header with ``readelf`` before GCC may start.

GCC configure contract
----------------------

The bootstrap configures GCC with the following effective policy::

  --target=powerpc-elf
  --prefix=<toolchain directory>
  --with-system-zlib        [Darwin only]
  --with-cpu=604
  --with-newlib
  --without-headers
  --without-isl
  --without-zstd
  --disable-bootstrap
  --disable-decimal-float
  --disable-libatomic
  --disable-libgomp
  --disable-libquadmath
  --disable-libsanitizer
  --disable-libssp
  --disable-multilib
  --disable-nls
  --disable-shared
  --disable-threads
  --disable-werror
  --enable-languages=c

``--target=powerpc-elf``
  Produces a bare-metal PowerPC ELF cross-compiler.  The compiler executable
  runs on the build machine; its output runs as firmware under emulation.  GNU
  ``config.sub`` reports the canonical identity as ``powerpc-unknown-elf``, but
  configure retains the requested alias for the installed ``powerpc-elf-*``
  program prefix.

``--prefix``
  Matches the binutils prefix so GCC finds the staged
  ``powerpc-elf-as`` and ``powerpc-elf-ld`` through the temporary ``PATH``.

``--with-cpu=604``
  Selects a conservative PowerPC 604 default matching the Classic Mac profile
  rather than inheriting a build-host CPU default.

``--with-system-zlib`` on Darwin
  Applies the same SDK-zlib host policy used for binutils.  This option affects
  the compiler programs that run on macOS, not generated PowerPC firmware.

``--with-newlib``
  Tells GCC that the eventual target environment follows newlib-like
  bare-metal assumptions.  This avoids tests that presume a hosted target C
  library even though newlib itself is not built in this stage.

``--without-headers``
  Builds the initial freestanding compiler without target system headers.
  The bootstrap installs ``all-gcc`` and ``install-gcc`` only; it does not
  attempt to build a complete target runtime.

``--without-isl``
  Disables Graphite loop-optimization support and its isl dependency.  The
  prerequisite helper is also invoked with ``--no-isl``.

``--without-zstd``
  Disables zstd support for GCC LTO bytecode.  The firmware compiler does not
  use host LTO, and optional Homebrew zstd discovery would reduce
  reproducibility.

``--disable-bootstrap``
  Avoids rebuilding GCC with the compiler it just produced.  That native-GCC
  bootstrap model is inappropriate for this small cross-compiler stage.

``--disable-decimal-float``
  Excludes decimal floating-point support that OpenBIOS does not require.

``--disable-libatomic``, ``--disable-libgomp``, ``--disable-libquadmath``,
``--disable-libsanitizer``, and ``--disable-libssp``
  Exclude target runtime libraries.  They require target headers, ABI support,
  threading, or operating-system facilities outside this freestanding stage.

``--disable-multilib``
  Produces one compiler configuration rather than a matrix of PowerPC CPU,
  endian, ABI, and floating-point runtime variants.  GCC documents PowerPC as
  having a broad predefined multilib set, so leaving this enabled would add
  substantial work and target-library assumptions.

``--disable-nls``
  Avoids gettext and keeps diagnostics stable.

``--disable-shared``
  Avoids target shared-library construction and host runtime coupling that is
  unnecessary for the installed compiler driver.

``--disable-threads``
  Selects a single-threaded bare-metal target model.

``--disable-werror``
  Prevents warnings from a newer Apple Clang host compiler from aborting the
  pinned GCC build.  It does not relax errors in the generated PowerPC code.

``--enable-languages=c``
  Builds only the C front end required for OpenBIOS.  C++, Objective-C,
  Fortran, Ada, Go, D, Modula-2, and Rust front ends would add bootstrap
  compiler or runtime prerequisites.

Host, build, and target identities
----------------------------------

A native Apple Silicon invocation has three separate identities:

* build/host programs such as ``powerpc-elf-gcc`` run as macOS Arm binaries;
* the cross-toolchain target is ``powerpc-elf``;
* QEMU's emulation target is ``ppc-softmmu``.

Native AArch64-Darwin support for a complete Darwin-target GCC and Darwin host
support for a C-family cross-compiler are different questions.  This bootstrap
builds the latter.  An error mentioning ``aarch64-apple-darwin`` must therefore
be classified by whether it describes the build/host compiler or the target
compiler before changing the target triplet.

Failure classification
----------------------

Use the reported bootstrap stage and the corresponding build directory:

``configuring and building binutils``
  Inspect ``build-binutils-<version>/config.log`` first.  Likely causes include
  the host compiler, SDK visibility, shell behavior, an accidental optional
  library, or a generated-file regeneration attempt.

``validating staged binutils``
  The programs installed but could not assemble, link, or identify a PowerPC
  ELF object.  Do not continue to GCC.

``preparing GCC prerequisites``
  The pinned GMP, MPFR, or MPC downloads failed or the prerequisite helper was
  modified unexpectedly.

``configuring and building GCC``
  Inspect ``build-gcc-<version>/config.log`` and the failing subdirectory.
  Confirm that staged binutils appears first in ``PATH`` and that the failure
  is not an attempted Autoconf or Automake regeneration.

``validating complete PowerPC toolchain``
  GCC installed but did not produce the required executables or generated an
  object whose ELF machine is not PowerPC.

Reproducible rebuild
--------------------

To discard the installed-toolchain cache while preserving verified source
archives::

  CONFIG_SHELL=/bin/bash \
  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/bootstrap-powerpc-toolchain.sh

The bootstrap marker records the build system, process architecture, Rosetta
state, target, source versions and checksums, host compiler commands, host-zlib
selection, and ``pkg-config`` policy.  Schema 6 invalidates older cached
toolchains that did not record the Darwin zlib choice.  A change to one of
those inputs must invalidate the cached toolchain.
