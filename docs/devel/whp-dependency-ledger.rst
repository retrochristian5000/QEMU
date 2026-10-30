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

QEMU's bootstrap must continue to materialize the recorded gitlink via
``git submodule update --init --depth 1 toolchains/llvm-project``.  It must
not use ``--remote``, which would replace an audited revision with an
unreviewed moving branch tip.  Publishing the pin makes fixes available to
the bootstrap; actual compiler and LLDB build success still requires
separate compilation and test evidence.

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
     - ``planned`` Meson source/tooling fork, pinned by gitlink; current QEMU configure uses its Python-venv Meson wheel and does not automatically execute this fork. Fork's current developer version is 1.12.99 and requires Python >= 3.10.
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
      +--> cc.sh native C seed
      |      +--> Python fallback
      |      +--> GNU sed / bootstrap-zlib / Git / Bash / SDL host builds
      +--> cxx.sh native C++17 seed -> Ninja / JACK / native LLVM
      |
      +--> seed Git
      |      +--> QEMU source checkout/update
      |      +--> pinned WHP zlib source
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
      |      +--> Python POSIX fallback
      |      +--> Automake / Autoconf maintainer stages
      |               |
      |               +--> pinned WHP Make fork
      |                       |
      |                       +--> managed GNU Make
      |                               +--> GNU sed
      |                               |      +--> Git-bootstrap zlib
      |                               |              +--> managed Git
      |                               +--> Bash
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

Pinned Meson source boundary
---------------------------

The WHP fork at ``toolchains/meson`` is available for controlled Meson
development.  It is a lazily initialized, exact-gitlink-pinned source tree,
not an unconditional dependency build or a replacement on ``PATH``.

QEMU's default configure path installs and invokes its venv Meson via
``python/scripts/mkvenv.py`` at ``pyvenv/bin/meson``.  To exercise the
QEMU-pinned WHP Meson fork without changing that default, export
``WHP_MESON_PROVIDER=fork`` before running ``configure``; the only other
accepted value is ``venv``.  The fork is initialized from the exact
``toolchains/meson`` gitlink only when downloads are enabled.  A different
checkout revision or local source edits cause an explicit failure, not a reset
or a branch switch.  The selected Python from QEMU's existing ``pyvenv``
runs ``toolchains/meson/meson.py``; no duplicate Python environment is
created.  The fork reports development version ``1.12.99`` and requires
Python >= 3.10, whereas the default QEMU Python selection accepts >= 3.9.
The selected provider is retained by ``config.status``.
The menuconfig ``QEMU Meson provider`` choice maps to
``WHP_MESON_PROVIDER=venv|fork`` and is an explicit opt-in, not a silent change to production builds.
The existing incremental configuration identity includes this selection so
changing providers requests configuration without wiping existing build outputs.

Use this provider to compare DTC wrap and incremental configuration behavior
with the default venv Meson in isolated or already compatible build trees.
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

Bootstrap phase ordering
------------------------

The host bootstrap is split into phases rather than one flat dependency list.

**Seed/tool phase:** ``cc.sh`` and ``cxx.sh``, seed GNU Make, seed sed, Python, Automake,
managed Autoconf, managed GNU Make, managed GNU sed, bootstrap zlib, managed
Git, Bash, and Ninja are available before native LLVM. The enforced managed
order is ``Automake -> Autoconf -> Make -> sed -> bootstrap-zlib -> Git ->
Bash -> Ninja``. These are generators/orchestration inputs needed to reach the compiler
build and therefore use build-machine roles. The seed GNU Make identity is
established before the Python fallback and exported through both ``MAKE_CMD``
and ``MAKE``. A single validated sed seed is likewise established before
Python and Automake. The seed Git boundary materializes the pinned zlib source.
If the host zlib is insufficient (or the WHP zlib is forced), an isolated
``deps/git-zlib`` fallback is built with ``CC_FOR_BUILD`` before managed Git
so Git's own ``ZLIB_PATH`` edge cannot silently consume the later QEMU
artifact prefix. Managed Autoconf is promoted
after Automake, managed Make after that Autotools pair, and managed GNU sed
after Make.

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

The ``cc.sh`` and ``cxx.sh`` native admission probes now compile
against C/C++ standard and POSIX ``unistd.h`` headers, link a libc
``access()`` call, and execute it. An empty ``main()`` alone could
accept a compiler with a missing macOS SDK. Probe subprocesses isolate
target include/library variables and injected loader search paths;
normal compiler invocations still receive all caller arguments and flags.
Relative explicit compiler seed paths are made absolute before promotion.

``cc.sh`` and ``cxx.sh`` are separate C and C++17 seed entry points.
They share the native compile/link/run probe, but each selects only its own
language driver. C++ selection first tries the driver paired with the native
C seed. Both adapters reject self-references and cross-adapter recursion;
``cc.sh --print-cxx`` is retired in favor of ``cxx.sh --print-cxx``.

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

``ld.sh`` is a POSIX native-linker seed adapter paired with ``cc.sh``.
``./ld.sh --print-ld`` (alias ``--print-seed``) resolves a linker that
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
sed seed. An explicit ``M4`` remains authoritative. On Darwin, otherwise,
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

grep seed bridge
----------------

The first grep used by QEMU is a host-side root capability rather than a
self-built GNU grep fork. ``grep.sh`` probes literal, extended and fixed-string
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
explicitly, including the compiler verified by ``cc.sh``, the GNU Make
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

**Seed sed** is a root capability. ``sed.sh`` validates the small semantic
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
source resolution, not the SHA-256 input.  The early parent source updater
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
The early QEMU source fast-forward updater handles only the parent Git
revision and submodule URL metadata. The launcher reconciles an existing DTC
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

The audit checks ``build.ninja`` through ``ninja -t commands``, verifies
that the DTC checkout matches the pinned wrap commit, and checks that
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
