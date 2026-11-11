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

GNU Make source Autoconf compatibility
------------------------------------

The WHP Make fork and its QEMU gitlink must agree on declared Autoconf and
Automake minima: ``configure.ac`` matches the versions in
``bootstrap.conf`` (currently Autoconf 2.72, Automake 1.16.5).
The legacy Make-specific ``gl/m4/acinclude.m4`` timestamp probe now uses
``AC_COMPILE_IFELSE`` rather than obsolete ``AC_TRY_COMPILE``, and
its network-library detection reports cache hits with ``AC_MSG_RESULT``
rather than the obsolete ``AC_FD_MSG`` descriptor. The Make helper checks
these source contracts before generating Autoconf output. These corrections
remove real obsolescence warnings; they are distinct from the previously
repaired macOS SDK/libSystem handoff. Source/gnulib caches remain keyed to
their pinned revisions, without clearing them to mask failures.

GNU Make native SDK handoff
----------------------------

On macOS, a compiler that links a bootstrap probe with explicit
``-isysroot`` is not proof that GNU Make's later Autoconf ``configure`` and
no-Make ``build.sh`` steps inherit the SDK. The managed Make helper validates
the selected Xcode/CLT root and exports the same ``SDKROOT`` through compiler
selection, configure, and the build stage, rather than falling back to an
unrelated developer root. A compile/link/execute probe using the sanitized
configure environment catches missing libSystem before source generation.
The configured-tool marker includes ``SDKROOT`` so output from a different
SDK cannot be reused. Target compiler/linker flags and Autoconf cache
variables remain isolated.

The gitlink recorded by the QEMU commit is authoritative.  A branch named in
``.gitmodules`` is discovery metadata, not permission to build an arbitrary
branch tip.

LLVM fork-to-QEMU pin propagation
---------------------------------

An LLVM source repair is not integrated into the WHP QEMU bootstrap merely
because it was pushed to ``retrochristian5000/LLVM`` ``main``.  At the end of
each LLVM fork edit round, update ``toolchains/llvm-project`` to the intended
published LLVM commit and push the corresponding QEMU gitlink commit to
``master`` in the same round.  A local gitlink change or an unpushed commit
does not complete the handoff.

Before advancing the pin, verify that the LLVM commit exists on the fork and
is a fast-forward descendant of the current gitlink.  Do not overwrite local
submodule changes, silently switch to ``main`` at build time, force-push a
rewound gitlink, or rebuild unrelated toolchains.  Record the target LLVM SHA
and the resulting QEMU SHA; verify the remote ``master`` tree still contains
that exact gitlink.  If the update cannot be pushed, report it explicitly as
an unintegrated LLVM repair rather than calling the bootstrap fixed.

QEMU's bootstrap initializes absent LLVM sources at the recorded gitlink
and advances an initialized detached checkout only when the pin is a proven
fast-forward descendant.  A newer local descendant is retained and its actual
commit is recorded in bootstrap cache identities; divergence or incomplete
history fails without moving the checkout.  Bootstrap never uses
``--remote`` or silently rewrites the parent gitlink.  Publishing a new
pin still requires an explicit, separately pushed QEMU gitlink commit;
compiler and LLDB success requires separate compilation and test evidence.

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

Required dependency guard policy
--------------------------------

This ledger is the dependency inventory and classification authority; it is
not a second source of immutable commit gates.  The parent Git gitlink records
the reproducible baseline, while an initialized checkout may use a newer
*provable descendant*.  Its effective HEAD supplies build/cache identity.
A published gitlink update remains required when integrating source changes.

Apply checks at the owning boundary, without repeating equivalent guards in
each downstream consumer:

* ``root``: require a working host capability, such as a compiler that can
  compile and link.  Prefer actual capability checks over redundant exact
  version or Git revision gates; a missing root blocks only its consumers.
* ``managed``: use common submodule reconciliation once to prove ancestry,
  recover bounded shallow history, and preserve newer descendants.  Downstream
  build stages must not introduce separate ``HEAD == gitlink`` or bare
  ancestry tests.  Verify only source interfaces and ABI actually consumed.
* ``graph``: let QEMU configure, Meson, or Ninja resolve the dependency;
  do not impose a duplicate pre-configuration source pin check.
* ``conditional``: check only when the feature or target is enabled.
  Failure of an unrelated optional dependency must not stop a required path.
* ``planned``: do not initialize or block normal builds for inactive sources.

Preserve guards against checkout rewinds, unexpected worktrees, overwriting
local edits, and unverified ancestry.  Do not bypass real compiler, linker,
ABI, checksum, or source-interface failures.  Incomplete ancestry is
unverified, not proof of divergence: history recovery must not move HEAD.
Report the failing dependency and active consumer rather than globally
rejecting unrelated build stages.

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
   * - ``toolchains/xen``
     - ``xen``
     - yes
     - Xen source/toolstack fork; ``planned`` managed source for QEMU's existing Xen backend. Current production discovery still enters through the feature-gated ``xencontrol`` pkg-config dependency rather than an unconditional Xen source build.
   * - ``toolchains/grub``
     - ``grub``
     - yes
     - conditional SeaBIOS/EFI and hybrid-image helper.
   * - ``toolchains/ninja-builder``
     - ``ninja-builder``
     - yes
     - host Ninja fallback; requires Python plus a host C++17 compiler.
   * - ``toolchains/sccacher``
     - ``sccacher``
     - yes
     - Optional pinned sccache compiler-cache helper; requires Cargo and Rust >= 1.91. When native LLVM PCH is on, sccache caches only LLVM C compilation; LLVM C++ compilation bypasses sccache to prevent unsupported PCH cache reuse. The QEMU cache policy remains separate.
   * - ``toolchains/meson``
     - ``Meson``
     - yes
     - Default WHP Meson fork for new QEMU configurations, invoked through the selected virtual-environment Python and pinned by gitlink. Explicit ``WHP_MESON_PROVIDER=venv`` retains the Meson wheel; saved provider selections are preserved. The fork requires Python >= 3.10.
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
     - Managed GNU Make host tool behind an explicit seed-Make boundary. Automake/Autoconf generate the maintainer inputs, the helper pins gnulib exactly, GNU Make's ``build.sh`` compiles the managed binary without recursive Make, and downstream consumers use the promoted executable.
   * - ``toolchains/git``
     - ``git-tools``
     - yes
     - Managed Git fork behind an explicit seed-Git boundary. Seed Git still obtains QEMU and materializes the fork; only an HTTPS-capable managed build may replace it for later remote/submodule work.
   * - ``toolchains/sdl``
     - ``SDLosaurus``
     - yes
     - SDL3 shared-library fallback (dylib/so/DLL), built by CMake + Ninja + the QEMU host C compiler. Static SDL3 archive output is disabled; QEMU retains normal pkg-config discovery.
   * - ``toolchains/jack``
     - ``jack``
     - yes
     - JACK client library for QEMU; Python/Waf + C/C++.  Full macOS server builds have a conditional Aften edge.
   * - ``toolchains/zlib``
     - ``ZLIB``
     - yes
     - Managed static zlib has two explicit roles: an isolated Git-bootstrap
       prefix built with ``CC_FOR_BUILD`` before managed Git, and an artifact
       prefix for QEMU/libisofs resolved after compiler promotion. Both use the
       same pinned source materialized through the seed-Git boundary.
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
      +--> seeds/cc.sh native C seed
      |      +--> Python fallback
      |      +--> GNU sed / bootstrap-zlib / Git / Bash / SDL host builds
      +--> seeds/cxx.sh native C++17 seed -> Ninja / JACK / native LLVM
      |
      +--> seed Git
      |      +--> QEMU source checkout/update
      |      +--> pinned WHP zlib source -> bootstrap zlib (seed C + seed Make)
      |      +--> pinned WHP Git fork
      |             +--> managed full Git (HTTPS-capable, needs bootstrap zlib) -> later submodules
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
      |      +--> Python POSIX fallback
      |      +--> Git-bootstrap zlib (after seed Git, before Autotools)
      |      +--> Automake / Autoconf maintainer stages
      |               |
      |               +--> pinned WHP Make fork
      |                       |
      |                       +--> managed GNU Make
      |                               +--> GNU sed
      |                               |      +--> managed Git
      |                               |              +--> Ninja (native C++17)
      |                               |              +--> Bash
      |                               +--> WHP Libtool bootstrap
      |                                       |
      |                                       +--> libisofs
      |
      +--> optional native LLVM
             |
             +--> QEMU host compiler
             |      +--> artifact zlib
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

Native LLVM transitive dependency inventory
---------------------------------------------

The LLVM submodule at ``toolchains/llvm-project`` is an independent source
repository. The actual QEMU consumer is
``scripts/bootstrap-native-clang.bash``, not every project or optional
dependency supported by upstream LLVM. This inventory records *capabilities*,
their existing QEMU provider, and which build lane activates them; it does not
declare all listed tools mandatory QEMU roots.

.. list-table::
   :header-rows: 1
   :widths: 19 27 25 29

   * - LLVM dependency / capability
     - Active boundary
     - Existing QEMU provider
     - Status / next action
   * - Host C and C++17-or-newer compiler, linker, native headers
     - LLVM's initial CMake configure and compiler build
     - ``seeds/cc.sh``, ``seeds/cxx.sh``, host SDK/toolchain selection
     - Required seed; never bootstrap LLVM with its own unfinished compiler.
   * - CMake
     - LLVM configure on a cache miss or source/configuration change
     - Validated ``seeds/cmake.sh`` selects an existing host CMake
     - Required capability for LLVM rebuild; no managed CMake source is
       registered in QEMU. Selection is a seed, not a CMake source build.
   * - Ninja
     - LLVM compilation and distribution install
     - ``toolchains/ninja-builder`` or admitted host Ninja
     - Required build executor; reuse the selected installation.
   * - Python
     - QEMU bootstrap scripts and selected LLVM generators/utilities
     - ``toolchains/python-runtime`` or validated host Python
     - Shared bootstrap capability; do not create a second Python environment
       solely for LLVM.
   * - Git and basic host utilities
     - Pin/revision verification, staging and shell orchestration
     - Selected seed/managed Git; shell, sed, mkdir, mv, rm, ln, mktemp
     - Active script preflight requires these utilities. No duplicate fork
       merely to satisfy LLVM.
   * - Xcode/CLT and macOS SDK
     - Native macOS compiler/linker tests and compiler-rt
     - ``macos-developer-tools.sh``, ``xcrun``, ``sw_vers``
     - Host-provided platform capability, not a Git submodule; verify the
       macOS SDK and native ABI without admitting an iOS SDK.
   * - compiler-rt
     - Native macOS runtime artifacts
     - LLVM's own ``compiler-rt`` runtime sources
     - Enabled on macOS; no independent QEMU third-party library bootstrap.
   * - zlib and zstd
     - Optional LLVM compression support
     - QEMU zlib fork; QEMU's separate zstd dependency discovery
     - Both explicitly OFF in this native LLVM configuration; neither is
       a required LLVM bootstrap edge. Do not build them early for LLVM.
   * - libxml2
     - ``NATIVE_LLVM_WINDOWS_MANIFEST=1`` selects ``llvm-mt``
     - No LLVM-specific managed source provider recorded
     - ``LLVM_ENABLE_LIBXML2=FORCE_ON`` in this optional lane. An
       external development library is required here; record a provider
       decision before adding or rebuilding any source.
   * - LLDB optional integrations
     - ``NATIVE_LLVM_ENABLE_LLDB`` (auto enables on macOS)
     - LLDB is part of the pinned LLVM source tree
     - LLDB Python, SWIG, Lua, libedit, curses, LZMA, libxml2,
       Tree-sitter and protocol-server integrations are explicitly OFF.
       They must not be promoted into LLVM roots merely because LLDB is built.
   * - Compiler cache
     - Native LLVM C/C++ object compilation when opted in
     - Admitted ``ccache`` or pinned ``toolchains/sccacher``
     - Optional accelerator; cache correctness and PCH restrictions take
       precedence over saving compile time.

