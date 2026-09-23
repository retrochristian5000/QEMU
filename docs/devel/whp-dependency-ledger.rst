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
   * - ``toolchains/bash``
     - ``bash``
     - yes
     - Bash fallback for WHP orchestration; host C compiler + GNU Make.

Known bootstrap and library edges
---------------------------------

The current host-side order is intentionally split from the QEMU artifact
graph.  A compact view is::

  primitive host tools / SDK / compiler
      |
      +--> Python >= 3.9
      |      +--> Bash fallback
      |      +--> Ninja fallback
      |
      +--> CMake --------------------+
      |      |                       |
      |      +--> SDL3               +--> Aften
      |      +--> optional mold            |
      |                                   +--> JACK full macOS server
      |
      +--> GNU Make
      |      +--> Python POSIX fallback
      |      +--> Bash fallback
      |      +--> libisofs
      |
      +--> optional native LLVM
             |
             +--> QEMU host compiler
             +--> firmware cross-toolchain lanes

  QEMU configure -> Python venv/Meson -> Meson dependency resolution
                 -> Ninja artifacts -> GNU Make test/firmware umbrella

Python is earlier than QEMU configuration because configure creates and uses
the QEMU Python virtual environment.  Ninja is also required before normal
Meson configuration.  A native WHP LLVM build is optional and must not become
a prerequisite for bootstrapping the compiler that is needed to build LLVM
itself.

Core QEMU dependencies represented by the minimal CI/build metadata include
GLib/gmodule, zlib, pixman, libffi, and libfdt in addition to the shell,
compiler, Python, Meson, Ninja, pkg-config, and basic build utilities.  The
full ``tests/lcitool/projects/qemu.yml`` profile adds feature-gated libraries
such as ALSA, GTK, GnuTLS, libcurl, libiscsi, libnfs, libslirp, libssh,
libusb, PipeWire, PulseAudio, SDL, SPICE, zstd, and others.  Those optional
libraries stay feature-gated rather than becoming WHP bootstrap roots.

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

#. A toolchain may not require the QEMU binary it is being built to produce.
#. Native LLVM must bootstrap from an existing host compiler; it must not make
   itself its own root dependency.
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
