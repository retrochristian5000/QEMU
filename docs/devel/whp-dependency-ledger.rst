.. _whp-dependency-ledger:

WHP dependency ledger
=====================

Purpose
-------

This ledger records dependencies that influence the WHP QEMU build.  It exists
to keep the bootstrap graph, QEMU's Meson/Ninja graph, firmware graph, and
editable source forks from being flattened into one ambiguous list.

A dependency belongs here when it is one of the following:

* a top-level git submodule pinned by QEMU;
* a host tool needed before QEMU can configure;
* a library or generator consumed by QEMU's configure/Meson/Ninja graph;
* a dependency required by one of the pinned submodules; or
* a conditional edge whose activation can change build order.

The gitlink recorded by the QEMU commit is authoritative.  A branch named in
``.gitmodules`` is discovery metadata, not permission to build an arbitrary
branch tip.

Dependency states
-----------------

``root``
  A host capability that must exist before the WHP can bootstrap replacements,
  for example a primitive shell, Git, a host compiler, an SDK/libc, or GNU
  Make for projects whose bootstrap path requires it.

``managed``
  A dependency whose source is pinned as a QEMU submodule and which has a WHP
  bootstrap or firmware path.

``graph``
  A dependency or artifact owned by QEMU configure, Meson, Ninja, or GNU Make.
  WHP preparation may describe the edge but must not build the artifact early.

``conditional``
  A real edge that is active only for a feature, host, firmware, or submodule
  build profile.

``planned``
  Source is present and intentionally retained for a future direct consumer,
  but the current production QEMU graph does not link it.

Top-level submodule registry
----------------------------

