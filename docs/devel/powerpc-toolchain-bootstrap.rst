PowerPC cross-toolchain bootstrap
================================

The WHP firmware path can bootstrap a small ``powerpc-elf`` toolchain for
OpenBIOS. The GNU lane builds the binary utilities required by firmware and a
freestanding C compiler without target operating-system headers or runtime
libraries. The Clang lane uses LLVM tools throughout and does not bootstrap
GNU binutils.

The canonical GNU implementation is ``scripts/bootstrap-powerpc-toolchain.sh``.
The Clang implementation reuses the same target and validation principles
while replacing the compiler and every required target binary utility.

Machine identities
------------------

Keep build, host, and target separate:

* ``build`` is the machine performing the bootstrap;
* ``host`` is the machine that runs ``powerpc-elf-gcc`` and binutils; and
* ``target`` is ``powerpc-elf``, the format emitted for OpenBIOS.

On native Apple Silicon, build and host canonicalize to
``aarch64-apple-darwin...`` even though Apple tools and ``uname`` use the name
``arm64``. The bootstrap normalizes that spelling and validates it with each
source tree's ``config.sub`` before compilation. The short target alias
``powerpc-elf`` may canonicalize to ``powerpc-unknown-elf`` while retaining the
installed ``powerpc-elf-*`` program prefix.

Build stages
------------

The GNU dependency order is intentional::

  validate host compiler and SDK
  download and verify binutils
  extract and configure binutils
  build and stage binutils
  assemble/link a PowerPC smoke object
  download and verify GCC
  prepare pinned GCC prerequisites
  configure and build GCC
  validate the complete staged cross-toolchain
  install atomically

GCC does not start until staged binutils can assemble and relocatably link a
32-bit big-endian PowerPC ELF object. This keeps a binutils failure from being
hidden by later compiler work.

Shell and environment policy
----------------------------

The public build selects one GNU Bash executable with ``WHP_BUILD_BASH``.
``CONFIG_SHELL`` is derived from that selection and is reused by nested
binutils/GCC configure recursion; there is no separate toolchain-shell knob.

The bootstrap clears target-tool, compiler-search, library-search, pkg-config,
and related variables that could leak from QEMU, Homebrew, or an earlier cross
toolchain. Build-machine C/C++ roles come from ``CC_FOR_BUILD`` and
``CXX_FOR_BUILD``. Host ``ar``, ``nm``, ``ranlib``, and ``strip`` are resolved
for the current machine rather than inherited accidentally.

On Darwin the host programs are Mach-O executables, so the selected SDK,
deployment target, and process architecture are applied to host compilation.
Apple Clang receives ``-arch`` plus the SDK/deployment flags. A deliberately
selected Darwin GNU GCC is validated by its target triplet and output Mach-O
slice rather than being treated as if ``-arch`` could change its configured
architecture.

Source policy
-------------

Release archives are the default. They already contain generated Autoconf and
Makefile inputs, so an ordinary bootstrap must not run ``autoreconf`` over the
source trees. If generated build files are intentionally changed, use the
release-specific Autotools versions in a separate regeneration workflow.

``MAKEINFO=true`` suppresses documentation generation because Texinfo output is
not required for the firmware compiler. It must not be used to hide accidental
Autoconf or Automake regeneration.

The optional official-Git source mode is selected by
``POWERPC_TOOLCHAIN_SOURCE_MODE=git`` and must resolve source revisions before
the normal bootstrap begins. Source URLs, refs, and explicit commit pins remain
provenance controls rather than aliases for build-state variables.

Darwin host libraries
---------------------

The toolchain does not inherit QEMU's Homebrew pkg-config search path. The
intentional Darwin exception is the ``libz`` supplied by the selected Apple
SDK. The pinned binutils/GCC release trees contain an old bundled zlib whose
legacy macOS compatibility macros conflict with current SDK declarations, so
Darwin configuration uses ``--with-system-zlib`` without adding Homebrew
package discovery.

Binutils contract
-----------------

The release bootstrap configures binutils for ``powerpc-elf`` with a narrow
firmware-oriented feature set. It disables GDB, gdbserver, gprofng, gold, NLS,
shared support, the simulator, and warnings-as-errors; it enables static
support and disables zstd. Darwin additionally uses the selected SDK zlib.

The completed stage must provide ``as``, ``ar``, ``ld``, ``nm``, ``objcopy``,
``objdump``, ``readelf``, ``strip``, and ``ranlib``. Smoke validation checks
that the produced object and relocatable link identify as 32-bit big-endian
PowerPC ELF before GCC may run.

GCC contract
------------

The GCC stage builds only the C frontend required for OpenBIOS. It targets
``powerpc-elf``, defaults to a PowerPC 604 CPU, uses freestanding/newlib-like
assumptions without target headers, disables multilib, threads, shared target
libraries, LTO and unrelated runtime libraries, and installs the compiler stage
rather than a complete hosted target runtime.

During GCC construction the staged ``powerpc-elf-*`` binutils are bound
explicitly through ``AS_FOR_TARGET``, ``LD_FOR_TARGET``, ``AR_FOR_TARGET``,
``NM_FOR_TARGET``, and the corresponding target-tool variables. Apple or
Homebrew tools later in ``PATH`` must never become the target assembler or
linker.