LLVM's source-level build configuration may support additional optional
packages, but the QEMU-selected ``LLVM_ENABLE_PROJECTS``,
``LLVM_ENABLE_RUNTIMES``, CMake flags and host platform determine which
ones are active. Before declaring a missing dependency, confirm an actual
configure/build consumer and whether a validated installed toolchain can
already be reused. The LLVM project's own source files and QEMU's recorded
gitlink remain separate authorities; never fetch an unrelated branch tip
or force a rebuild solely to populate this documentation.

LLVM deeper seed-candidate scan
------------------------------

This scan follows the current QEMU native-LLVM configuration, not every
optional feature supported by upstream LLVM. Evidence: LLVM's
llvm/cmake/config-ix.cmake, llvm/CMakeLists.txt, clang/CMakeLists.txt,
lld/CMakeLists.txt, lldb/CMakeLists.txt, compiler-rt/CMakeLists.txt,
and QEMU's scripts/bootstrap-native-clang.bash.

* CMake: actively required for LLVM configuration; ``seeds/cmake.sh``
  now admits an existing CMake >= 3.20 with explicit override precedence.
  It does not build CMake or depend on LLVM, breaking the bootstrap cycle.
* Ninja: required executor; QEMU already selects NINJA_CMD and its
  managed ninja-builder fork. Reuse this authority before adding a seed.
* Python3: actively discovered by LLVM and Clang through CMake; compiler-rt
  also probes Python3 and retains an old Python2 fallback. Audit forwarding
  the selected QEMU Python as Python3_EXECUTABLE before creating another
  interpreter selection or treating Python2 as required.
* Apple developer tools: xcrun, sw_vers, SDK and native linker discovery
  are macOS capabilities supplied by Xcode/CLT. An xcrun seed wrapper may
  help maintain coherent identity, but it is not a source-fork dependency.
* Apple libtool: Darwin compiler-rt includes CMake UseLibtool for archive
  handling. Do not confuse the Apple developer-tool executable with the
  GNU Libtool fork tracked under toolchains/libtool. Check actual commands
  before considering a Darwin-specific selector.
* C library and SDK facilities: LLVM probes Threads (required), dl, rt,
  iconv and Backtrace, among others. A probe is not proof that an additional
  standalone source package is necessary on every host.
* Feature-only packages: zlib, zstd, libedit, FFI, ICU, curl, httplib and
  Z3 are probed under feature guards. The current native LLVM bootstrap
  explicitly disables zlib, zstd, libedit, FFI and Z3; do not elevate
  inactive or opportunistic probes into mandatory bootstrap roots.
* Perl and LLDB binding tools: Clang looks for Perl when its tests are
  enabled; QEMU disables Clang tests. LLDB Python/SWIG, Lua, curses,
  libedit and other optional integrations are disabled by QEMU's LLDB
  profile. Existing seeds/perl.sh is not a missing LLVM root here.
* TableGen: llvm-tblgen and clang-tblgen are generated by LLVM's own
  build graph, not external package seeds to download separately.

Future seed decision gate: record the active consumer, host/target ABI,
minimum working capability, known host provider, source/cache identity
and earliest valid dependency order. Do not create a managed fork or
repeat a build merely because a CMake probe names a dependency.

External host-tool edges by active consumer
------------------------------------------

The submodule registry covers managed source, not every executable invoked
by a bootstrap script. Classify external dependencies at their active consumer
boundary; a root for one build lane is not automatically a universal QEMU root.

.. list-table::
   :header-rows: 1
   :widths: 19 27 54

   * - Classification
     - Consumer
     - Required capability / behavior
   * - ``root`` (normal configuration)
     - QEMU configure and Meson
     - Python, native compiler, Ninja, and pkg-config-compatible dependency
       discovery. The ``pkg-config.sh`` seed's *early host-tool* fallback
       does not make pkg-config optional once QEMU configuration requires it.
       The default pinned Meson fork needs Python >= 3.10, even though the
       fallback Python bootstrap accepts >= 3.9.
   * - ``conditional``
     - PowerPC GCC/binutils **source rebuild**
     - GNU Make; tar with ``.tar.xz`` extraction support; bzip2, gzip, Perl,
       ln, mv and rm; curl **or** wget for downloads; shasum **or** sha256sum
       for checksum validation. Source extraction and GCC's
       ``contrib/download_prerequisites`` belong to this rebuild lane.
       Reusing a validated installed PowerPC toolchain does **not** require
       these rebuild-only tools. Early host identity probes remain separate.
   * - ``conditional``
     - OpenBIOS / SeaBIOS preparation
     - GNU Make and Git for selected firmware source preparation. Auto mode
       can disable that firmware lane on failure without blocking core QEMU;
       explicit enablement reports an error instead.
   * - ``conditional``
     - IA32 EFI GRUB source/LLVM expansion
     - GNU Make plus tar, mktemp, cksum, awk and Git for its helper; CMake
       and source generators are needed when rebuilding the optional toolchain.
       Homebrew auto-install is not a universal core QEMU prerequisite.
   * - ``conditional``
     - macOS toolchain and LTO manifests
     - ``cksum`` and ``awk`` sign verification manifests when
       ``MACOS_VERIFY_TOOLCHAIN=1`` or ``QEMU_HOST_LTO=1``, respectively;
       these checks do not apply to disabled or unrelated host lanes.
   * - ``conditional``
     - Optional mold linker
     - CMake and native C/C++ linking only if mold preparation is selected;
       mold is not a universal linker or a Darwin Mach-O prerequisite.

A missing-tool preflight alone does not establish a universal dependency.
Check whether the tool is used before or after a validated cache hit, which
feature activates it, and whether failure is fatal, a fallback or a deliberate
skip. Do not promote download or source-generation tools into the common root.

Pinned Meson source boundary
---------------------------

The WHP fork at ``toolchains/meson`` is available for controlled Meson
development.  It is a lazily initialized, gitlink-baselined source tree,
not an unconditional dependency build or a replacement on ``PATH``.

QEMU defaults to the WHP Meson fork for new configurations.
QEMU's own virtual-environment Python invokes ``toolchains/meson/meson.py``
directly, without installing a separate Meson wheel.  The explicit
``WHP_MESON_PROVIDER=venv`` compatibility option installs and uses
``pyvenv/bin/meson``.  Existing saved ``.whpconfig`` selections remain
authoritative; a saved ``venv`` selection is never silently migrated.  The fork is initialized from the exact
``toolchains/meson`` gitlink only when downloads are enabled.  An initialized
checkout at a newer descendant is preserved, while divergent or unverifiable
history and local source edits cause an explicit failure, never a reset or
branch switch.  The selected Python from QEMU's existing ``pyvenv``
runs ``toolchains/meson/meson.py``; no duplicate Python environment is
created.  The fork reports development version ``1.12.99`` and requires
Python >= 3.10, whereas the default QEMU Python selection accepts >= 3.9.
The selected provider is retained by ``config.status``.
The menuconfig ``QEMU Meson provider`` choice maps to
``WHP_MESON_PROVIDER=fork|venv``.  Incremental configuration identity
tracks the provider and the effective Meson checkout commit; existing fork
checkouts are verified for source edits and ancestry even when configuration
is otherwise up-to-date. Changing providers requests reconfiguration without
wiping existing build outputs.

Use the explicit venv provider to compare DTC wrap and incremental
configuration behavior in isolated or already compatible build trees.
Changing providers does not repair Git checkout failures in
``scripts/ensure-dtc-subproject.py``, which runs before Meson setup.  Never
wipe an incremental build directory to switch providers, and do not infer
successful end-to-end integration from Meson version selection alone.

To inspect the exact source when needed, use
``git submodule update --init toolchains/meson``.  The configured
``branch = master`` in ``.gitmodules`` is discovery metadata only; the
QEMU gitlink determines the revision and must never be replaced by an
unreviewed branch tip.

Core QEMU dependencies represented by the minimal CI/build metadata include
GLib/gmodule, zlib, pixman, libffi, and libfdt in addition to the shell,
compiler, Python, Meson, Ninja, pkg-config, and basic build utilities.  The WHP
GLib fork is pinned at ``toolchains/glib`` so QEMU has a repository-owned GLib
source alongside the system/package-manager dependency path.  The
full ``tests/lcitool/projects/qemu.yml`` profile adds feature-gated libraries
such as ALSA, GTK, GnuTLS, libcurl, libiscsi, libnfs, libslirp, libssh,
libusb, PipeWire, PulseAudio, SDL, SPICE, zstd, and others.  Those optional
libraries stay feature-gated rather than becoming WHP bootstrap roots.

Xen source boundary
-------------------

QEMU already carries native Xen accelerator, backend, bus, device, and PVH
integration.  Its Meson dependency probe currently enters through
``dependency('xencontrol', method: 'pkg-config')``, so Xen remains a
feature-gated QEMU graph edge rather than a host bootstrap root.

The WHP-owned ``toolchains/xen`` gitlink records the editable Xen source
lineage without changing that production dependency contract yet.  The
submodule is therefore ``planned``: it is pinned source/provenance for a
future managed Xen toolstack/library build, but normal QEMU configuration may
continue to consume a compatible externally prepared Xen installation.

Routine QEMU source refresh must not materialize Xen merely because the
gitlink exists.  A future Xen bootstrap helper must initialize the exact
``toolchains/xen`` gitlink lazily when Xen support is selected, and it must
publish the resulting headers/libraries through the same pkg-config-facing
boundary QEMU already understands rather than bypassing Meson dependency
resolution.

WHP shell interpreter boundary
------------------------------

The universal programming standard's POSIX Shell (``sh``) and Bash
(``bash``) profiles are separate language contracts. In this QEMU fork,
WHP-owned ``*.sh`` launchers, seeds and POSIX modules use the widely
deployed POSIX.1-2017 shell subset; ``*.bash`` implementations use GNU
Bash (minimum 3.2 for the WHP build path). A Bash implementation may use
``[[ ... ]]``, arrays, ``local``, process substitution and
``pipefail``, but those constructs must not enter a POSIX launcher.
Conversely, ``$(...)``, ``$((...))``, ``printf``, ``case`` and
ordinary shell functions remain valid POSIX syntax, not Bash features.