``Editable`` means the submodule URL points at a WHP-owned
``retrochristian5000/*`` fork.  External projects remain pinned and may be
patched through QEMU when necessary, but their upstream repository is not owned
by the WHP account.

.. list-table::
   :header-rows: 1
   :widths: 28 22 10 40

   * - Path
     - Source
     - Editable
     - Current role / dependency notes
   * - ``roms/seabios``
     - ``X86-Firmware``
     - yes
     - x86 firmware; WHP i386 toolchain edge; GRUB edge is conditional.
   * - ``roms/SLOF``
     - qemu-project SLOF
     - no
     - PowerPC firmware source; upstream-owned build prerequisites.
   * - ``roms/ipxe``
     - qemu-project iPXE
     - no
     - network option ROM source; built only when selected by QEMU firmware targets.
   * - ``roms/openbios``
     - ``PPC-Firmware``
     - yes
     - PowerPC firmware; depends on the WHP PowerPC compiler/binutils-replacement lane.
   * - ``roms/qemu-palcode``
     - ``Alpha-Firmware``
     - yes
     - Alpha PALcode source; not on the default i386/PPC build path.
   * - ``roms/u-boot``
     - qemu-project U-Boot
     - no
     - firmware source for selected machines; upstream-owned prerequisites.
   * - ``roms/skiboot``
     - qemu-project skiboot
     - no
     - POWER firmware source; conditional on matching targets.
   * - ``roms/QemuMacDrivers``
     - qemu-project QemuMacDrivers
     - no
     - Macintosh ROM/driver inputs; firmware/data edge.
   * - ``roms/seabios-hppa``
     - qemu-project seabios-hppa
     - no
     - HPPA firmware source; target-conditional.
   * - ``roms/u-boot-sam460ex``
     - qemu-project u-boot-sam460ex
     - no
     - Sam460ex firmware source; target-conditional.
   * - ``roms/edk2``
     - qemu-project edk2
     - no
     - UEFI firmware source; some selected builds also require ``iasl`` and bzip2.
   * - ``roms/opensbi``
     - qemu-project opensbi
     - no
     - RISC-V firmware source; target-conditional.
   * - ``roms/qboot``
     - qemu-project qboot
     - no
     - lightweight x86 firmware source; target-conditional.
   * - ``roms/vbootrom``
     - qemu-project vbootrom
     - no
     - firmware source; target-conditional.
   * - ``tests/lcitool/libvirt-ci``
     - libvirt-ci
     - no
     - dependency metadata and CI tooling; not a runtime QEMU dependency.
   * - ``toolchains/llvm-project``
     - ``LLVM``
     - yes
     - native and cross compiler family; bootstrap must start from an already usable host compiler.
   * - ``toolchains/wine``
     - ``water`` (Wine)
     - yes
     - Wine 11.16 fork; ``planned`` Windows API/PE validation and cross-development layer. Normal source already carries ``configure``; basic build requirements include GNU Make, flex, bison, a host compiler, and platform development headers/tooling.
   * - ``toolchains/grub``
     - ``grub``
     - yes
     - conditional SeaBIOS/EFI and hybrid-image helper.
   * - ``toolchains/ninja-builder``
     - ``ninja-builder``
     - yes
     - host Ninja fallback; requires Python plus a host C++17 compiler.
   * - ``toolchains/fast-linker``
     - ``fast-linker``
     - yes
     - mold-derived optional linker; CMake plus C/C++; disabled for Darwin Mach-O.
   * - ``toolchains/python-runtime``
     - ``Python``
     - yes
     - Python >= 3.9 fallback; POSIX bootstrap requires a host C compiler and GNU Make.
   * - ``toolchains/make``
     - ``make``
     - yes
     - Pinned GNU Make fork; currently ``planned`` as a managed build tool because its Git maintainer-source tree still needs a seed GNU Make/Autotools path before it can produce the configured no-Make bootstrap inputs.
   * - ``toolchains/git``
     - ``git-tools``
     - yes
     - Managed Git fork behind an explicit seed-Git boundary. Seed Git still obtains QEMU and materializes the fork; only an HTTPS-capable managed build may replace it for later remote/submodule work.
   * - ``toolchains/sdl``
     - ``SDLosaurus``
     - yes
     - SDL3 fallback; CMake + Ninja + host C compiler.
   * - ``toolchains/jack``
     - ``jack``
     - yes
     - JACK client library for QEMU; Python/Waf + C/C++.  Full macOS server builds have a conditional Aften edge.
   * - ``toolchains/aften``
     - ``aften``
     - yes
     - A/52 (AC-3) encoder; CMake + C compiler + threads/libm.  AArch64 uses scalar C today; arm64e is a distinct Apple ABI selection.
   * - ``toolchains/libisofs``
     - ``libisofs``
     - yes
     - Darwin ISO metadata path; GNU Make + GNU Libtool + host C compiler; pkg-config is used for discovery/probes.
   * - ``toolchains/libtool``
     - ``libtool``
     - yes
     - Managed GNU Libtool host-tool fallback for Autotools consumers. The Git maintainer tree bootstraps from GNU Make, Autoconf/Automake, Help2man, Texinfo, xz, and its pinned gnulib/bootstrap submodules; it does not consume an existing Libtool.
   * - ``toolchains/bash``
     - ``bash``
     - yes
     - Bash fallback for WHP orchestration; host C compiler + GNU Make. The WHP
       profile is non-interactive and omits Readline/history plus other unused
       interactive/network/debug subsystems while retaining build-script syntax.
   * - ``toolchains/automake``
     - ``automake``
     - yes
     - Managed Automake/aclocal fallback. Its Git bootstrap consumes the
       validated seed sed plus Perl, Autoconf/autom4te, and seed GNU Make.
   * - ``toolchains/autoconf``
     - ``autoconf``
     - yes
     - Managed Autoconf/autom4te/autoheader/autoreconf suite. Its Git bootstrap
       self-hosts Autoconf from the pinned source but consumes Automake/aclocal,
       GNU M4, Perl, seed GNU Make, and the validated seed sed.
   * - ``toolchains/sed``
     - ``sed``
     - yes
     - Managed GNU sed host tool. Its maintainer-source bootstrap is downstream
       of Automake and a validated host sed seed, then the installed GNU sed is
       promoted ahead of managed Git, Bash, and later Autotools consumers.

Known bootstrap and library edges
---------------------------------

The current host-side order is intentionally split from the QEMU artifact
graph.  A compact view is::

  primitive host tools / SDK / compiler
      |
      +--> cc.sh native C seed
      |      +--> Python fallback
      |      +--> GNU sed / Git / Bash / SDL host builds
      |      +--> lazy C++17 seed -> Ninja / JACK / native LLVM
      |
      +--> seed Git
      |      +--> QEMU source checkout/update
      |      +--> pinned WHP Git fork
      |             +--> managed full Git (HTTPS-capable) -> later submodules
      |             +--> managed local Git -> local repository operations only
      |
      +--> Python >= 3.9
      |      +--> Bash fallback
      |      +--> Ninja fallback
      |
      +--> CMake
      |      +--> optional mold
      |
      +--> GNU Make seed
      |      +--> pinned WHP Make fork (planned)
      |      +--> Python POSIX fallback
      |      +--> Bash fallback
      |      +--> WHP Libtool bootstrap
      |               |
      |               +--> libisofs
      |
      +--> optional native LLVM
             |
             +--> QEMU host compiler
             |      +--> SDL3 host library
             |      +--> JACK client library
             |      +--> Libtool-configured downstream archives
             |             +--> libisofs
             |
             +--> firmware cross-toolchain lanes
             +--> Windows PE/COFF cross targets
                       |
                       +--> Wine execution/API validation (planned)

  When native LLVM is disabled, SDL3/JACK fall back to the seed build-machine
  compiler so portable/non-LLVM builds retain their existing preparation path.

  GNU Make + flex + bison + host/platform development headers
      |
      +--> pinned WHP Wine fork (planned)

  QEMU configure -> Python venv/Meson -> Meson dependency resolution
                 -> Ninja artifacts -> GNU Make test/firmware umbrella

Python is earlier than QEMU configuration because configure creates and uses
the QEMU Python virtual environment.  Ninja is also required before normal
Meson configuration.  A native WHP LLVM build is optional and must not become
a prerequisite for bootstrapping the compiler that is needed to build LLVM
itself.

Core QEMU dependencies represented by the minimal CI/build metadata include
GLib/gmodule, zlib, pixman, libffi, and libfdt in addition to the shell,
compiler, Python, Meson, Ninja, pkg-config, and basic build utilities.  The WHP
GLib fork is pinned at ``toolchains/glib`` so QEMU has a repository-owned GLib
source alongside the system/package-manager dependency path.  The
full ``tests/lcitool/projects/qemu.yml`` profile adds feature-gated libraries
such as ALSA, GTK, GnuTLS, libcurl, libiscsi, libnfs, libslirp, libssh,
libusb, PipeWire, PulseAudio, SDL, SPICE, zstd, and others.  Those optional
libraries stay feature-gated rather than becoming WHP bootstrap roots.

Bootstrap phase ordering
------------------------

The host bootstrap is split into phases rather than one flat dependency list.

**Seed/tool phase:** ``cc.sh``, seed GNU Make, seed sed, Python, Automake,
managed Autoconf, managed GNU sed, managed Git, Bash, and Ninja are available
before native LLVM. These are generators/orchestration tools needed to reach
the compiler build and therefore use build-machine roles. The seed GNU Make
identity is established before the Python fallback and exported through both
``MAKE_CMD`` and ``MAKE``. A single validated sed seed is likewise established
before Python and Automake. Managed Autoconf is promoted after Automake, and
managed GNU sed is promoted only after that suite is available.

**Compiler promotion:** when ``BOOTSTRAP_NATIVE_LLVM=1``, the native LLVM
bootstrap publishes QEMU's artifact ``CC``/``CXX`` and coherent LLVM
archive/binutils replacements.

**Artifact-library phase:** SDL and JACK are linked into QEMU, so in an LLVM
build they are deliberately deferred until after compiler promotion. In a
non-LLVM or portable build they remain preparable with the seed compiler.
Libtool stays after compiler promotion because its configure/cache records
archive and binary-tool identities, and libisofs remains downstream of that
Libtool selection.

Bootstrap compiler boundary
---------------------------

``cc.sh`` is the pre-LLVM native compiler adapter. It is intentionally a
root-boundary selector rather than a compiler implementation: a usable host
compiler must already exist before the WHP LLVM fork can build itself. The
adapter validates that its selected C compiler can compile, link, and execute a
native probe, and it exposes a separate lazy C++17 selection for components
that actually need C++.

The build-machine roles are ``CC_FOR_BUILD`` and ``CXX_FOR_BUILD``.
Target ``CC``/``CXX`` are deliberately excluded from seed discovery so a
cross compiler cannot leak backward into Python, GNU sed, Git, Bash, SDL,
Ninja, JACK, or the native LLVM bootstrap. Explicit seed overrides use
``WHP_CC_SEED`` and ``WHP_CXX_SEED``.

Git bootstrap boundary
----------------------

The WHP owns the pinned ``toolchains/git`` fork, but Git cannot be the first
Git executable in the graph. An already usable seed Git is required to obtain
the QEMU checkout, refresh ``master``, read the QEMU gitlink, and materialize
``toolchains/git`` plus its pinned ``sha1collisiondetection`` gitlink.

After that seed boundary, ``scripts/ensure-git.py`` builds a private Git.
The preferred profile retains libcurl/HTTPS transport while disabling unrelated
bootstrap surfaces such as gettext, Perl, Python helpers, Tcl/Tk, gitweb,
Expat/WebDAV, and direct OpenSSL use. Iconv is intentionally retained because
Darwin enables ``PRECOMPOSE_UNICODE``; combining that path with
``NO_ICONV`` removes ``reencode_string_iconv`` while
``compat/precompose_utf8.c`` still calls it. On current Darwin releases the
managed build uses the expected libiconv prefix. In ``auto`` mode a failed
full profile may fall back to a reduced ``NO_CURL`` local profile; that binary is
exposed for local use but is never promoted over the HTTPS-capable seed.

``BOOTSTRAP_GIT=1`` requires the fork and requires ``git-remote-https``
before the managed Git is placed on ``PATH``. This keeps the
``Git -> checkout Git`` edge visible as a seed boundary rather than a hidden
self-cycle.

Autoconf bootstrap boundary
---------------------------

The pinned ``toolchains/autoconf`` fork is a maintainer-source checkout, but
its ``bootstrap`` self-hosts temporary ``autoconf`` and ``autom4te`` programs
from the source tree. It therefore does not need an installed Autoconf to
generate its own ``configure``.

The cycle boundary is Automake: the WHP Automake Git bootstrap still consumes
a seed Autoconf/autom4te pair, while the Autoconf Git bootstrap consumes
Automake/aclocal. The valid order is therefore::

  seed Autoconf/autom4te
          |
          +--> managed Automake/aclocal
                    |
                    +--> managed Autoconf suite
                              |
                              +--> managed GNU sed
                              +--> later Autotools consumers

Managed Autoconf must not be fed back into the same Automake bootstrap that
produces the Automake instance it consumes. The seed Autoconf dependency is
therefore narrowed to the first Automake stage.

``scripts/ensure-autoconf.py`` uses a tool-only install profile: executables,
Autom4te/Autoconf/M4sugar/Autotest data, autoscan data, and auxiliary config
scripts are installed without Info or manual generation. Help2man and Texinfo
remain upstream developer/release tools, not requirements of the QEMU profile.

The direct roots for this managed stage are Automake/aclocal, GNU M4, Perl,
seed GNU Make, a primitive shell, ``realpath``/``mktemp``, and the validated
sed seed.

sed/Automake bootstrap boundary
-------------------------------

GNU sed has two different roles in the WHP bootstrap and they must not be
flattened into one executable slot.

**Seed sed** is a root capability. ``sed.sh`` validates the small semantic
subset needed by the bootstrap and rejects recursion back into itself. The
public ``build.sh`` resolves this seed once as ``WHP_SED_SEED`` before the
Python fallback or Automake bootstrap. Python, Automake, and GNU sed's own
self-bootstrap therefore consume one provenance identity rather than
independently rediscovering host sed implementations.

**Managed GNU sed** remains downstream of Automake and managed Autoconf. The pinned sed fork is a
maintainer-source checkout whose bootstrap explicitly requires Automake and
Autoconf; its gnulib path also requires M4. The sed fork's ``bootstrap.conf``
declares gettext, makeinfo, and Perl as build prerequisites. In the current
WHP invocation, ``--skip-po`` avoids PO refresh/download work but does not
remove those prerequisite checks, and the gettext path can still run
``autopoint`` because ``configure.ac`` uses GNU gettext macros.

The resulting order is therefore::

  seed Git + host compiler + seed GNU Make + seed sed
      |
      +--> Python fallback
      +--> Automake/aclocal
              |
              +--> managed GNU sed
                      |
                      +--> managed Git
                      +--> managed Bash
                      +--> later Autotools consumers

Managed Autoconf/autom4te, M4, Perl, gettext/autopoint, makeinfo, and the pinned
gnulib checkout are prerequisites of the current maintainer-source sed path.
They are not later QEMU artifacts that should be moved ahead of sed; today
they remain root/tool prerequisites. A future release-style sed source profile
could retire some of these maintainer-only edges, but moving managed sed ahead
of Automake would instead create a bootstrap cycle.

Keeping managed sed before Git and Bash is intentional. Those downstream
builds may use the promoted GNU sed through ``SED``/``PATH``; moving sed after
them would throw away the benefit of the managed tool without removing any
real prerequisite.

Bash bootstrap profile
----------------------

The managed Bash fork is used as a non-interactive implementation shell for
WHP build modules. It is always invoked with ``--noprofile --norc`` at the
orchestration boundary, so the bootstrap does not need to reproduce a full
interactive login shell.

The QEMU profile keeps the Bash language features already used by WHP scripts,
including indexed arrays, ``[[ ... ]]`` conditionals, arithmetic
``(( ... ))``, and process substitution. ``scripts/ensure-bash.py``
executes a runtime contract probe after installation and on cache reuse so a
future configure change cannot silently remove those required features.

The following subsystems are deliberately disabled in the managed profile:

* Readline, history, and bang-history. They are interactive facilities. This
  also removes Bash's normal build dependency on its bundled Readline/history
  archives; the pinned Bash Makefile lists 31 Readline objects and five
  history-library objects behind those dependency variables.
* Programmable completion, aliases, and the pushd/popd directory stack. The WHP
  script tree does not use those shell facilities.
* Coprocesses and ``/dev/tcp``/``/dev/udp`` network redirections. Build
  orchestration uses explicit subprocesses and tools instead of Bash network or
  coprocess primitives.
* Restricted-shell mode and Bash debugger support. Neither is part of the WHP
  build-shell contract.
* Imported environment functions. WHP scripts do not export functions with
  ``export -f``, and disabling implicit function import reduces caller
  environment influence on the managed build shell.

This is intentionally a selective profile, not Bash's
``--enable-minimal-config``. The latter disables arrays, process
substitution, conditional commands, arithmetic commands, and other syntax that
the WHP already uses, so adopting it would create a fragile re-enable list.

GNU Make bootstrap boundary
---------------------------

The WHP owns the pinned ``toolchains/make`` fork and downstream bootstrap
consumers should honor one selected GNU Make through ``MAKE_CMD`` or
``MAKE``.  Bash, libisofs, OpenBIOS, SeaBIOS, the POSIX Python fallback,
and the i386 EFI GRUB bootstrap therefore converge on the same executable
selection instead of rediscovering ``make`` independently.

The pinned GNU Make ``master`` is currently a maintainer-source tree.  It
contains GNU Make's ``build.sh``, which can compile Make without an existing
Make program, but ``build.sh`` consumes ``build.cfg`` and other outputs
created by ``configure``.  The Git tree does not carry the release-style
generated ``configure``/``Makefile.in``/gnulib build inputs.  Regenerating
those inputs from the Git tree requires the Autotools/gnulib maintainer path,
whose documented prerequisites include GNU Make.

That means the fork must not yet replace the first seed GNU Make: doing so
would hide a ``Make -> Make`` cycle.  The intended promotion path is to make
the fork carry, or reproducibly produce without Make, the configured-source
inputs needed by ``build.sh``.  Once that path is validated, the pinned fork
can move from ``planned`` to ``managed`` and sit before Python, Bash, and
the other Make-consuming bootstraps.

GNU Libtool bootstrap boundary
------------------------------

The pinned ``toolchains/libtool`` fork is a maintainer-source checkout, so
QEMU must generate its release-style Autotools files before configuration.
The managed bootstrap uses the fork's exact gitlink plus its nested
``gnulib`` and ``gl-mod/bootstrap`` gitlinks, stages them in an isolated
build workspace, suppresses translation downloads, and records the generating
Autotools identities in the cache marker.

This does not create a Libtool-to-Libtool cycle.  GNU Libtool's own
``bootstrap.conf`` deliberately sets ``LIBTOOLIZE=true`` because
``libtoolize`` is an output of the package being bootstrapped.  The WHP
helper also removes inherited ``LIBTOOL`` and ``LIBTOOLIZE`` variables
before running the maintainer bootstrap.  The real seed edge is therefore
GNU Make + Autoconf/Automake + Help2man/Texinfo/xz -> Libtool.

``BOOTSTRAP_LIBTOOL=auto`` keeps a complete existing GNU Libtool pair when
one is already available and otherwise attempts the pinned fork.
``BOOTSTRAP_LIBTOOL=1`` forces the fork.  A successful private bootstrap
exports ``LIBTOOL``, ``LIBTOOLIZE``, and its aclocal macro directory so
libisofs and future Autotools consumers see one coherent Libtool revision.
Apple's unrelated ``/usr/bin/libtool`` is never accepted as GNU Libtool.

libisofs bootstrap boundary
----------------------------

The Darwin libisofs bootstrap is an artifact-library edge, not a Meson-owned
subproject.  QEMU currently uses the pinned fork only for the metadata-assisted
ISO path.  Its QEMU profile is static-only, library-only, and documentation-free:
``--disable-shared --enable-static --disable-demo --disable-docs``, with libacl
and libjte disabled.  The standalone libisofs fork keeps both demo and Doxygen
documentation enabled by default.

The prerequisites which must exist *before* libisofs are:

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Dependency
     - WHP state
     - libisofs edge
   * - Python >= 3.9
     - managed/root
     - Runs ``scripts/ensure-libisofs.py``; therefore it is earlier than the
       libisofs source/configure/build steps.
   * - Git
     - managed after seed
     - Reads the QEMU gitlink and materializes the pinned
       ``toolchains/libisofs`` checkout.
   * - GNU Make
     - root seed
     - Builds and installs libisofs.  The selected seed is exported through
       ``MAKE_CMD`` and ``MAKE`` before Automake, Libtool, or libisofs run.
       The pinned WHP Make fork remains ``planned`` and is not promoted across
       its unresolved Make-to-Make maintainer-source cycle.
   * - Autoconf + GNU M4
     - managed/root
     - Managed WHP Autoconf regenerates ``configure`` from the fork's
       maintainer source; GNU M4 remains a root capability checked by the
       libisofs helper.
   * - Automake/aclocal
     - managed/root
     - Generates the Makefile inputs.  The WHP Automake fallback is prepared in
       the seed/tool phase before libisofs.
   * - GNU sed
     - managed/root
     - Used by Autoconf/configure and selected before the libisofs bootstrap.
   * - GNU Libtool/libtoolize
     - managed/root
     - Must precede libisofs.  The managed Libtool path is deliberately after
       native LLVM promotion so its cached archive/binutils identities match the
       compiler family that will build libisofs.
   * - configuration shell
     - managed/root
     - Bash is preferred through ``WHP_BUILD_BASH``/``CONFIG_SHELL``; the
       generated project-local Libtool is tied to this configure environment.
   * - C compiler + archive/binutils tools
     - root/promoted
     - Seed compiler when native LLVM is disabled; promoted WHP LLVM tools when
       ``BOOTSTRAP_NATIVE_LLVM=1``.
   * - Darwin SDK/libSystem
     - root
     - Supplies the platform headers/runtime and the pthread/iconv facilities
       used by the current Darwin profile.
   * - zlib
     - root library
     - libisofs links zlib during its own build and exports ``-lz`` to static
       consumers.  This edge exists before QEMU's later Meson dependency
       resolution and must not be modeled as a dependency on the QEMU build.
   * - pkg-config/pkgconf
     - root probe tool
     - Detects a usable host libisofs and validates the private static install.
       QEMU's later Homebrew path-normalizing wrapper is configure-state policy,
       not a library which must be built before libisofs.

The current audit found no WHP library or firmware component built *after*
libisofs which libisofs actually consumes.  SDL/JACK are independent QEMU host
libraries; the PowerPC/OpenBIOS, SeaBIOS/GRUB, and mold lanes are also
independent.  The ordering defect was tool selection rather than a missing
library build: canonical GNU Make selection previously happened in the later
QEMU preparation stage even though Automake, Libtool, and libisofs had already
needed Make.  The public build boundary now establishes the seed GNU Make
identity first, while the later stage only re-validates the same selection.

ACL and libjte are disabled in the QEMU libisofs profile and therefore are not
active edges.  The demo and documentation are both disabled at configure time.
The fork wraps its Doxygen target plus documentation install/uninstall hooks in
``BUILD_DOCS``, so QEMU cannot accidentally install stale ``doc/html`` output and
Doxygen is not part of the QEMU libisofs prerequisite graph.  This does not
affect QEMU's own documentation targets.
On macOS, the QEMU profile treats libisofs as an ABI-sensitive dependency
rather than merely checking that it compiled. The fork validates the 64-bit
Darwin widths exposed through its public API: data pointers, ``size_t``,
``ssize_t``, ``off_t``, ``time_t``, ``ino_t``, and typed xinfo function
pointers. The existing arm64e configure gate separately requires Clang
pointer-authenticated calls.

QEMU repeats that contract in its consumer link probe, rejects Apple-silicon
deployment targets below macOS 11, and queries the installed static archive
with ``lipo -archs``. The private archive must report exactly one architecture
and it must exactly equal the requested Mach-O architecture. This is
significant for ``arm64e`` because it is a distinct Mach-O CPU subtype, not
merely an ``arm64`` spelling alias.

Do not use ``llvm-lipo -verify_arch`` on ``libisofs.a`` with the pinned LLVM
fork. Its ``VerifyArch`` implementation handles Mach-O objects and universal
binaries but not ``Archive`` inputs, whereas its ``-archs`` path explicitly
constructs an archive slice, validates that all archive members share the same
CPU type and CPU subtype, and reports the subtype-aware architecture name.

The xinfo implementation was audited for pointer-authentication hazards. Its
function-pointer keys remain stored, compared, and invoked as the declared
``iso_node_xinfo_func`` type rather than being flattened through integer or
data-pointer storage.
The private QEMU install no longer invokes blanket ``make install``. It calls
only Automake's generated ``install-libLTLIBRARIES``,
``install-libincludeHEADERS``, and ``install-pkgconfigDATA`` targets. The
library target uses Libtool's explicit ``--mode=install $(INSTALL)`` contract;
the header and pkg-config targets use Automake's data installer path.

Caller overrides of ``INSTALL``, ``INSTALL_DATA``, ``INSTALL_PROGRAM``,
``INSTALL_SCRIPT``, ``INSTALL_STRIP_PROGRAM``, ``MKDIR_P``, ``mkdir_p``, and
``LN_S`` are removed before configure, so an ambient build environment cannot
replace the locally detected install utilities. The targeted install bypasses
libisofs' ``install-exec-hook`` (including ldconfig), documentation hooks, and
any future package install class not explicitly admitted to QEMU.

Libtool may still create ``libisofs.la`` while installing the static library;
QEMU removes that private Libtool metadata immediately because downstream QEMU
consumers use the archive and pkg-config metadata instead. A post-install
surface check requires ``libisofs.a``, ``libisofs.h``, and ``libisofs-1.pc``
and rejects shared libraries, demos, generated documentation, or a leftover
``libisofs.la``.
The QEMU configure profile also disables local-filesystem metadata features
that the Darwin call site does not request: xattr import/export, Linux
``chattr`` flags, XFS-style project IDs, and the directory-record prediction
debug check. Zlib stays enabled because QEMU imports existing ISO images and
compressed-image content remains a valid read-path capability.

After ``bootstrap`` has generated ``configure`` and ``Makefile.in``, the QEMU
workspace prunes maintainer-only material that cannot participate in the
private build: ``demo/``, ``doc/``, the obsolete ``test/`` tree, GitHub/IDE
metadata, and release-planning text such as ``TODO``/``ChangeLog``/``Roadmap``.
Core source, ``configure.ac``, ``Makefile.am``, ``acinclude.m4``, generated
Autotools helpers, and dependency tracking remain intact. The fork also avoids
generating ``doc/doxygen.conf`` at configure time when ``--disable-docs`` is
active, so pruning ``doc/`` cannot create a configure-time dependency hole.



Darwin still falls through libisofs' generic local-filesystem feature branch,
so native macOS xattr import/export remains a feature gap. Do not map Darwin
onto the Linux or FreeBSD AAIP adapter as an ABI shortcut: the underlying
xattr interfaces have different platform signatures and semantics. A future
Darwin adapter should be implemented and probed explicitly.


Wine and Windows ABI validation
-------------------------------

The WHP Wine fork is pinned at ``toolchains/wine`` from the
``retrochristian5000/water`` repository.  The source identifies itself as
Wine 11.16 and already carries a generated ``configure`` script, so an
ordinary build does not need to regenerate Autoconf inputs first.

Wine has four distinct WHP roles and they must remain distinguishable:

#. **Windows API implementation evidence.** Wine's ``include/*.h``,
   ``include/*.idl``, and ``dlls/*`` trees expose API names, structures,
   interfaces, DLL organization, and implementation behavior. They are useful
   comparative evidence for Windows API studies, but they are not automatically
   the normative definition of Microsoft's ABI or API.
#. **Windows cross-development tools.** Wine supplies tools including
   ``winegcc``, ``winebuild``, ``widl``, ``wrc``, and
   ``winedump``. These provide an independent lane for producing and
   inspecting PE/COFF-facing artifacts.
#. **LLVM Windows validation.** WHP LLVM may produce Windows-targeted PE/COFF
   binaries first; Wine can then execute or inspect compatible outputs. This
   direction is ``LLVM -> Windows artifact -> Wine validation``, not a
   Wine dependency inside LLVM's bootstrap.
#. **Wine cross-build research.** Wine's configure logic supports PE
   architecture selections including ``aarch64`` and ``arm64ec``, and
   cross-compiling Wine requires an already-built Wine tools directory through
   ``--with-wine-tools=DIR``. Native Wine tools and target Wine artifacts
   therefore form separate build roles.

Do not merge Windows ``arm64ec`` with Apple ``arm64e``. ``arm64ec``
belongs to the Windows PE/ABI lane; ``arm64e`` belongs to Apple's
pointer-authenticated Mach-O ABI lane. A spelling resemblance is not an ABI
edge.

The first Wine integration is intentionally ``planned``, not
``managed``. The full Wine feature surface has many optional dependencies,
and a WHP bootstrap should select an explicit profile rather than silently
turn every available host library into a required build root. Wine's basic
documented source-build requirements include GNU Make, flex, bison, a host
compiler, and the platform's development headers/tooling; graphics, audio,
security, multimedia, USB, printing, and similar libraries remain conditional.

Darwin user-mode recovery
-------------------------

Darwin/macOS user-mode is a ``planned`` QEMU execution target rather than
a third-party dependency. The recovery contract and ABI boundaries are
tracked in :ref:`whp-darwin-user`. LLVM may generate Mach-O test fixtures
for this lane, but Darwin-user must not become a prerequisite for the LLVM
bootstrap that generates those fixtures.

Meson-owned subprojects and wraps
---------------------------------

Meson wraps such as dtc, slirp, Berkeley SoftFloat/TestFloat, libblkio,
libvfio-user, keycodemapdb, and Rust crates are not top-level git submodules.
They remain inside QEMU's Meson dependency graph.  Do not pre-build them from
the WHP launcher merely to make them look like the top-level
``toolchains/*`` sources.

Aften and JACK
--------------

Aften and JACK have two distinct possible edges and they must not be merged.

The WHP JACK fork uses Aften for the macOS CoreAudio server driver's AC-3
encoder.  Its ``--client-only`` profile deliberately skips Aften because that
server driver is not compiled.  QEMU's current ``scripts/ensure-jack.py``
uses ``--client-only``, so the present QEMU JACK bootstrap does not need to
build Aften first.

Aften nevertheless remains a first-class editable submodule.  It may be used
directly by a future QEMU A/52/AC-3 audio sink or another QEMU feature without
being routed through JACK.  That direct QEMU edge is currently ``planned``:
the QEMU Meson/audio tree does not yet link libaften.

The Aften fork recognizes ``aarch64``, ``arm64``, and ``arm64e``.
AArch64 currently uses the portable scalar C implementation; x86 and
PowerPC/AltiVec have the existing architecture-specific SIMD code.  NEON is
therefore an optimization opportunity, not a dependency that should be
claimed as already implemented.

Circularity guards
------------------

#. The native compiler selected by ``cc.sh`` is a seed dependency. The WHP
   LLVM fork may replace compilers only after LLVM has been built; LLVM must
   never be selected as the compiler required to bootstrap its own first stage.
#. Seed Git remains mandatory for the initial QEMU checkout/source refresh and
   for materializing the pinned Git fork. Managed Git may take over only after
   it has been built; a local-only build must not replace HTTPS-capable seed Git.
#. A toolchain may not require the QEMU binary it is being built to produce.
#. Native LLVM must bootstrap from an existing host compiler; it must not make
   itself its own root dependency.
#. Wine may validate Windows artifacts produced by LLVM, but Wine must not
   become a prerequisite for bootstrapping the LLVM compiler that produces
   those artifacts.
#. A Wine cross-build that uses ``--with-wine-tools=DIR`` must consume an
   already-built compatible native Wine tools tree; the target build must not
   recursively depend on itself to create those tools.
#. The pinned GNU Make fork must not be promoted to the first Make executable
   while its maintainer-source preparation still needs a seed GNU Make.
   GNU Make's no-Make ``build.sh`` is usable only after its configured inputs
   have been produced.
#. Managed Autoconf must not bootstrap the Automake instance that it itself
   consumes. Seed Autoconf/autom4te feeds the first Automake stage; that
   Automake stage then builds the pinned Autoconf for later consumers.
#. Managed GNU sed must not replace the seed sed before Automake exists.
   Python and Automake consume the validated seed; the sed maintainer bootstrap
   then consumes Automake and promotes the pinned GNU sed for later consumers.
#. The pinned GNU Libtool fork must not consume an installed Libtool to
   bootstrap itself. Its maintainer bootstrap uses ``LIBTOOLIZE=true``, and
   the WHP wrapper clears inherited ``LIBTOOL``/``LIBTOOLIZE`` before
   generating and installing the private toolset.
#. Aften may feed a full JACK macOS server build and may later feed QEMU
   directly.  JACK must not become the only route through which QEMU can reach
   Aften.
#. QEMU's JACK ``--client-only`` bootstrap must not grow a false Aften
   dependency merely because the full JACK server has one.
#. Host tools such as Python, Ninja, Bash, CMake-built dependencies, and LLVM
   bootstrap stages must not inherit guest/cross-target flags accidentally.
#. Firmware sources are reached through the QEMU graph when they produce QEMU
   artifacts.  Preparation may establish exact source/tool identities but must
   not compile the final firmware artifact early.
#. Recursive submodules are synchronized to exact gitlinks.  Following nested
   branch tips would create an untracked dependency edge and is forbidden.

Audit rule
----------

Every top-level path in ``.gitmodules`` must appear in this ledger.  The
static ``scripts/tests/test-whp-dependency-ledger.py`` check enforces that
coverage.  Finding the path in the ledger does not mean every transitive
upstream prerequisite has been audited; unknown or newly discovered
requirements are added here as evidence is found rather than guessed.