LLVM-only Clang toolchain
-------------------------

Select this lane with ``POWERPC_TOOLCHAIN_COMPILER=clang``. Host defaults may
select it automatically, but the implementation and firmware contract are not
host-specific.

The WHP LLVM fork is pinned by the QEMU git submodule at
``toolchains/llvm-project``. The gitlink is the revision authority; derived
LLVM source caches are not independent revision pins. An offline build requires
the submodule to be initialized already, and tracked LLVM changes must be
committed before QEMU advances the submodule pointer.

OpenBIOS continues to consume the GNU-style ``powerpc-elf-`` interface. The
migration publishes compatibility entry points while changing the underlying
implementation one stage at a time:

* ``powerpc-elf-gcc`` routes target compilation and generated assembly through
  WHP Clang and its integrated assembler;
* ``powerpc-elf-ld`` routes the normal firmware link through LLD;
* ``powerpc-elf-ar`` and ``powerpc-elf-ranlib`` route archive creation and
  indexing through ``llvm-ar`` and ``llvm-ranlib``;
* ``powerpc-elf-nm`` routes symbol inspection through ``llvm-nm``;
* OpenBIOS does not require or publish a separate ``powerpc-elf-as`` command;
  its assembly rule invokes the compiler driver with ``-x assembler``; and
* ``powerpc-elf-strip`` routes the firmware strip through ``llvm-strip`` after
  structure-preservation checks.

GNU ``libsframe`` implements the encoder and decoder for ``.sframe`` sections,
a compact stack-unwinding format. Current GNU BFD source calls that API while
parsing, merging, and writing those sections, so disabling ``libsframe`` alone
does not provide a sound smaller BFD foundation. OpenBIOS neither generates nor
consumes SFrame in this lane. Because Clang IAS, LLD, and the qualified LLVM
utilities cover every firmware operation, the Clang foundation does not build
GNU BFD, ``libsframe``, or any other GNU binutils component.

Older cached ``as``, ``objcopy``, ``objdump``, and prefixed ``readelf`` entry
points are removed. Firmware validation uses the pinned ``llvm-readelf``
directly, and no private ``*.bfd`` fallback is retained. The separate GCC lane
continues to use its complete GNU binutils contract.

The LLD smoke link checks the OpenBIOS-critical linker interface and requires a
32-bit big-endian PowerPC executable whose entry, reset/vector geometry, and
load segments remain inside the Power Mac PROM window with no dynamic loader.
The strip smoke test uses an OpenBIOS-shaped PowerPC ELF and requires
``llvm-strip`` to preserve ELF identity, entry point, load geometry, and
allocatable code bytes while removing the symbol table.

The compiler/LLVM foundation, LLD, archive, symbol, and strip stages keep
separate markers so a policy change in one stage cannot be hidden by an
otherwise-current cache. ``POWERPC_TOOLCHAIN_SOURCE_MODE`` controls only the
GNU GCC lane; the Clang lane always comes from the QEMU LLVM submodule gitlink.

Cache and path policy
---------------------

``POWERPC_TOOLCHAIN_DIR`` is the public toolchain location. Work and download
cache directories are derived from it by the build system rather than exposed
as independent configuration choices. Incremental builds reuse a toolchain
only when its marker matches the current source, host, shell, SDK, and tool
policy and its installed executables still pass usability checks.

Force a new bootstrap with::

  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 ./build.sh whp-openbios-ppc

The GNU bootstrap marker schema is ``7`` and the LLVM-only foundation schema is
``11``. A schema or input change invalidates older cached toolchains instead of
trying to reinterpret them. LLVM stages maintain their own marker schemas
alongside the foundation marker.

Validation boundary
-------------------

A green QEMU host build does not by itself validate the firmware toolchain when
``BUILD_OPENBIOS=0`` or ``BOOTSTRAP_POWERPC_TOOLCHAIN=0``. Full firmware
validation requires the selected compiler and its integrated assembler, linker,
and strip stages to pass their smoke checks, then OpenBIOS must build, pass ELF
validation, and boot under the intended QEMU PowerPC machine.

Failure classification
----------------------

``validating host compiler and SDK``
  Treat this as a host ABI, compiler, SDK, architecture, or shell-policy
  problem.

``configuring and building binutils``
  Inspect ``build-binutils-<version>/config.log`` first. Do not proceed to GCC
  until the assembler/linker stage is understood.

``validating staged binutils``
  The tools installed but failed the PowerPC ELF smoke contract.

``preparing GCC prerequisites``
  A pinned prerequisite download or source-preparation step failed.

``configuring and building GCC``
  Inspect ``build-gcc-<version>/config.log`` and verify that staged target tools
  are the ones actually selected.

LLVM tool stage failure
  Inspect the stage-specific marker and smoke directory. Each tool is
  qualified against the required PowerPC/OpenBIOS contract before its
  target-prefixed entry point is published.

``validating complete PowerPC toolchain``
  The compiler installed but failed target, endianness, sysroot, or executable
  checks.

The reported first failing stage is the diagnostic boundary. Do not repair a
later stage until the earlier one is proven correct.