The scope is WHP-owned scripts, not arbitrary upstream QEMU sources or user
filenames. The canonical build subset is
``scripts/whp-build/shell-inventory.bash``; first-stage programs under
``seeds/*.sh`` and shared ``scripts/whp-build/*.sh`` modules are also
checked. The lightweight regression
``scripts/tests/test-shell-dialect-contract.py`` runs ``sh -n`` for
these POSIX paths and ``bash -n`` for inventoried Bash paths; it rejects
Bash-only constructs in seed implementations. Sourced modules may have no
shebang; a launcher with one must declare the correct interpreter. These
checks establish syntax and interpreter intent, not cross-host runtime
compatibility or complete security validation. Preserve explicit error
checks, safe quoting, caller statuses and the sh-to-Bash handoff.

Root seed adapter namespace
---------------------------

Only host seed adapters live under the repository-root ``seeds/`` directory:
``awk.sh``, ``grep.sh``, ``sed.sh``, ``git.sh``, ``cc.sh``,
``cxx.sh``, ``cpp.sh``, ``ld.sh``, ``pkg-config.sh``, and ``m4.sh``. Their invocation is explicitly
``./seeds/<tool>.sh``; the root ``build.sh`` remains QEMU's public build
entry. This naming boundary leaves ``seeds/install.sh`` unambiguously
available for a future *host install-program* seed, without suggesting it
installs QEMU. No install bridge is currently provided.

The C preprocessor bridge selects the validated native C compiler driver
and invokes it with ``-E`` (and the selected macOS ``-isysroot``).
``CPP_FOR_BUILD`` is always the callable ``seeds/cpp.sh`` bridge, not a
bare Clang/GCC driver that might compile instead of preprocessing. An explicit
``CPP_FOR_BUILD`` naming a native compiler is admitted via ``WHP_CPP_SEED``,
then normalized to that same bridge; command strings such as ``clang -E``
are rejected because the bridge itself adds ``-E``. Conflicting explicit
``WHP_CPP_SEED`` and ``CPP_FOR_BUILD`` choices fail closed. The native
compiler used for host preprocessing is recorded separately, and target
``CPP`` (including cross-firmware preprocessors) remains untouched. Seed
links and native compiler checks stay bound to the source tree when the bridges
are invoked through symlinks. The ``test-cpp-seed-contract.py`` regression
checks actual driver arguments in both ordinary and SDK-root handoffs.
Old root-level adapter entrypoints are intentionally absent; callers, tests,
and CI use the namespaced paths.

The native ``m4.sh`` seed selects GNU M4 for maintainer-source
Autotools generation. It accepts explicit ``WHP_M4_SEED`` or ``M4``
without silent fallback, prefers a Homebrew GNU M4 keg on macOS before
checking ``m4`` and ``gm4`` on PATH, and rejects obsolete GNU M4
versions below 1.4.16 or implementations failing the GNU
``patsubst`` execution check. Autoconf, Libtool and libisofs resolve the same host
M4 identity before recording their own bootstrap cache markers. The seed
is not a universal runtime QEMU dependency: it belongs to maintainer-source
regeneration, rather than builds using existing generated inputs.

The native ``pkg-config.sh`` seed selects a usable ``pkg-config`` or
``pkgconf`` executable for build-machine dependency detection. Explicit
``WHP_PKG_CONFIG_SEED``, ``PKG_CONFIG_FOR_BUILD``, and ``PKG_CONFIG``
are honored in that order; invalid explicit choices fail without falling back
to an unrelated package manager. The seed does not alter the package search
database, Meson target flags, or Homebrew's existing output-normalizing
wrapper. Host-tool preparation selects it only after the dependency provider
has been chosen, and retains the prior optional fallback when no
pkg-config implementation is installed.

Bootstrap phase ordering
------------------------

Managed Perl fork and independent interpreter seed
-------------------------------------------------

The pinned ``toolchains/perl`` gitlink references the
``retrochristian5000/perl`` fork on ``main``. A working preinstalled Perl selected by ``seeds/perl.sh`` remains the
bootstrap root. The managed Perl stage now runs **before** managed
Automake/Autoconf, so their source-generation steps can use the validated
managed interpreter where available. The original interpreter remains
``WHP_PERL_BOOTSTRAP_SEED`` after promotion, avoiding any self-dependency.

Perl's generated ``Configure`` is question-driven when invoked without
options, but the managed build must never require a user to answer its
prompts. QEMU invokes it with ``-des`` (defaults, exit after configuration,
terse output), disconnects stdin from the terminal, and bounds the
configuration subprocess with a timeout. The pinned Perl source is currently
a development series (``PERL_VERSION=45`` in ``patchlevel.h``): its
default confirmation would otherwise **reject** that release, even under
``-des``. QEMU reads the staged source's ``PERL_VERSION`` before
Configure and explicitly supplies ``-Dusedevel`` only for odd-numbered
development series. Stable even-numbered series do not receive development
consent. Unknown source version formats fail rather than guessing.

The staged source tree is reconstructed on cache invalidation, so previous
``config.sh`` answers cannot silently become defaults for a different
revision or toolchain. The bootstrap marker schema changes when this
configuration policy changes. ``scripts/tests/test-perl-configure-unattended.py``
checks both development and stable option selection, noninteractive stdin,
failure propagation, and bounded configuration execution.

``scripts/ensure-perl.py`` reconciles the recorded submodule commit and
stages a Git archive under ``$BUILD_DIR/bootstrap/perl/source``, leaving
the source checkout alone. Perl's own generated POSIX ``Configure`` is
run with the native compiler and a private
``$BUILD_DIR/deps/perl`` prefix; its ordinary Makefile builds the
self-hosting miniperl/full interpreter. The install stage includes Perl's
matching core modules rather than promoting a binary alone. The final
``bin/perl`` must execute ``use strict``, ``warnings`` and
``Config`` and report the native host OS. Compiler/SDK/bootstrap-seed,
source revision and Make identities enter the incremental cache marker.

Before managed Automake and Autoconf, ``BOOTSTRAP_PERL=auto`` attempts
this fork on macOS and keeps the original Perl seed on failure. ``BOOTSTRAP_PERL=1``
requires the managed interpreter; ``BOOTSTRAP_PERL=0`` disables
promotion. Auto on other supported hosts retains the original seed unless
explicitly forced. A successful build exports ``PERL``, promotes
``WHP_PERL_SEED``, and places the managed Perl directory ahead of PATH
for the later Autotools stages and other host consumers without changing
the independent root interpreter. The native Perl stage depends on seed
Git, seed Make, an existing C compiler, and the original Perl/AWK/sed
host tools, **not** the managed Autotools tools; moving it earlier does not
create an Autoconf/Automake/Perl cycle.

``scripts/tests/test-perl-bootstrap.py`` checks source pinning,
bootstrap order, interpreter semantics, and the preserved seed.
``.github/workflows/managed-perl.yml`` exercises native builds on
macOS/Linux when CI runs; source and workflow checks alone do not confirm
that those native builds pass.

Perl native dependency inventory (macOS and other Unix hosts)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This inventory separates Perl's own requirements from QEMU's bootstrap
policy. It is not a request to install every tool or library listed below.

* **QEMU wrapper and source roots (mandatory in this workflow):**
  Python 3 executes ``scripts/ensure-perl.py``; a working Git seed
  reconciles ``toolchains/perl`` and supplies ``git archive``; an existing
  independent Perl seed is resolved by ``seeds/perl.sh``. The wrapper also
  needs a writable build directory and a native GNU Make selection. Its
  source staging uses Python's standard-library ``tarfile`` and ``fcntl``
  locking on supported Unix hosts, not an external tar executable.

* **Perl configure/build roots (mandatory):** a POSIX shell (QEMU invokes
  ``/bin/sh``), an appropriate native C compiler/linker, working C system
  headers and libraries, and Make. Perl's ``Configure`` performs Unix
  utility probes and shell commands, so basic tools such as ``sed``,
  ``grep``, ``awk`` and file utilities must be functional. QEMU already
  selects separate host seeds for those early tool families. The exact
  auxiliary command set should be verified from the pinned ``Configure``
  and its generated ``config.sh`` rather than guessed from modern
  Autoconf dependency lists. Perl's ``miniperl`` is built from source;
  neither managed Autoconf nor managed Automake is needed to create it.

* **Native archiver and archive indexing:** ``seeds/ar.sh`` verifies a
  selected host ``ar`` by compiling a native object, creating an archive,
  listing its member, extracting it, and comparing the original bytes.
  ``seeds/ranlib.sh`` indexes an archive created with that same validated
  archiver and verifies it can link. On macOS both select tools through the
  existing Xcode/CLT resolver. Explicit invalid overrides fail closed.
  Managed Perl passes ``-Dar`` and ``-Dranlib`` to ``Configure`` and
  records both paths in its incremental marker. No unbuilt LLVM, managed
  Autotools, or guest-target archive utility is needed for either seed.

* **macOS toolchain boundary:** selected Xcode/Command Line Tools,
  ``DEVELOPER_DIR``, ``SDKROOT``, the native compiler, architecture
  flags, and system headers must agree. Record the resolved SDK and compiler
  alongside ``cc``, ``ccflags`` and ``ldflags`` in the generated
  Perl configuration. An arbitrary ``CFLAGS`` or ``LDFLAGS`` inherited
  from QEMU's target compiler must not override Perl's native settings.
  Test on macOS arm64 separately from QEMU's arm64e target/compiler tuning:
  do not assume that a host-native Perl must be compiled with arm64e.

* **Optional libraries and extensions:** system and third-party choices
  (for example GDBM/DBM backends, dynamic loading, compression modules,
  locale facilities and thread support) depend on Perl's detection results
  and the requested modules. They must not be promoted to unconditional
  bootstrap dependencies without a failing required feature test. The
  Perl macOS documentation specifically warns that non-system library
  locations can cause incompatible linkage or ``dyld`` failures.
  A source build may use system-provided libraries instead of a Homebrew
  fork; any selected external library must match the native architecture.

* **Test-only or downstream tools:** ``make test`` exercises much more
  than the minimal ``make perl`` and ``make install`` path. QEMU's
  managed Automake, Autoconf, LLVM and other consumers follow Perl in the
  graph and should not be treated as its prerequisites. External ``[``
  and ``test`` are diagnostic alternatives to shell builtins; the closing
  ``]`` is an argument, not another executable or dependency.

For a failed macOS build, preserve the first failing ``Configure`` probe,
the staged ``config.sh`` and ``config.log`` if produced, the exact compiler,
SDK and resolved library locations, and the first ``make`` failure. The
incremental bootstrap marker alone records the *requested* inputs, not every
library or command Perl actually discovered. Verify reuse separately from
full native compilation; a successful no-op cache hit cannot establish
that a fresh build succeeds.

Managed Gawk fork and AWK bootstrap boundary
-------------------------------------------

The pinned ``toolchains/gawk`` gitlink references
``https://github.com/retrochristian5000/gawk.git``. A functional host
``seeds/awk.sh`` selection is needed **before** Python, source menus,
Autotools, GNU Make and later toolchain builds can run. That seed must not
be removed or replaced with an unbuilt Gawk executable. QEMU retains its
identity in ``WHP_AWK_BOOTSTRAP_SEED`` and uses it when compiling Gawk.

After Automake/Autoconf are available, ``scripts/ensure-gawk.py`` can
initialize the **pinned** fork, stage it into
``$BUILD_DIR/bootstrap/gawk/source``, configure a native-only host build,
compile ``support/libsupport.a`` and the ``gawk`` executable using the
selected native C compiler and GNU Make, and install only the validated
binary under ``$BUILD_DIR/deps/gawk/bin/gawk``. The fork contains generated
Autoconf/Automake inputs and Bison-generated C files; the helper preserves
these for tool-only builds rather than requiring documentation/extension
installation. Its marker includes actual source revision, root seed,
compiler, GNU Make, macOS SDK and selected bootstrap flags. Cache reuse
requires both matching identity and a passing executable semantics probe.

``BOOTSTRAP_GAWK=auto`` tries the fork on macOS after the Autotools
stage, falling back to the unchanged host AWK seed if it cannot build.
``BOOTSTRAP_GAWK=1`` explicitly requires the pinned fork, and
``BOOTSTRAP_GAWK=0`` retains the system seed. On other hosts, automatic
mode retains the host seed unless explicitly forced. Successful promotion
sets ``AWK`` and ``WHP_AWK_SEED`` to the built executable; the existing
locked ``seed-bin/awk`` bridge provides the same implementation to
literal ``awk`` commands. The original seed is preserved separately
to prevent a circular Gawk build dependency. No guest-target compiler,
architecture, or Apple platform SDK is used to build native Gawk.

The pinned Gawk fork is a real dependency rather than a substitute for
the native seed. If its generated files become outdated or absent, an
explicit forced build fails visibly; it does not silently fetch external
dependencies or make a new upstream source pin. The policy regression is
``scripts/tests/test-gawk-bootstrap.py``, with a focused macOS/Linux
native-build job in ``.github/workflows/managed-gawk.yml``.

The host bootstrap is split into phases rather than one flat dependency list.

**Seed/tool phase:** ``seeds/cc.sh``, ``seeds/cpp.sh``, and ``seeds/cxx.sh``, seed GNU Make, seed AWK,
seed sed, seed Git, and Python form the bootstrap roots. The low-dependency order is
``seed Git -> bootstrap-zlib -> managed Perl -> Automake -> Autoconf ->
managed Gawk -> managed Make -> managed sed -> managed Git -> Ninja ->
Bash``. The root Perl seed is selected before managed Perl and remains
available for rebuilding it. Independent small sources
are prepared before larger trees when their own prerequisites are satisfied;
size never overrides required dependency edges. These generators and host
tools are resolved before the optional native LLVM compiler build.

The seed GNU Make identity is established before the Python fallback and
exported through both ``MAKE_CMD`` and ``MAKE``. The build's visible seed
diagnostics use generic lowercase role names: ``QEMU seed awk:``,
``QEMU seed grep:``, ``QEMU seed sed:``, ``QEMU seed make:``,
``QEMU seed cc:``, ``QEMU seed cpp:``, ``QEMU seed ld:``, and ``QEMU seed git:``.
The Git seed is selected by ``seeds/git.sh --print-seed`` before the parent
source updater invokes any Git command. Both the pre/post-update HEAD checks
and the updater use that exact executable, and its selected path is logged as
``QEMU seed git:``. When source refresh is disabled or skipped, the same
selector runs once immediately before host-tool preparation instead; a
shell-only ``menuconfig`` invocation does not require Git. The downstream
managed Git promotion does not reselect the seed.
These role labels do not assert the tool's brand. The current QEMU and
maintainer-tree Make consumers still validate GNU Make where their source
contracts require it; changing the label does not pretend an unverified
non-GNU implementation will build those trees. Validated AWK and sed seeds are
available before Python and Automake; AWK also precedes the shell menu and
parent source-refresh steps. The seed Git boundary materializes
the pinned zlib source and Git fork. Bootstrap zlib uses the **seed** GNU
Make and ``CC_FOR_BUILD``, so it does not need to wait for the heavier
Automake/Autoconf/managed Make chain. If host zlib is insufficient or the
WHP fork is forced, its isolated ``deps/git-zlib`` prefix is later used
by managed Git. Git's ``ZLIB_PATH`` thus remains independent of both
the managed Git being built and the subsequent QEMU artifact zlib.

Ninja command handoff validation: an explicitly supplied ``NINJA_CMD``
must identify an executable that responds to ``--version`` before it is
passed to CMake, Meson or the native LLVM bootstrap. Explicit
``NINJA_CMD`` conflicts with ``BOOTSTRAP_NINJA=1`` rather than silently
bypassing the forced pinned fork. In automatic mode, an unusable discovered
host Ninja is rejected before deciding whether to attempt the pinned
fallback; the final selected helper is checked again before export.
``scripts/tests/test-ninja-bootstrap-call-contract.py`` exercises the
POSIX resolver independently of the expensive toolchain bootstrap.

Versioned Autotools handoffs distinguish two separate requirements:
``automake`` and ``aclocal`` must be from the same GNU Automake release,
and ``autoconf`` and ``autom4te`` must be from the same GNU Autoconf
release. GNU branding and successful ``--version`` calls alone do not
establish a coherent pair. The POSIX host-tool resolver now parses matching
numeric release strings and rejects a mixed pair before exporting tools to
downstream dependencies; explicit mismatches fail without fallback. A
**minimum** supported version is still determined by each downstream source
(e.g. the pinned GNU Make bootstrap requirements described below), rather
than guessed globally from the selected host tools. The focused
``scripts/tests/test-autotools-version-pairs.py`` fixture covers matching
and conflicting versions and malformed commands.

Managed Autoconf remains after Automake, managed Make after that pair, and
managed sed after Make. Ninja is prepared after Git selection but before
the larger Bash bootstrap: Ninja needs native C++17 and Python rather
than Bash or the Autotools source-generation chain. The explicit optional
sccache bootstrap runs at the Git-ready boundary *within* host-tool
preparation: seed/managed Git, bootstrap zlib, Automake/Autoconf, Make and
sed are already selected, then initialized submodules are reconciled, and
sccache can be built before Ninja and Bash. Cargo's native C/C++ dependencies
use the previously validated ``CC_FOR_BUILD`` and ``CXX_FOR_BUILD`` seeds,
while Rust/Cargo are required only when sccache is explicitly enabled.
The sccache executable is available before native LLVM. This order makes
caching earlier Ninja/Bash compilation possible only if those independent
source builds explicitly opt in to using the cache; it does not imply they
are automatically wrapped.

**Compiler promotion:** when ``BOOTSTRAP_NATIVE_LLVM=1``, the native LLVM
bootstrap publishes QEMU's artifact ``CC``/``CXX`` and coherent LLVM
archive/binutils replacements.

**Artifact-library phase:** zlib, SDL, and JACK are linked into QEMU, so in an
LLVM build their QEMU-facing preparation is deliberately deferred until after
compiler promotion. Artifact zlib uses ``deps/zlib``, separate from the
pre-Git ``deps/git-zlib`` fallback. In a non-LLVM build the bootstrap zlib
archive may be reused because no compiler promotion occurred. Libtool stays
after compiler promotion because its configure/cache records archive and
binary-tool identities, and libisofs remains downstream of that Libtool
selection.

Bootstrap compiler boundary
---------------------------

Native LLVM CMake configuration cache integrity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The LLVM CMake/Ninja configuration marker now contains the pinned LLVM Git
revision and source checkout location, independently of the installed host
toolchain's cache identity. Changes to the gitlink reconfigure CMake in
place even if source timestamps do not trigger Ninja's regeneration rule.
The native bootstrap excludes inherited cross-target CMake toolchains,
alternate generators, project injection hooks and pkg-config cross sysroots.
CMake ``-U`` removes stale cross-target entries from an existing cache
without deleting the incremental Ninja build directory. The cache-reuse
guard also checks ``CMakeCache.txt`` for injected toolchains/sysroots
and the Ninja generator, so a matching text marker alone is insufficient.

The shared ``whp_native_sdkroot`` resolves the selected Apple SDK once
per native probe or actual compiler invocation, validates explicit SDKROOT
against the selected Xcode/CLT developer directory, and passes the same
``-isysroot`` to both real ``seeds/cc.sh`` and ``seeds/cxx.sh`` invocations.
This repairs the case where the probe succeeded with an SDK but a
subsequent absolute-path Clang invocation failed to locate libSystem.
Linux compiler arguments and execution paths are unchanged.

Native C compiler admission versus bootstrap cache reuse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``build.sh`` validates the native C seed once and exports the selected
absolute compiler as ``CC_FOR_BUILD``. Python bootstraps prefer that
resolved path over probing ``seeds/cc.sh`` again. Separate configure checks
remain necessary when an actual tool rebuild changes the flags/SDK used.
GNU Make already checks its installation marker before its configure-C
smoke; GNU sed now follows the same ordering. On a valid sed producer
marker and usable installed binary, the extra configure compile/link/run
probe is skipped. On a miss, it still runs *before* deleting installed or
staged files. No persistent cross-run compiler attestation or force-true
CMake compiler-workaround variable is introduced.

Native LLVM compiler-selection shortcut
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The native macOS C/C++ ABI probe now verifies each requested architecture's
actual arm64, arm64e or x86_64 predefines, macOS SDK platform and LP64 data
model. An ignored ``-arch arm64`` cannot pass simply because Rosetta runs
an x86_64 executable. Compile/link and execution failures retain their
individual diagnostics, selected compiler, SDK and deployment target. The
arm64e authenticated indirect-call checks remain mandatory.

``scripts/bootstrap-native-clang.bash`` reuses ``CC_FOR_BUILD`` and
``CXX_FOR_BUILD`` when they are available from the public build entry.
Explicit ``NATIVE_LLVM_BOOTSTRAP_CC`` and ``NATIVE_LLVM_BOOTSTRAP_CXX``
take precedence and are validated directly with their native seed adapters;
the unused default candidates are not probed first. A standalone LLVM build
without either seed still uses the adapters. Only the duplicate arm64e
C/C++ ABI compile/link/run is skipped after both languages have succeeded
earlier in that same shell invocation. Neither LP64 checks, target-triple
consistency, C++ standard selection, the CMake compiler tests, nor installed
LLVM runtime checks are bypassed. No persistent compiler-success token is
introduced.

The ``seeds/cc.sh`` and ``seeds/cxx.sh`` native admission probes now compile
against C/C++ standard and POSIX ``unistd.h`` headers, link a libc
``access()`` call, and execute it. An empty ``main()`` alone could
accept a compiler with a missing macOS SDK. Probe subprocesses isolate
target include/library variables and injected loader search paths;
normal compiler invocations still receive all caller arguments and flags.
Relative explicit compiler seed paths are made absolute before promotion.

``seeds/cc.sh`` and ``seeds/cxx.sh`` are separate C and C++17 seed entry points.
They share the native compile/link/run probe, but each selects only its own
language driver. C++ selection first tries the driver paired with the native
C seed. Both adapters reject self-references and cross-adapter recursion;
``seeds/cc.sh --print-cxx`` is retired in favor of ``seeds/cxx.sh --print-cxx``.

The build-machine roles are ``CC_FOR_BUILD`` and ``CXX_FOR_BUILD``.
Target ``CC``/``CXX`` are deliberately excluded from seed discovery so a
cross compiler cannot leak backward into Python, GNU sed, Git, Bash, SDL,
Ninja, JACK, or the native LLVM bootstrap. Explicit seed overrides use
``WHP_CC_SEED`` and ``WHP_CXX_SEED``. When a selected compiler fails
its version, compile/link, or native execution probe, the adapters now show
the actual stderr/stdout from that failed stage, its exit status, and the
driver name. Failed optional PATH candidates remain quiet, and successful
seed selection emits only the path on stdout. Each native probe uses a
private ``mktemp`` directory so interrupted/incremental builds do not
collide with an earlier probe process.

macOS developer selection
-------------------------

Full Xcode (usually ``Xcode.app/Contents/Developer``) and standalone Apple
Command Line Tools (``/Library/Developer/CommandLineTools``) have separate
compiler/SDK roots. An explicit ``DEVELOPER_DIR`` overrides ``xcode-select -p``.
The ``xcrun --sdk macosx`` tools and default SDK must belong to the selected
root. Explicit ``WHP_*_SEED`` and ``*_FOR_BUILD`` compiler overrides retain
precedence, but automatic Apple discovery does not silently fall through to
unrelated ``PATH`` compilers when a developer installation is broken.
An explicitly supplied ``SDKROOT`` may select an older MacOSX SDK inside
that same developer root, never a different Xcode/CLT installation. Both
standalone LLVM bootstrap and QEMU's macOS wrapper validate that boundary.
No global ``xcode-select --switch`` or developer installation is changed.

Bootstrap linker boundary
-------------------------

``seeds/ld.sh`` is a POSIX native-linker seed adapter paired with ``seeds/cc.sh``.
``./seeds/ld.sh --print-ld`` (alias ``--print-seed``) resolves a linker that
can consume the selected native compiler's relocatable object; ``--check``
runs the same capability probe. Normal invocations pass arguments unchanged to
the resolved executable. Explicit seed overrides are ``WHP_LD_SEED`` and
``LD_FOR_BUILD``; broken overrides fail rather than silently selecting a
different ABI. Selection rejects recursion into the adapter itself.

``build.sh`` exports ``LD_FOR_BUILD`` before bootstrapping Python and LLVM,
but never replaces QEMU artifact ``LD`` with this script. Darwin selects the
Apple developer linker through ``xcrun`` at the seed boundary, not automatic
``ld64.lld``. Broken Xcode/CLT linker discovery now fails closed instead of
falling back to ``/usr/bin/ld`` or an unrelated PATH linker. The default
native ``ar``, ``ranlib``, ``nm``, ``strip``, and ``lipo`` drivers
are also resolved with ``xcrun`` when not explicitly set, allowing exact
Apple-provided ``/usr/bin/<tool>`` shims for system utilities; final host links still use the Clang driver's selected linker,
and ASan, ARM64e, optional mold, and firmware cross-linker policies retain
their separate probes. The relocatable probe is not evidence that an executable
link, LTO, sanitizers, or a particular target ABI succeeds.

Git bootstrap boundary
----------------------

Git's native Make invocation now validates the same macOS SDK used
by the seed Clang. The selected Xcode/CLT SDK is checked before compiler
selection and exported as ``SDKROOT`` into the sanitized Git build,
which probes ``<unistd.h>`` compilation, linking, and execution.
The SDK and deployment target participate in the Git cache marker;
a changed SDK cannot silently reuse an incompatible Git executable.

The WHP owns the pinned ``toolchains/git`` fork, but Git cannot be the first
Git executable in the graph. An already usable seed Git is required to obtain
the QEMU checkout, refresh ``master``, read the QEMU gitlink, and materialize
``toolchains/git`` plus its pinned ``sha1collisiondetection`` gitlink.

The bundled Python fallback also reads its gitlink and reconciles its source
through this validated seed. When the public updater already selected
``WHP_GIT_SEED``, Python reuses it; standalone Python bootstraps discover
Git with ``seeds/git.sh``. Neither path assumes that bare ``git`` on
``PATH`` is the selected implementation. Git invocation failures are fatal
rather than being misreported as missing gitlinks.

After that seed boundary, the bootstrap-zlib phase materializes the pinned
``toolchains/zlib`` gitlink with the seed Git. When a managed fallback is
needed, it is built under ``deps/git-zlib`` with ``CC_FOR_BUILD`` and
published only as ``WHP_GIT_ZLIB_PREFIX``. ``scripts/ensure-git.py`` passes
that prefix through Git's supported ``ZLIB_PATH`` Make variable and records
the zlib bootstrap marker hash in Git's cache identity. This breaks the
apparent ``Git -> zlib -> Git`` cycle without leaking the build-machine zlib
into QEMU's later artifact-library phase.

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

QEMU's early parent source fast-forward runs before host-tool promotion, so it
uses a host Git seed. After host-tool selection, a full HTTPS-capable managed
Git sets ``GIT`` and prefixes its ``bin`` directory to ``PATH``. If no managed
Git is promoted and the caller has not supplied ``GIT``, the bootstrap exports
the verified ``WHP_GIT_SEED`` explicitly instead of relying on a possibly
different ``PATH`` lookup. A caller-supplied Git override remains intentional.
``scripts/ensure-dtc-subproject.py`` uses that selected ``GIT`` for its
pinned-commit reconciliation. Its read-only ``--diagnose`` output identifies
the selected executable, version and HTTPS helper; if the pinned object probe
fails, it independently checks the same local object with the seed Git when
available. A failed selected-Git probe alone must not be interpreted as proof
that the pinned commit is absent: the Git executable itself may have failed.
Neither diagnostic changes the checkout, wrap marker, or build directory.

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

The QEMU ``seeds/automake.sh`` adapter resolves a validated native
GNU Automake/aclocal pair before downstream maintainer-source generation.
It prefers an ``aclocal`` beside the selected ``automake``, honors
explicit ``WHP_AUTOMAKE_SEED`` and ``WHP_ACLOCAL_SEED`` choices, and rejects
mixed or malformed version banners. ``--print-seed`` and
``--print-aclocal`` expose the two resolved executables; ordinary arguments
delegate to Automake and ``--aclocal`` delegates to aclocal. Host discovery
and the managed Autoconf bootstrap consume this bridge rather than selecting
two unrelated executables from PATH. No new source dependency is introduced:
a seed selects already installed tools and does not build Automake itself.
The paired seed is not a substitute for the separate **seed Autoconf**
needed to generate the managed Automake source. The offline
``scripts/tests/test-automake-seed.py`` checks release pairing, overrides,
recursion and argument forwarding.

The separate ``seeds/autom4te.sh`` adapter admits an existing GNU
Autoconf/``autom4te`` **pair** and supports direct consumers of the
``autom4te`` executable. ``--print-seed`` returns the selected
``autom4te``; ``--print-autoconf`` returns the paired ``autoconf``;
``--check`` reports both; ordinary arguments execute ``autom4te``,
while ``--autoconf`` delegates to ``autoconf``. Explicit
``WHP_AUTOM4TE_SEED`` and ``WHP_AUTOCONF_SEED`` take precedence,
and contradictory pair versions fail instead of falling back to PATH.
For an implicitly selected pair, the companion executable next to the
selected tool is preferred. The host bootstrap and managed Automake
source stage use the seed for a coherent versioned handoff, without
creating a new dependency or attempting to generate the missing tool.

The adapter does not break the Autotools source-level cycle by itself:
the initial ``autoconf`` and ``autom4te`` must be installed and
independent of the pending managed Autoconf output. The cycle guard
checks both selected paths. The offline
``scripts/tests/test-autom4te-seed.py`` and
``scripts/tests/test-automake-seed-cycle.py`` exercise this boundary.

Managed Autoconf must not be fed back into the same Automake bootstrap that
produces the Automake instance it consumes. The seed Autoconf dependency is
therefore narrowed to the first Automake stage. This is a genuine source-stage
cycle broken by an existing, independent Autoconf/autom4te installation, not
a recursive build in the correctly ordered QEMU host graph. The managed
Automake bootstrap now rejects a seed path inside the current build's
``deps/autoconf`` output and gives an explicit diagnostic when the seed is
missing. The ``test-automake-seed-cycle.py`` regression covers independent
seeds, missing seeds, and attempts to feed managed output back upstream.

The pinned Automake source ``bootstrap`` invokes ``$AUTOCONF -Wall -Werror``
after creating temporary Perl-based Automake and aclocal helpers, and its
``configure.ac`` also checks that Autoconf works. The pinned Autoconf source
``bootstrap`` invokes ``$ACLOCAL`` and ``$AUTOMAKE``. Merely moving the
bootstrap ordering or claiming self-hosting removes these commands would
reintroduce the cycle. A completely seedless host is therefore not supported
by these two Git maintainer-source bootstraps without a separately validated
source-generation strategy; the guard prevents a misleading fallback but
does not eliminate the minimum external seed.

``scripts/ensure-autoconf.py`` uses a tool-only install profile: executables,
Autom4te/Autoconf/M4sugar/Autotest data, autoscan data, and auxiliary config
scripts are installed without Info or manual generation. Help2man and Texinfo
remain upstream developer/release tools, not requirements of the QEMU profile.

The native ``seeds/perl.sh`` bridge selects an existing Perl before the
managed Automake and Autoconf source-generation stages. It accepts
``WHP_PERL_SEED`` or ``PERL`` as an authoritative one-executable override,
then discovers ``perl`` on PATH or the conventional ``/usr/bin/perl``.
Admission executes a small ``-e`` program with ``use 5.006``,
``strict``, and ``warnings`` rather than trusting a successful
``--version`` or an executable bit alone. This corresponds to the pinned
Automake source's Perl 5.6 minimum and requires no additional Perl package
or cross-target interpreter. ``--print-seed`` returns the actual selected
binary, ``--check`` reports it, and regular invocation delegates arguments
unchanged. ``scripts/tests/test-perl-seed.py`` covers missing, bad, recursive
and explicit seeds. Only consumers needing Perl request the seed; QEMU itself
does not impose Perl as a new global prerequisite.

The direct roots for this managed stage are Automake/aclocal, GNU M4, Perl,
seed GNU Make, a primitive shell, ``mktemp``, and the validated
sed seed. The pinned Autoconf source bootstrap invokes ``mktemp`` for a
temporary tool directory, but not a standalone ``realpath`` command.
The Python bootstrap already resolves its source/build paths with
``pathlib``, so requiring a separate ``realpath`` program would add an
unnecessary portability gate (particularly on older macOS hosts).
An explicit ``M4`` remains authoritative. On Darwin, otherwise,
the standard Homebrew M4 keg locations are checked before PATH so Apple's
compatibility M4 cannot silently outrank an installed GNU M4. Admission now
requires GNU M4 1.4.16 or newer with working ``--gnu`` support, matching the
maintainer bootstrap's exclusion of the historical strstr-bug releases.
Admission also executes GNU ``patsubst`` under ``--gnu --fatal-warnings`` and checks
its exact output. A plausible version banner alone cannot admit a broken or
non-expanding executable. This is a compatibility floor, not a pin to an older
M4 release; newer GNU M4 installations remain eligible.

The selected executable is mirrored as the bootstrap's literal ``m4``
command so Autotools subprocesses cannot rediscover a different
implementation. The completed Autoconf marker records ``M4_PATH`` and
``M4_VERSION`` separately. ``host-tools.sh`` validates that path again and
exports it as the canonical ``M4`` for later maintainer-source orchestration,
including sed, Libtool, and libisofs. The promotion path repeats the GNU macro
execution check so a binary replaced after initial bootstrap cannot silently
be used downstream. GNU Make receives the managed Autoconf
suite generated with that M4, but its helper deliberately strips inherited
``M4`` from Make's own artifact configure environment as part of its target
contamination guard. The installed-runtime smoke test removes caller ``M4``
first, so an ambient Homebrew tool cannot hide a broken M4 path embedded in
``autom4te``.

awk seed bridge
---------------

The first AWK is a validated host seed, not a recursively compiled managed
AWK. ``seeds/awk.sh`` accepts an explicit ``WHP_AWK_SEED`` or ``AWK`` and rejects
unusable overrides rather than silently falling back. It verifies the POSIX
subset used by QEMU's bootstrap: ``-F`` and ``-v``, field and record counters,
regular expressions, substitutions, and array splitting. Both the adapter and
the literal ``scripts/whp-build/seed-bin/awk`` launcher reject recursion.

``build.sh`` resolves AWK **before** the parent source refresh and portable
shell ``menuconfig`` entry. It exports the exact native executable through
``AWK`` and ``WHP_AWK_SEED``, prepends the canonical literal launcher to
``PATH``, and locks the selection via ``WHP_AWK_LOCKED=1``. Later CMake,
OpenBIOS, LLVM, and post-build scripts using a literal ``awk`` therefore
consume the same seed without repeated capability probes. No host AWK binary
is overwritten, and no new AWK source pin or compiler dependency is created.

grep seed bridge
----------------

The first grep used by QEMU is a host-side root capability rather than a
self-built GNU grep fork. ``seeds/grep.sh`` probes literal, extended and fixed-string
matching, quiet and inverted matching, and patterns beginning with a hyphen.
It rejects an unusable explicit ``GREP`` or ``WHP_GREP_SEED`` and rejects
selection of its own bridge as the seed.

``build.sh`` resolves ``WHP_GREP_SEED`` before the sed/Python/Autotools
bootstrap stages, publishes ``GREP`` as the exact selected executable, and
prepends the single-purpose ``scripts/whp-build/seed-bin`` directory to
``PATH``. Its ``grep`` launcher forwards every argument and exit code to
that same validated executable. The locked fast path avoids re-probing every
literal grep invocation. The wrapper is in the tracked source tree, so no
temporary PATH shim, new grep submodule or recursive grep bootstrap is needed.

Native bootstrap variable and cache integrity
---------------------------------------------

The early Automake, Autoconf and Git builders sanitize their child native
tool environments through ``scripts/bootstrap_env.py``. Poisoned target
``CC``, flags, Make overrides, Autoconf cache answers, pkg-config sysroots,
macro search paths and injected runtime-library variables cannot silently
reach their source configure or Make invocations. Selected tools are restored
explicitly, including the compiler verified by ``seeds/cc.sh``, the GNU Make
seed, configuration shell, GNU M4, Perl and Autotools.

Automake and Autoconf cache markers now include native CC/version,
configuration shell, selected SDK and deployment target. Both early
generators now validate the selected Xcode/CLT SDK before resolving the
native compiler and export the same ``SDKROOT`` to configure. This avoids
the split between a successful seed CC probe and a native configure that
cannot find ``unistd.h`` or other SDK headers. Git's cache
schema changes with its corrected environment contract. GNU Make rejects
malformed or nonexistent inherited ``ACLOCAL_PATH`` entries before using
them in generation and cache markers; valid absolute macro paths survive.
Only affected producer caches become stale. No global cache purge is needed.

Optional toolchain bootstrap requirements
-----------------------------------------

Libtool, sccache, Automake and mold are not common build-machine roots:

* **Automake/aclocal:** In ``BOOTSTRAP_AUTOMAKE=auto``, use a working host
  pair even on macOS. Only an absent/unusable pair, or explicit
  ``BOOTSTRAP_AUTOMAKE=1``, activates the pinned source bootstrap. Its Perl,
  Autoconf/autom4te, GNU Make and sed inputs are requirements of that
  *generation* lane, not of a usable host Automake installation.
* **Libtool/libtoolize:** A working system pair avoids the managed fallback.
  Building the maintainer-source fork requires GNU Make, the Autotools suite,
  GNU M4, Help2man, Texinfo, xz and the pinned nested source graph. Current
  ``ensure-libtool.py`` resolves source and tool identities before evaluating
  its marker; those identities are inputs to cache correctness, not evidence
  that every QEMU build requires the Libtool maintainer tools.
* **sccache/sccacher:** Placed after final Git promotion, bootstrap-zlib
  preparation and initialized submodule reconciliation, but before native
  Ninja/Bash source builds and native LLVM. QEMU artifact zlib, SDL, and JACK
  remain compiler-selected, later libraries, not inputs to the sccache seed.
  Opt-in compiler caching is separate from C/C++,
  Meson and Ninja correctness. The pinned local-only build needs the selected
  Git, Cargo and Rust >= 1.91 when requested. Its cache marker includes the
  Rust/Cargo identities and source revision; removing these checks without an
  equivalent identity would risk reusing a mismatched binary. A disabled
  sccache lane must not force Cargo or Rust into the core build.
* **mold:** Automatic selection does not build mold just because the source
  submodule exists. An already installed, marker-matching mold linker can be
  reused without CMake; CMake is checked after the cache miss. Compiler/link
  validation still runs before the linker is adopted. Explicit mold requests
  fail on incompatible ABI/linker flags rather than silently substituting it,
  especially for Darwin ARM64e authenticated fixups.

``BOOTSTRAP_AUTOMAKE=1`` and ``BOOTSTRAP_AUTOCONF=1`` remain forced modes;
``auto`` is a capability-first selection, not a request to rebuild solely
because the host is macOS. Retain real source/ABI and cache identity guards.

Bootstrap force-mode failure contract
-------------------------------------

Automake and Autoconf are promoted in dependency order. In ordinary
``BOOTSTRAP_AUTOMAKE=1`` or ``BOOTSTRAP_AUTOCONF=1`` mode, failure to
produce the pinned tool is fatal even if a usable system version exists.
Only ``auto`` can fall back to the host toolchain. Shell-only and portable
probe modes intentionally skip expensive bootstraps; they retain host
discovery without claiming a pinned tool was built.

Bootstrap memory-corruption validation
--------------------------------------

The normal bootstrap compilers and their cache markers remain free of
experimental sanitizer flags. The GNU sed Linux bootstrap CI instead
reconfigures the exact pinned/generated sed source in a distinct
``whp-sed-sanitized`` object directory using a native C compiler with
AddressSanitizer and UndefinedBehaviorSanitizer. It executes deterministic
basic, capture/backreference, binary-NUL and large-record cases, failing
on sanitizer diagnostics or abnormal exit. Leak detection is enabled for
the runtime smoke, but disabled only during Autoconf feature probes.
The macOS ARM64e sanitizer runtime has its own explicit
``asan-arm64e-runtime.yml`` validation; CI does not silently impose
Linux sanitizer flags on Apple bootstrap executables. A clean smoke
does not prove the absence of all memory-safety defects.

sed/Automake bootstrap boundary
-------------------------------

GNU sed has two different roles in the WHP bootstrap and they must not be
flattened into one executable slot.

**Seed sed** is a root capability. ``seeds/sed.sh`` validates the small semantic
subset needed by the bootstrap and rejects recursion back into itself. The
public ``build.sh`` resolves this seed once as ``WHP_SED_SEED`` before the
Python fallback or Automake bootstrap. Python, Automake, and GNU sed's own
self-bootstrap therefore consume one provenance identity rather than
independently rediscovering host sed implementations. The promoted
``SED`` is a distinct downstream tool; host-tools must not unset
``WHP_SED_SEED`` after the managed sed builder runs.

**Managed GNU sed** remains downstream of Automake and managed Autoconf. The pinned sed fork is a
maintainer-source checkout whose bootstrap explicitly requires Automake and
Autoconf; its gnulib path also requires M4. The sed fork's ``bootstrap.conf``
declares gettext, makeinfo, and Perl as build prerequisites. In the current
WHP invocation, ``--skip-po`` avoids PO refresh/download work but does not
remove those prerequisite checks, and the gettext path can still run
``autopoint`` because ``configure.ac`` uses GNU gettext macros.
The selected ``AUTOPOINT`` is pinned in the sed bootstrap marker.
On Homebrew, its executable need not share a prefix with an installed
``share/aclocal/gettext.m4``; that external file is optional.
The real invariant is that autopoint stages ``m4/gettext.m4`` into
the isolated sed source, verified immediately after bootstrap and before
configure. The system macro search path is included only when it exists,
so a relocated gettext installation cannot cause a false prerequisite
failure or an empty ``ACLOCAL_PATH`` element.

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
generated ``configure``/``Makefile.in``/gnulib build inputs.

Those stages have different dependency boundaries. Make's
``bootstrap --gen`` path consumes gnulib, Autoconf/Automake, autopoint, and
the validated sed/configuration-shell environment, but its bootstrap scripts
do not execute GNU Make. The generated ``configure``, however, contains
Automake checks which execute ``${MAKE-make}``: for example
``AM_MAKE_INCLUDE`` probes include behavior and Automake's sanity machinery
can probe Make timestamp behavior. The seed Make is therefore a real
**configure-time** input even though ``build.sh`` itself is the no-Make
compile/link path.

The first GNU Make consequently remains an explicit seed rather than being
silently replaced. Python's POSIX fallback and the managed Automake stage also
consume that seed upstream. Managed Autoconf is produced after Automake and is
then used to generate GNU Make's configure machinery.

After those prerequisites are available, ``BOOTSTRAP_MAKE=auto`` prefers the
pinned fork on macOS, ``BOOTSTRAP_MAKE=1`` forces it, and
``BOOTSTRAP_MAKE=0`` retains the seed. ``scripts/ensure-make.py`` stages the
exact QEMU gitlink and replaces GNU Make's moving ``stable-202507`` gnulib
branch reference with the audited commit
``b22f5a3037712a3c957a03071ce0b219cef4d65b``.

The final Make output marker intentionally includes configure/build inputs
such as the seed Make, compiler, configuration shell, pkg-config identity,
Autotools identities, and the fixed configure profile. A change in those
inputs can legitimately require ``configure`` and ``build.sh`` to run again
even when the Make gitlink did not change. That rebuild must not imply another
gnulib download or another Autoconf regeneration. Because the Make
source uses ``AM_GNU_GETTEXT``, its generated-source cache must also
contain ``m4/gettext.m4`` staged by autopoint. A cache missing that
macro is rejected and regenerated; merely having ``configure`` or a
matching marker is insufficient.

The helper therefore separates two reusable producer layers. Gnulib is stored
under ``BUILD_DIR/cache/gnulib/<commit>``, with its exact Git HEAD and clean
tracked state verified. Autoconf/Automake-generated Make source is stored
separately under ``BUILD_DIR/cache/make-generated`` and is keyed by the Make
revision, pinned gnulib commit, declared Autotools floors, actual generator
tool identities, autopoint, seed sed, ``ACLOCAL_PATH``, host system, and
configuration shell. Its generation runs with ``--gen --no-git`` and with
the seed Make, compiler, and pkg-config removed from the generation
environment. Consequently a compiler or seed-Make change can rerun
``configure + build.sh`` while reusing both gnulib and the already-generated
Autoconf source. Network access is needed only when the immutable gnulib cache
is absent or invalid.

When the generated-source cache itself is stale, the maintainer generation
stage regenerates the Autoconf inputs from the pinned source. The required
Automake and Autoconf versions are read from that Make revision's own
``bootstrap.conf``; the helper does not maintain a second hard-coded version
floor. Automake/aclocal must identify as one GNU Automake version at or above
that floor. Likewise, ``autoconf``, ``autom4te``, ``autoheader``, and
``autoreconf`` must agree on one GNU Autoconf version at or above Make's
declared requirement.

The selected configuration shell is exported through both ``CONFIG_SHELL``
and ``SHELL`` and participates in the Make bootstrap marker. Make's bootstrap
library also contains literal ``sed`` calls, so the validated seed sed is
mirrored as ``bootstrap/make/seed-bin/sed`` and that private directory leads
``PATH``. The ``SED`` variable and literal command lookup therefore resolve
to the same implementation.

GNU Make's Git documentation warns that ordinary Git-tree VPATH builds are not
supported. That warning does not mean this WHP path should ignore the
build-directory interface intentionally provided for the no-Make bootstrap:
``configure.ac`` uses ``AC_CONFIG_LINKS([build.sh:build.sh])`` specifically to
place ``build.sh`` in the configured build directory. WHP therefore runs
``configure`` out-of-tree, verifies ``build.cfg``, ``config.status``,
``Makefile``, ``lib/Makefile``, ``src/config.h``, and the configured
``build.sh``, then executes that configured ``build.sh``. It does not bypass
``config.status`` by reaching back to the source copy.

Because this is a build-host tool, inherited target compiler/linker flags,
archive tools, pkg-config search roots, ``CONFIG_SITE``, M4 overrides, and
Autoconf cache variables are removed before configure runs. The fixed WHP
configure profile disables dependency tracking, NLS, and Guile. The resulting
binary is promoted through ``MAKE_CMD``, ``MAKE``, and ``PATH`` for GNU sed,
Git, Bash, Libtool, libisofs, firmware, and the later QEMU build graph. This
keeps the ``Make -> Make`` edge visible as a seed boundary instead of
pretending it does not exist.

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
     - managed after seed
     - The seed GNU Make bootstraps the early Python/Autotools boundary. Once
       Automake and Autoconf exist, the pinned WHP Make is promoted through
       ``MAKE_CMD`` and ``MAKE``; libisofs therefore consumes the managed
       executable when that promotion succeeds.
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
     - managed/root library
     - libisofs links the artifact zlib selected before this stage and exports
       ``-lz`` to static consumers. When WHP stages a private zlib,
       ``WHP_ZLIB_PREFIX`` supplies its exact headers/archive; otherwise the
       usable host zlib remains authoritative. This edge exists before QEMU's
       later Meson dependency resolution.
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

Bootstrap command failures are stage-labelled and retain the exact command,
working directory, exit status, and the final bounded output tail while still
streaming build output live. Post-install consumer validation keeps
pkg-config-version, compile/link, and executable-runtime failures distinct
instead of collapsing them into one boolean message. The consumer probe source
is written to its temporary ``probe.c`` before Clang is invoked; this is part
of the tested bootstrap contract so a missing probe input cannot be hidden by a
generic validation failure.

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
Automake's generated ``install-libLTLIBRARIES`` for the archive and the stable
``install-data`` aggregate for the public header plus generated pkg-config
metadata. The fork's macOS CI uses the same contract; the old
``install-pkgconfigDATA`` leaf was invalid because
``nodist_pkgconfig_DATA`` generates a differently named leaf target.

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
The private libisofs build owns its compiler/linker flag boundary. QEMU global
``CFLAGS``, ``CPPFLAGS``, ``CXXFLAGS``, Objective-C flags, ``LDFLAGS``,
``LIBS``, ``CPP``, and ``LD`` are removed before configure. Ambient search
roots such as ``CPATH``, ``LIBRARY_PATH``, Darwin ``DYLD_*`` paths, and
pkg-config search/sysroot variables are isolated as well. This prevents a
Homebrew or caller dependency from re-entering the build after the explicit
flags were cleared, and prevents QEMU-only linker policy such as
``-fuse-ld=lld`` or ``--read-workers`` from being appended to libisofs.

The helper reconstructs only its GNU C11/strict-prototype policy and the
resolved Darwin ABI triplet in ``CFLAGS``. Caller ``CPPFLAGS`` are still erased,
but macOS receives one dependency-owned input define,
``-D_DARWIN_C_SOURCE=1``, so Darwin system extensions are explicit on every
libisofs compile path. Autoconf probe results such as
``LIBISOFS_DARWIN_ABI64``, ``LIBISOFS_ARM64E_ABI``, large-file defines, and
``HAVE_*`` remain configure-owned and are not predeclared by the wrapper.
``LDFLAGS`` remains empty unless a managed dependency such as
``WHP_ZLIB_PREFIX`` contributes only its private library search path; compiler-driver
links consume the Darwin ABI triplet once through ``CFLAGS``. LLVM
``AR``/``RANLIB``/``NM``/``STRIP`` and ``LIPO``
remain intentional tool selections, but QEMU's exported ``LD=ld64.lld`` does
not: Clang chooses the platform linker for libisofs Darwin/arm64e configure
and link probes.

When the managed zlib bootstrap publishes ``WHP_ZLIB_PREFIX``, the private
libisofs configure receives that exact prefix through dependency-owned
``CPPFLAGS``/``LDFLAGS`` search paths. The post-install smoke test then
replaces inherited pkg-config search state with the private libisofs directory
and uses the explicit zlib library path. This keeps validation on the exact
artifact pair rather than rediscovering a Homebrew/SDK copy.

The fork's iconv probe is also kept out of global link state after configure
validates it. On Darwin the required ``-liconv`` remains represented once by
``ICONV_LIBS``/the static pkg-config metadata instead of appearing both in
global ``LIBS`` and the library's explicit dependency list.

The private install step deliberately avoids Automake's generated leaf target
names. In particular, ``nodist_pkgconfig_DATA`` generates
``install-nodist_pkgconfigDATA``, not ``install-pkgconfigDATA``. QEMU therefore
installs the static library with ``install-libLTLIBRARIES`` and delegates headers
and generated pkg-config metadata to Automake's stable ``install-data``
aggregate. The exact install target set is part of the workspace identity so
incremental reuse cannot hide a future install-contract change.

QEMU configures the fork with ``--disable-debug``. The fork now respects an
explicit caller ``CFLAGS`` and no longer prepends its historical debug/warning
or optimization bundle on top of orchestrator-owned flags; only the
``DEBUG``/``NDEBUG`` semantic define follows the selected debug mode.
This empty-``LDFLAGS`` policy is tied to the pinned Automake C link template,
which expands ``$(CCLD) $(AM_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) $(LDFLAGS)``.
Thus the Darwin ABI triplet in ``CFLAGS`` reaches Libtool's compiler-driver
link exactly once. If that Automake template changes, the libisofs static test
must fail before the policy is reconsidered.

The global ``-Werror=strict-prototypes`` check remains intentional. The pinned
WHP Autoconf emits ``char func(void)`` declarations for both ``AC_CHECK_LIB``
and ``AC_CHECK_FUNC`` probe paths, so strict-prototype warnings do not turn
valid zlib/iconv/function checks into false negatives.





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

The native LLVM distribution includes ``llvm-rc`` and ``llvm-windres``
for Windows resource scripts such as QEMU's ``version.rc``.  It does not
require ``llvm-mt`` to build those resources.  ``llvm-mt`` merges Windows
application XML manifests; it does not manage WHP build manifests or Mach-O
metadata. A downstream PE/COFF CMake consumer may opt in with
``NATIVE_LLVM_WINDOWS_MANIFEST=1`` when a compatible native libxml2 is
available. That flag selects ``LLVM_ENABLE_LIBXML2=FORCE_ON`` and installs
``llvm-mt`` only after checking an actual XML merge. Missing libxml2 is an
explicit configure failure rather than an unusable manifest-tool executable.
The default is off, preserving lean ARM64/ARM64e/macOS and other host builds.
A consumer must select its manifest tool explicitly when necessary; simply
installing ``llvm-mt`` does not add a QEMU manifest link step.

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

Berkeley SoftFloat/TestFloat use ``patch_directory`` to supply their
``meson.build`` and ``meson_options.txt`` from the tracked QEMU
``subprojects/packagefiles/`` trees. The upstream Git checkouts do not
necessarily contain these Meson files. An older interrupted fetch or an
external checkout can leave the source directory present but unpatched.
The pinned WHP Meson wrap resolver now restores *only absent* package files
when the existing checkout lacks its build file, including in offline
``wrap_mode=nodownload`` builds. It preflights all existing patch-file
collisions, refuses conflicting files and unsafe patch paths, and does not
reset, fetch, change branches, or recreate the source directory.
An existing ``meson.build`` continues to use Meson's original validation
path; files already present are never silently replaced by this recovery.
The fork's ``unittests.wraptests`` guard successful restoration, conflict
preservation, and subsequent no-op resolution.

The DTC wrap in ``subprojects/dtc.wrap`` resolves the internal libfdt
fallback from the WHP-owned ``retrochristian5000/dtc`` fork at an immutable
commit.  This is a Meson-owned subproject, not a second vendored copy or a
new top-level git submodule.  The top-level gitlink updater rejects
``subprojects/*`` paths before updating any gitlink, while DTC's own
reconciliation helper honors the selected ``GIT`` command from the WHP
host-tool bootstrap.  Git implementation changes therefore must not silently
split the DTC fetch path from the other pinned dependency fetches.
On a clean, detached, stale DTC checkout the helper fetches the exact wrap
revision directly from the wrap URL without relying on or changing the
checkout's ``origin`` remote.  A custom remote or a missing ``origin``
therefore cannot block a verified pinned Git fetch.  Local source edits and
attached stale branches are still protected.  The helper's ``--diagnose``
mode reports the Git boundary without fetching or modifying sources.

In ``menuconfig``, ``QEMU libfdt provider`` maps to Meson's existing
``fdt`` option (``auto``, ``system``, ``internal``, ``enabled``,
or ``disabled``).  The default is ``auto``, preserving native QEMU
dependency selection.  The separate ``Prefetch missing pinned DTC checkout``
switch maps to ``WHP_DTC_FETCH_MISSING=1`` and opts into the existing
pre-Meson ``--fetch-missing`` helper; by default DTC remains Meson-lazy.
With downloads disabled, prefetch cannot obtain an absent pinned commit.
Neither choice rewrites ``dtc.wrap``, switches a development branch, or
cleans the incremental build directory.

DTC wrap upgrade protocol
~~~~~~~~~~~~~~~~~~~~~~~~~

Meson first resolves an existing DTC directory containing ``meson.build``
without re-fetching the Git revision.  Its
``.meson-subproject-wrap-hash.txt`` stores a checksum of the UTF-8 wrap
text; a mismatch warns of changed metadata, but does not verify DTC HEAD.
The expected SHA-256 is derived from the live ``dtc.wrap`` text, not
an embedded digest or the DTC source files.
The DTC fork now ignores its generated ``.meson-subproject-wrap-hash.txt``
so Meson's metadata does not falsely mark DTC's own Git source as dirty
or alter Git-based ``vcs_tag`` results.  That change is pinned through
QEMU's immutable DTC wrap revision rather than by following a branch.  Reconciliation parses the
pinned Git revision and computes this digest from one UTF-8 snapshot,
rechecks the wrap before writing the marker, and refreshes a missing
marker.  A changed revision, URL, or fetch depth changes the computed
wrap checksum; a DTC source modification without a wrap change does not.
A concurrent wrap edit prevents a stale marker from being installed.
The digest is independent of ``CI``, ``PYTHONHASHSEED``,
``WHP_SOURCE_UPDATE``, ``WHP_MESON_PROVIDER`` and
``MESON_PACKAGE_CACHE_DIR``; these affect workflow execution or
source resolution, not the SHA-256 input. ``CI`` and
``WHP_SOURCE_UPDATE_DONE`` affect the parent QEMU source updater, not
the independent post-host DTC step. ``QEMU_FDT_MODE=system/disabled``
skips internal DTC; ``WHP_SOURCE_UPDATE=0`` also skips it unless
``WHP_DTC_FETCH_MISSING=1`` requests a prefetch. A missing DTC
checkout normally remains Meson-lazy. Read-only diagnosis now prints
the expected text checksum even before DTC has been fetched, and
reports DTC eligibility separately from the parent source updater.

The tracked QEMU ``configure`` must be executable (``100755``).
Without that Git file mode, direct ``../configure`` invocations
fail with permission denied *before* Meson can verify a DTC wrap.
Do not attribute that failure to SHA-256.  The early parent source updater
treats ``CI=0`` and ``CI=false`` as disabled CI flags rather than silently
skipping the parent refresh.  The read-only DTC diagnostics expose both
the hash input and relevant environment controls without rewriting the
stored marker.
The pinned WHP Meson fork also parses and SHA-256 hashes a single UTF-8
wrap snapshot, instead of reading the changing wrap file twice.  Its wrap
unit tests are invoked during QEMU's internal-DTC macOS workflow.  This
complements QEMU's pre-Meson reconciliation; Meson's generic existing-source
wrap validator does not replace the exact DTC Git-revision check.
The WHP reconciliation step must therefore check the pinned Git revision,
validate DTC's Meson interface and declared version, and only then refresh
that marker.  The present fork pin is DTC 1.8.1, whose Meson project reads
``VERSION.txt``; original DTC 1.6.0 is not compatible with QEMU's
``dtc:tests`` option.  A minimum DTC version of 1.8.1 is enforced in
the helper for both existing and proposed revisions.  Future versions
such as 1.9.0 may still pass when their Meson interface is compatible.
The DTC version is independent of the version of the Meson executable.
A post-Meson read-only verification of explicit ``-Dfdt=internal``
builds now confirms that the resolved DTC checkout's Git HEAD matches the
immutable wrap revision, DTC's Meson libfdt interface remains compatible,
the checkout has no nonignored source changes, the generated marker is
Git-ignored, and its SHA-256 equals the current UTF-8 wrap text digest.
``--verify`` returns a failure on a missing/stale marker, an unexpected
checkout, or source drift without refreshing the marker or moving HEAD.
The existing pre-Meson reconciliation remains responsible for any safe
repair; the post-Meson verification does not turn a diagnostic into a
source update. Parent Git release archives keep their vendored-source
configuration path, and system/disabled libfdt providers bypass this check.
The macOS workflow verifies both the default venv Meson and pinned WHP
Meson fork after configuration and again following incremental reconfigure.
The early QEMU source fast-forward updater handles only the parent Git
revision and submodule URL metadata. It must fail the launcher when
``WHP_SOURCE_UPDATE=1`` fails, rather than silently continuing with stale
QEMU source. After ``host-tools.sh`` selects WHP-managed or verified seed
Git, ``scripts/whp-build/update-submodules.py`` compares the pinned gitlinks
from QEMU's current ``HEAD`` with **already initialized** submodule working
trees and updates clean, detached, stale checkouts to the exact gitlink.
Locally available pinned commits require no fetch; missing pinned commits
may be fetched only for their initialized submodule. Every differing
checkout is preflighted for local modifications and attached branches
before any checkout is moved; failures stop the build instead of hiding
source drift. Never use ``git submodule update --remote`` or a hard reset
here. Uninitialized firmware/toolchains stay lazy, and Meson-owned wraps
remain outside the Git submodule updater. ``WHP_SOURCE_UPDATE=0`` skips
both automatic Git phases; automatic mode skips network refresh in CI.
The launcher reconciles an existing DTC
checkout **after** loading saved menuconfig settings and selecting the
requested Python and Git in ``host-tools.sh``, even when the incremental
QEMU build would otherwise skip ``configure``. This avoids invoking a seed
Git or incidental system Python before the requested host tools exist.
A parent Git refresh alone cannot change the Meson-owned DTC source or its
stored hash. The post-host-tools repair preserves local changes, attached
development branches, and build outputs. It leaves missing DTC checkouts lazy
unless ``WHP_DTC_FETCH_MISSING=1`` explicitly requests prefetch. When
``QEMU_FDT_MODE=system`` or ``disabled``, neither the launcher nor
``configure`` reconciles DTC, because those libfdt modes never enter
Meson's internal DTC subproject. The actual system library is still checked
by Meson; an absent or incompatible system libfdt remains a proper configure
error. For ``auto`` and ``enabled``, the internal fallback remains possible
and reconciliation is retained. Disabling source updates with
``WHP_SOURCE_UPDATE=0`` skips automatic post-host-tools repair, although
QEMU ``configure`` retains its required pre-Meson check when the libfdt
provider might be internal.
Use the mutating helper without ``--diagnose`` to perform an explicit
repair; ``--diagnose`` reports state only.

A further independent identity is the DTC commit tree, visible through
``git -C subprojects/dtc rev-parse HEAD^{tree}``.  Its hash identifies the
committed DTC source, unlike the SHA-256 wrap marker.  Even matching Git
HEAD and wrap marker cannot prove an unchanged local working tree: the
reconciliation helper now checks nonignored Git source changes on its
matching-pin fast path.  Ignored generated build files remain untouched.
The read-only ``--diagnose`` output shows HEAD, pinned revision,
their tree hashes (when available), local changes, DTC version and
Meson interface status, so source changes cannot hide behind metadata.

For a future fork revision, update only the immutable ``revision`` in
``subprojects/dtc.wrap`` after reviewing the new DTC source.  QEMU
currently passes DTC options ``tools``, ``yaml``, ``python``,
and ``tests``, and consumes ``libfdt_dep``.  The helper validates these
before checking out a *new* revision using read-only Git object access.
It understands both ``meson_options.txt`` and newer ``meson.options``.
Incompatible upgrades are rejected while preserving the old HEAD, marker,
and Meson build graph; they require an explicit coordinated QEMU change,
not a forced marker update.  New revisions can reuse already-fetched commits
offline and are not taken from a floating branch.

After reviewing a candidate, run the DTC reconciliation tests and both the
venv and pinned-fork Meson internal-DTC configure checks.  Retain the
incremental-reconfigure check and the libfdt Ninja/link validation.  An
upgrade is not complete merely because its wrap hash changed.  Never
``git stash``, reset DTC sources, or wipe an existing QEMU build just
to make a marker match.

QEMU continues to prefer usable system libfdt
when selected; the internal fallback builds only libfdt (without DTC tools,
Python bindings, or DTC's standalone tests).  Keep the wrap revision pinned;
do not replace it with a floating branch or rebuild DTC separately in the
WHP launcher.  The October 2026 fork update modernizes macOS native
shared-library test linking and Flex/Bison CI coverage.  It also fixes
``dtc -O asm`` on Mach-O: the generated DTB header uses C-computed
big-endian offsets instead of assembler shifts of forward label
differences (which Apple Clang rejects as non-relocatable).  Existing
assembly labels remain exported.  These are host toolchain portability
changes, not new Apple API dependencies in the portable libfdt ABI.

FDT symbol-link verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``system/device_tree.c`` calls the libfdt function ``fdt_nop_node``.
Our pinned DTC fork defines it in ``libfdt/fdt_wip.c``; the DTC Meson
``libfdt`` target includes that source.  QEMU's ``system/meson.build``
attaches the ``fdt`` dependency to the conditional device-tree source,
and the top-level ``meson.build`` explicitly keeps ``fdt`` on the
system-emulator executable's link dependencies after extracting system
objects.  Do not replace this with a copied libfdt implementation or
hard-coded linker flags in the WHP Ninja launcher.

For a persistent Meson build configured with the internal DTC provider,
audit the generated graph without rebuilding or resetting it::

    python3 scripts/tests/test-fdt-ninja-link.py build --internal

The audit checks ``build.ninja`` through Ninja's query and expanded
compilation database (including response files), verifies that the DTC
checkout matches the pinned wrap commit, and checks that
the link includes the internal ``libfdt.a`` and builds ``fdt_wip.c``.
After successful compilation, append ``--built`` to inspect the
archive's exported ``fdt_nop_node`` symbol with ``nm``.

If an existing build still selects an unsuitable system libfdt,
reconfigure that *same* build directory with ``-Dfdt=internal`` through
Meson and allow Ninja to regenerate its dependency graph.  Never delete
the whole build tree merely to change the libfdt provider.  If a source
checkout is stale relative to the DTC wrap pin, repair only that
Meson-owned subproject, respecting local modifications and the recorded
revision.  The PPC CI lane explicitly selects ``-Dfdt=internal`` and
uses the resulting archive for the FDT node-removal runtime test;
a host ``-lfdt`` runtime test alone does not validate the WHP fork.

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

#. The native compiler selected by ``seeds/cc.sh`` is a seed dependency. The WHP
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
   before its configure-time Make probes have run. The seed remains explicit
   through Python and the managed Automake bootstrap, and GNU Make's generated
   ``configure`` receives that same seed through ``MAKE``. The
   ``bootstrap --gen`` stage and the compile/link ``build.sh`` stage do not
   execute Make themselves, so seed-Make or compiler changes must not
   invalidate the cached Autoconf-generated source unnecessarily. Only after
   configure plus the no-Make ``build.sh`` succeed may the managed Make be
   promoted for downstream work.
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
