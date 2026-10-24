macOS host builds
=================

The WHP wrapper supports native Apple Silicon and Intel macOS builds. It keeps
four roles separate:

* the process architecture that runs the build;
* the architecture of the QEMU host executable;
* QEMU's emulation target, for example ``ppc-softmmu``; and
* firmware targets such as ``powerpc-elf``.

For the supported native build path the QEMU host architecture is derived from
the running process. There is no separate host-architecture override.

Entry point and SDK policy
--------------------------

Use the normal launcher::

  ./build.sh

On macOS it enters ``scripts/macos-builder.sh`` automatically. The wrapper
selects the active Apple developer directory and SDK with ``xcode-select`` and
``xcrun`` unless ``DEVELOPER_DIR`` or ``SDKROOT`` is supplied. SDK identity
and deployment policy are kept separate: the wrapper reads the macOS target
minimum/default/maximum from ``SDKSettings.json`` or ``SDKSettings.plist`` when
available. The automatic deployment target is the running macOS major/minor
version while that version is supported by the selected SDK. If the host is
newer than an explicitly selected older SDK, the automatic target is clamped
to the SDK's default deployment target instead of making the host version an
invalid minimum. A beta or newer SDK on an older host therefore keeps the host
runtime as the minimum so build-time executables remain runnable.

An explicit ``MACOSX_DEPLOYMENT_TARGET`` is never silently clamped. It must fit
the selected SDK's deployment range. If SDK deployment metadata cannot be read,
the SDK release version is used as the fallback default and its major/minor
release line supplies a conservative maximum. arm64 builds still require a
deployment target of macOS 11.0 or newer.

The wrapper owns ``-isysroot`` and ``-mmacosx-version-min`` for C, C++,
Objective-C, and link flags. Do not duplicate those options manually in
``CFLAGS``, ``CXXFLAGS``, ``OBJCFLAGS``, ``CPPFLAGS``, or ``LDFLAGS``.

Architecture and Rosetta
------------------------

Native Apple Silicon::

  arch -arm64 ./build.sh

An intentional Intel build under Rosetta::

  arch -x86_64 env MACOS_ALLOW_ROSETTA=1 ./build.sh

The process architecture selects the build directory and architecture flags.
Native Arm expects the Homebrew prefix ``/opt/homebrew``; Intel and Rosetta
builds expect ``/usr/local``. A nonstandard layout requires the explicit
``MACOS_ALLOW_MIXED_HOMEBREW=1`` escape hatch.

Universal binaries are not produced in one build tree. Build and test arm64
and x86_64 independently before combining artifacts.

Build-machine and host compilers
--------------------------------

``CC`` and ``CXX`` compile QEMU host objects. ``OBJC`` compiles Cocoa code.
``CC_FOR_BUILD`` and ``CXX_FOR_BUILD`` compile tools that execute during the
build, including firmware helpers and cross-toolchain host programs.

Apple Clang selected through ``xcrun`` is the default for all of those roles.
An experimental non-Clang QEMU host compiler requires a matching C/C++ pair and
``MACOS_ALLOW_NONCLANG=1``. Objective-C and build-machine tools remain on the
validated Apple toolchain unless the build logic explicitly says otherwise.

Before QEMU configuration, ``scripts/verify-macos-toolchain.sh`` verifies the
effective compiler pipeline. It checks target triples, Clang resource paths,
compiler configuration files, representative C/C++/Objective-C links,
build-machine execution, and resulting Mach-O architecture slices.

Shared executable POSIX startup
-------------------------------

All ``qemu-system-*`` binaries enter the common ``system/main.c`` and
``system/vl.c`` startup path, but each emulator still has target-specific
devices and machine initialization. The common ``qemu_init_exec_dir()``
helper also serves several QEMU host tools and resolves relocated firmware,
module and data paths.

On Darwin, the ``_NSGetExecutablePath()`` result may exceed
``PATH_MAX``. The helper now retries only oversized paths using the size
returned by dyld, resolves the executable's symlinks using
``realpath(path, NULL)``, and frees that temporary allocation. If dyld
or ``realpath`` cannot supply the canonical location, startup continues
through the existing ``argv[0]`` and configured bindir fallbacks rather
than returning with an unset directory.

POSIX startup and daemon job-control dispositions use ``sigaction`` with
initialized structures. The double-fork daemonization protocol and existing
close-on-exec pipe are unchanged; substituting ``posix_spawn`` here would
not preserve daemon semantics.

To verify the source contract without building the full host toolchain::

  python3 scripts/tests/test-system-posix-startup.py

On a native macOS build, smoke-test the exact emulator binary with
``--version`` and ``-machine help``, and verify that relocated module
and firmware lookups still succeed. Repeat with the same binary under a
symlinked path. These changes repair known path and signal-handling edge
cases, but **do not establish a wall-clock startup speedup**. Timing and
system-call tracing are required before claiming one.

TCG code cache and macOS memory measurement
-------------------------------------------

The fork budgets automatic system-mode TCG cache size using both host and
guest RAM. A reserved JIT mapping does not consume its full size in resident
RAM. The two virtual addresses used by split-W^X can alias the same pages,
so their virtual sizes must not be added as physical memory consumption.

The existing QMP/RSS benchmark can report live code-cache occupancy, TB count
and TB flush count beside paused, running and peak process RSS::

  python3 scripts/bench-host-memory.py --qemu /path/to/qemu-system-ppc \
    --machine mac99 --guest-mib 256 --boot-seconds 5 --jit-stats

Compare the automatic policy with a smaller explicit code cache, keeping
guest RAM, virtual CPU count, split-W^X mode and workload identical::

  python3 scripts/bench-host-memory.py --qemu /path/to/qemu-system-ppc \
    --machine mac99 --guest-mib 256 --boot-seconds 5 --jit-stats \
    --tb-size 32

The ``--jit-stats`` option reads the experimental QMP ``x-query-jit``
interface; a missing or changed counter is an error, not a fabricated
measurement. JIT cache occupancy and TB flushes do not attribute all RSS
to TCG, measure macOS physical footprint or establish sustained throughput.
Compare repeated runs under a representative workload before changing
runtime cache sizing defaults.

Environment hygiene and build identity
--------------------------------------

The macOS wrapper removes inherited search variables that can silently redirect
headers, libraries, compiler helpers, CMake, pkg-config, or dynamic-loader
searches. It also removes the opposite-architecture Homebrew ``bin`` and
``sbin`` entries from ``PATH`` unless a mixed layout was explicitly allowed.

The build identity records the process architecture, SDK, deployment target,
compiler signatures, flags, dependency paths, LTO policy, and configure shell.
If that identity changes, the wrapper recreates only a WHP-owned QEMU build
tree. It refuses to delete an unrelated directory. Persistent firmware tools
remain outside the disposable QEMU Meson tree.

``MACOS_ALLOW_INHERITED_SEARCH_PATHS=1`` is an expert escape hatch for an
intentional external search environment. ``MACOS_AUTO_CLEAN=0`` converts a
required clean reconfiguration into an error instead of automatically
recreating the owned build directory.

Lean Bash bootstrap
-------------------

The managed Bash fork is built as a noninteractive host shell. QEMU needs the
resulting executable, not the Bash manuals, translations, or loadable builtins,
so its bootstrap copies only the tested ``bash`` binary rather than running
the recursive upstream ``make install`` target. The prior installed Bash
remains available during compilation; the replacement is staged with a
rollback path if publication fails. The existing executable, ABI and
``MACHTYPE`` runtime checks still gate publication.

If ``JOBS`` is unset, this small host-tool bootstrap uses at most two make
jobs (or one on a single-core host) instead of using every logical CPU.
An explicit positive ``JOBS`` value remains authoritative. This budget is
independent of native LLVM compile, TableGen, and linker pools.

The pinned Bash source is taken from a Git archive, not from a potentially
dirty checkout. Its extraction now streams the archive directly from Git
rather than retaining the complete tar in Python's memory; Git errors are
spooled to a temporary file and failed extractions remove their partial
workspace. This reduces peak *bootstrap* memory use without changing the
resulting shell binary. The archive-extraction regression test includes an
8 MiB source file and checks peak Python allocations.

Darwin uses the macOS system allocator: the Bash fork selects it for Darwin,
and the managed bootstrap explicitly passes ``--without-bash-malloc``.
This is an allocator compatibility safeguard, not a claim that Bash has no
runtime memory leaks. Runtime heap behavior on arm64 and arm64e still requires
native macOS profiling; the streaming change affects source extraction only.

Bash POSIX descriptor duplication
---------------------------------

The pinned WHP Bash fork now prefers ``fcntl(F_DUPFD_CLOEXEC)`` when it
saves the shell's private, buffered script-input descriptor. On hosts that
support the command (including modern macOS), a single descriptor-duplication
operation sets ``FD_CLOEXEC`` atomically instead of using the historical
``F_DUPFD`` followed by ``F_SETFD``. This also avoids one ``fcntl``
call on successful saves. A kernel that rejects the command with ``EINVAL``
and systems without the constant retain the old two-step path. An
explicitly supplied destination fd still receives the traditional
close-on-exec handling.

Only this private script descriptor is changed. Bash pipelines, coprocesses,
job control, ordinary shell redirections, and the double-fork/QEMU daemon
path retain their established descriptor inheritance rules. In particular,
``pipe2`` is not adopted blindly on Darwin, where it is not uniformly
available. The ``toolchains/bash`` gitlink remains authoritative; the
native macOS Bash bootstrap workflow runs the fork's
``tests/whp-posix-fd.sh`` smoke test with the actual built Bash after
checking the selected ARM64e ABI.

The smoke test detects changed script and pipeline behavior but cannot by
itself establish an atomicity race or benchmark wall-clock startup.
Do not claim a boot-time gain without repeated native measurements.

Link-time optimization
----------------------

``QEMU_HOST_LTO`` controls LTO for QEMU's Meson-built host artifacts. Native
Apple Silicon enables it by default. Do not place raw ``-flto`` or related LTO
linker options in global compiler or linker flags; those flags could leak into
firmware helpers or nested toolchain builds.

In menuconfig, **LTO mode (ThinLTO or full)** selects
``QEMU_HOST_LTO_MODE=auto|thin|full``. The default ``auto`` preserves
the previous behavior: Darwin prefers ThinLTO, other hosts retain Meson's
default full-LTO mode. Explicit ``thin`` selects ``b_lto_mode=thin``;
explicit ``full`` selects Meson's ``b_lto_mode=default`` and disables
the ThinLTO cache. Either explicit mode enables the host LTO toggle if
that toggle is ``auto``; choosing a mode while LTO is disabled is an
error. The selected compiler and linker must support that mode. This
does not enable LTO in firmware or native LLVM bootstrap stages.

When LTO is enabled on Darwin, ``configs/meson/darwin.txt`` defaults to
``b_lto_mode=thin`` and ``b_thinlto_cache=true``. Both the Bash and portable
build entries limit ``b_lto_threads`` to the established macOS job budget.
Meson still owns compilation and linking: do not inject ``-flto=thin``
globally, and do not infer that the option is enabled merely because ThinLTO
mode and caching appear in the native file. Check ``b_lto`` in Meson's
``meson-info/intro-buildoptions.json`` to verify actual activation.

``scripts/verify-macos-lto.sh`` compiles separate translation units using
the selected LTO mode, indexes one with the selected ``AR`` and ``RANLIB``,
then links through that archive with the selected compiler/linker pipeline.
It checks the Mach-O architecture, executes the result, and records the
actual ``LTO_MODE`` and archive tools in ``.whp-macos-lto``. This catches
mismatches where a full-LTO preflight passes but ThinLTO archive extraction
fails (or vice versa). A failed preflight signals an incompatible
compiler/archive/linker combination, not permission to inject raw flags.

ThinLTO's cache primarily helps **incremental** re-links; a clean link still
runs the optimization backends. The cache belongs to the owned Meson build
tree and is not a substitute for keeping the selected Clang, archiver, and
Mach-O linker coherent.

Shared native LLVM host toolchain (experimental)
-----------------------------------------------

The WHP native LLVM bootstrap can optionally generate the aggregate
``libLLVM`` dynamic library and Clang's ``libclang-cpp`` for host tools.
This is different from ``BUILD_SHARED_LIBS=ON``, which generates many
component DSOs and is discouraged by LLVM's distribution documentation.
The supported, explicit trial is::

  NATIVE_LLVM_SHARED_TOOLCHAIN=1 BOOTSTRAP_NATIVE_LLVM=1 \
    ./build.sh qemu-system-ppc

The default is ``NATIVE_LLVM_SHARED_TOOLCHAIN=0``; existing static LLVM
toolchains retain their *exact prior schema-12 cache marker* and therefore
do not rebuild merely because the option was introduced. With ``1``,
the native LLVM/Clang CMake graph uses ``LLVM_BUILD_LLVM_DYLIB=ON``,
``LLVM_LINK_LLVM_DYLIB=ON``, ``CLANG_LINK_CLANG_DYLIB=ON``,
``LLVM_DYLIB_COMPONENTS=all``, and ``BUILD_SHARED_LIBS=OFF``.
The two dynamic library components are included in the same installed
distribution as Clang, LLD, compiler resources, and platform runtimes.

The bootstrap validates that installed ``libLLVM`` and
``libclang-cpp`` are present (``.dylib`` on macOS, ``.so`` on ELF
hosts). On macOS it also checks the installed Clang binary's actual
``libclang-cpp`` load command. LLVM's own CMake helpers provide
relative runtime search paths (``@loader_path/../lib`` or
``$ORIGIN/../lib``). The shared libraries and their binaries must stay
together; moving just ``clang`` or ``ld64.lld`` without the matching
libraries breaks execution. The program still builds cross-target objects
and firmware images with their existing ABI-specific policies; a host
shared-library option does not turn guest binaries into shared libraries.

**Benchmark before adopting this profile by default.** A combined DSO may
reduce duplicated LLVM code in multiple tools, but adds a large library link
and dynamic-loader startup dependencies. Compare installed size, clean link
time, incremental link time, process startup, resident memory and QEMU guest
execution separately. It does not repair the Mach-O LLD
``__asan_globals_required`` symbol problem, which has its own targeted
linker/runtime probe above. To return to the original static profile, set
``NATIVE_LLVM_SHARED_TOOLCHAIN=0``; existing incremental CMake objects
are retained, while the installed toolchain distribution is regenerated
for the requested linking policy.

Shared SDL3 host library
------------------------

The pinned SDL3 fallback (``toolchains/sdl``) now builds a **shared**
``libSDL3`` library instead of a static-only archive. CMake uses
``SDL_SHARED=ON``, ``SDL_STATIC=OFF``, and a versioned bootstrap cache
identity; stale static-only cache entries are rebuilt in place. The
bootstrap verifies that a loadable ``.dylib``, ``.so``, or ``.dll``
was installed before recording success. ``BOOTSTRAP_SDL=auto`` continues
to prefer a suitable system SDL3 before trying the pinned fallback.

QEMU links dynamically through its existing SDL3 Meson/pkg-config dependency.
For private fallback builds, the QEMU host link receives build-tree-relative
``@loader_path`` (macOS) or ``$ORIGIN`` (ELF) runtime paths for emulators
and one-directory-deep loadable modules. Build/test processes also receive
the fallback prefix's dynamic-library search path. This is not a general
promise that an installed QEMU executable will find SDL3 after deleting the
private build tree: package the shared library alongside the executable or
depend on a compatible system SDL3 runtime for redistributed binaries.

Dynamic linking avoids embedding the SDL3 archive in every linked consumer
and may save space or rebuilding work, but does not guarantee higher TCG
execution speed. Measure runtime separately from binary size and link time.

When linking SDL3 with WHP's native Mach-O ``ld64.lld``, a newer Clang may
report an undefined symbol such as
``_objc_msgSendClass$shouldMonitorBackgroundEvents$_OBJC_CLASS_$_GCController``.
The SDL GameController backend reads and writes this class property in
``src/joystick/apple/SDL_mfijoystick.m``. The symbol is a compiler-emitted
Objective-C class-message stub that the selected linker must synthesize,
**not** a missing GameController implementation or SDL export.

The WHP native ``ld64.lld`` has not yet been verified to synthesize class
stubs, while Clang can emit them. QEMU already disables the unsupported
optimization for its own Objective-C compilation, but its macOS wrapper runs
**after** the SDL bootstrap. The pinned SDL fork's CMake build compiles Apple
``.m`` files through its C target using ``-x objective-c``, so merely
setting ``CMAKE_OBJC_FLAGS`` would not protect those sources. The SDL
fork now has an opt-in ``SDL_OBJC_NO_CLASS_SELECTOR_STUBS`` CMake setting,
which adds ``-fno-objc-msgsend-class-selector-stubs`` to its ``.m`` sources
only. QEMU enables that setting **only with its managed Mach-O LLD**, and
pins the corresponding SDL commit in ``toolchains/sdl``. Apple ``ld`` and
ordinary C source compilation remain unaffected. The bootstrap cache
identity tracks the linker and mitigation selection so incompatible old SDL
objects are not reused. If the linker gains the required support, retire the
opt-out after a direct Objective-C compilation-and-link test.

Darwin AddressSanitizer global-link validation
----------------------------------------------

Clang's Mach-O AddressSanitizer instrumentation emits
``__DATA,__asan_globals`` metadata and calls
``__asan_register_image_globals``. The final executable must link via
the **selected Clang driver** with ``-fsanitize=address`` so that the
matching ``libclang_rt.asan_osx_dynamic.dylib`` is selected. Defining
a dummy ``__asan_globals_required`` or allowing unresolved symbols
would conceal a broken compiler/runtime/linker pairing rather than repair it.

QEMU's host build strips inherited optimization and sanitizer overrides from
``CFLAGS``, ``CXXFLAGS``, and ``OBJCFLAGS`` after firmware preparation,
including negative ``-fno-sanitize=...`` settings and frame-pointer overrides.
The selected ``QEMU_ASAN=1`` profile then applies its instrumentation through
Meson to C, C++, and Objective-C host sources. Do not put sanitizer policy in
``CPPFLAGS`` or force ``-fsanitize=address`` into ``LDFLAGS``: use
``QEMU_ASAN=1`` so the Clang driver links the matching runtime.

WHP's native LLVM bootstrap now offers a focused ASan probe. It is enabled
automatically for ``QEMU_ASAN=1`` and can also be requested directly
with ``NATIVE_LLVM_VALIDATE_ASAN=1``. The probe:

#. verifies the selected Clang's own dynamic ASan runtime exists;
#. compiles a real ASan-instrumented global and checks the resulting
   Mach-O object's ``__asan_globals`` section;
#. links the object with that same Clang driver and the selected Mach-O
   linker (``ld64.lld`` or Apple ``ld``);
#. if ``ld64.lld`` fails on ``__asan_globals_required``, compares the
   identical Clang/link invocation using Apple ``ld`` to isolate a
   linker implementation problem from a runtime/SDK mismatch.

A probe failure stops **only the requested ASan validation**. It does
not invalidate or delete an otherwise usable incremental native LLVM
installation, nor does it force a full LLVM rebuild. For a direct diagnostic
on the installed compiler without starting QEMU, run::

  python3 scripts/verify-native-asan-darwin.py \
    --clang /path/to/llvm/bin/clang \
    --readobj /path/to/llvm/bin/llvm-readobj \
    --arch arm64 --sdkroot "$(xcrun --sdk macosx --show-sdk-path)" \
    --deployment-target 15.0 --use-lld

Replace the SDK/deployment target with those of the actual build.
For AddressSanitizer, omit ``--use-lld``: the WHP profile still selects
Apple ``ld`` for this runtime contract, including ARM64e. The probe does
not claim to repair the missing symbol; its output identifies whether the
next code change belongs in Clang instrumentation, compiler-rt distribution,
or Mach-O LLD.

ARM64e AddressSanitizer runtime admission
-----------------------------------------

ARM64e ASan cannot be approved just because Clang emitted
``__DATA,__asan_globals`` or Apple ``ld`` linked an executable. On Darwin,
ASan relies on the Clang-linked
``libclang_rt.asan_osx_dynamic.dylib`` and dyld. The pinned LLVM
compiler-rt also has ARM64e-specific test deployment logic. Do not
silently substitute an unrelated runtime or assume ARM64 and ARM64e
sanitizer compatibility without executing instrumented code.

``scripts/verify-native-asan-darwin.py`` retains the original
``__asan_globals_required`` link diagnostic. Use ``--execute``
to add two ARM64e C++ runtime checks after the metadata link, or
``--runtime-only`` to run them without needing ``llvm-readobj``.
The checks:

#. verify that Clang and Clang++ select the same compiler-rt resource;
#. require the dynamic Darwin ASan runtime to exist;
#. link and execute an instrumented C++ callback using the requested
   ``-arch``, checking the ARM64e PAC ABI macros when appropriate;
#. run a separate instrumented heap-out-of-bounds case and require
   a nonzero exit **and** an actual AddressSanitizer report;
#. clear inherited ``DYLD_*`` variables during execution so a user's
   injection/fallback search paths cannot conceal dyld resolution errors.

For a direct check with Apple's toolchain::

  python3 scripts/verify-native-asan-darwin.py \
    --clang "$(xcrun --find clang)" \
    --clangxx "$(xcrun --find clang++)" \
    --arch arm64e \
    --sdkroot "$(xcrun --sdk macosx --show-sdk-path)" \
    --deployment-target "$(sw_vers -productVersion | cut -d. -f1,2)" \
    --runtime-only

An explicit ``WHP_MACOS_ARCH=arm64e QEMU_ASAN=1`` host build now
requires that runtime test to pass **before** expensive firmware or QEMU
compilation. Default ASan builds remain on arm64 in auto mode, and ASan
continues to use Apple ``ld`` rather than the experimental Mach-O LLD
lane. The bootstrap also runs the execution test when explicitly
validating an ARM64e native LLVM compiler with
``NATIVE_LLVM_VALIDATE_ASAN=1``.

The separate ``asan-arm64e-runtime.yml`` workflow uses ordinary ARM64 as
a control before testing ARM64e with Apple's Clang. A positive result
establishes the tested macOS/compiler-rt/runtime combination; it does
not prove that every ASan-instrumented QEMU module or coroutine works.
Leave compiler-rt's PAC signal-context handling intact without evidence
for an ISA-level modification.

ARM64e host auto-detection
---------------------------

On Apple Silicon, ``WHP_MACOS_ARCH=auto`` (the default) first checks
whether the selected C and C++ drivers can compile, link **and execute**
an indirect call with the arm64e pointer-authentication ABI. If either
probe fails, QEMU uses the ordinary ``arm64`` host ABI. This is a host
capability test; a compiler merely accepting ``-arch arm64e`` is not
sufficient. Intel builds remain ``x86_64``. AddressSanitizer stays on
``arm64`` in automatic mode.

The selected linker also participates in detection: Mach-O LLD may
auto-select arm64e only with ``WHP_ARM64E_USE_LLD=1`` and a successful
authenticated-fixup probe. Explicit ``WHP_MACOS_ARCH=arm64`` disables
auto-promotion. Explicit ``WHP_MACOS_ARCH=arm64e`` retains the
compile/link-only development override, but it does not prove that
the resulting QEMU executable can launch or that its TCG runtime passes.
The macOS runtime and TCG smoke tests remain necessary validation.

Apple A18 Pro CPU-profile evidence
----------------------------------

The pinned LLVM fork names ``apple-a18-pro`` separately from ``apple-a18``.
Both currently share the Apple M4-derived ISA feature baseline. This is
provisional and is **not** evidence of matching pipeline latencies, cache
sizes, or availability of every optional Armv9.2-A extension.

LLVM's ``apple-a18-pro`` now selects a separate
``AppleA18ProModel`` rather than the Apple A7-era ``CycloneModel``.
The new scheduling model is deliberately incomplete: it does not inherit
Cyclone's integer, floating-point, or branch resource reservations and
per-opcode latencies. Its coarse values (issue width 6, buffer 192, load
latency 4, misprediction penalty 16) are **temporary Cyclone-derived
assumptions**, not measured A18 Pro properties. Code-generation and runtime
performance must be compared against the previous model before attempting
to promote complete scheduling or claim a performance improvement.

Apple's public CPU Optimization Guide identifies ISA feature queries and
SME as relevant to Apple silicon; per-chip instruction and latency details
in the guide require additional developer access. Apple's public XNU SME
documentation says its implementation does not expose ordinary non-streaming
SVE and does not currently implement ``FEAT_SME_FA64``. Apple's arm64e
guidance also distinguishes ordinary PAC from the newer PAuth_LR / arm64e.x1
contract. Do not add these features just because the CPU implements
Armv9.2-A or an earlier arm64e ABI.

To audit the pinned LLVM source against the feature-policy guard and collect
Darwin sysctl observations on an A18 Pro host, run::

  python3 scripts/tests/test-apple-a18-pro-profile.py

The script fails if the current pinned profile unexpectedly enables an
unverified feature or an A18 Pro host explicitly reports a required ISA
feature as unavailable. Unknown sysctls are recorded as unknown, not zero.
The source check requires an initialized ``toolchains/llvm-project``
submodule; ``--hardware-only`` permits a runtime-only report. The CI
source check does not substitute for execution tests on actual A18 Pro
hardware.

References: Apple's ``Apple Silicon CPU Optimization Guide`` and
``Preparing your app to work with pointer authentication``, plus Apple
XNU ``doc/arm/sme.md``.

LLVM Mach-O inspection with llvm-otool
------------------------------------

The pinned LLVM source defines ``llvm-otool`` as an ``llvm-objdump``
symlink with an otool-compatible argument parser. The WHP Darwin native
LLVM distribution includes this entry point alongside ``llvm-objdump``.
It does not compile a second disassembler or independently verify LLVM's
Mach-O decoder. Inspect a linked executable using::

  "$NATIVE_LLVM_DIR/bin/llvm-otool" -h ./qemu-system-ppc
  "$NATIVE_LLVM_DIR/bin/llvm-otool" -l ./qemu-system-ppc
  "$NATIVE_LLVM_DIR/bin/llvm-otool" -t -v -mcpu=apple-a18-pro ./qemu-system-ppc
  "$NATIVE_LLVM_DIR/bin/llvm-otool" -chained_fixups ./qemu-system-ppc
  "$NATIVE_LLVM_DIR/bin/llvm-otool" -dyld_info ./qemu-system-ppc

The ``-mcpu=`` option configures the disassembler; it does not verify the
running machine's ISA capabilities or change the target of the original
build. Not every Mach-O file has chained fixups or dyld rebases. For the
ARM64e-authenticated relocation fixture, the WHP LLD probe checks the
versioned pointer format using both LLVM command interfaces when
``llvm-otool`` is installed, while the existing ``llvm-objdump``
metadata decoder still validates PAC keys and discriminators.

Native LLVM precompiled headers
-------------------------------

The pinned LLVM fork defines a real ``LLVMSupport`` precompiled header and
reuses it in eligible C++ targets. ``NATIVE_LLVM_PCH=auto`` (the default) enables
PCH for native macOS LLVM builds when the host C++ compiler is Apple Clang or
LLVM Clang 18+, including when ``sccache`` is selected. Linux and other hosts
retain PCH disabled by default. ``NATIVE_LLVM_PCH=0`` explicitly disables
PCH; ``NATIVE_LLVM_PCH=1`` requests it even outside the automatic profile.

A saved ``.whpconfig`` entry of ``NATIVE_LLVM_PCH=n`` remains an explicit
opt-out after this change; select ``auto`` in ``menuconfig`` to activate the
new default without overwriting user preferences.

When PCH is enabled together with ``sccache``, the native LLVM bootstrap
keeps ``CMAKE_C_COMPILER_LAUNCHER=sccache`` but clears
``CMAKE_CXX_COMPILER_LAUNCHER``. PCH generation and every LLVM C++ compile
(including PCH consumers) bypass sccache; this avoids unsupported cache reuse
and preserves C-object caching. It does **not** enable C++ sccache hits for
LLVM in PCH mode. With PCH disabled, both C and C++ retain sccache. The QEMU
build's separate cache launcher is unaffected. The bootstrap forces
``LLVM_CCACHE_BUILD=OFF`` so LLVM's legacy compile-launch rule cannot
override the per-language CMake launchers. With ``ccache``, LLVM adds Clang's
``-fno-pch-timestamp`` option for reproducible PCH inputs.

The chosen ``CMAKE_DISABLE_PRECOMPILE_HEADERS`` value belongs to both the
installed-toolchain marker and the CMake configuration identity, so switching
PCH policy reconfigures the existing Ninja graph rather than silently reusing
incompatible objects. To verify that PCH is *actually* generated, inspect the
native LLVM ``build.ninja`` for ``cmake_pch`` rules; a CMake OFF value alone
cannot establish a performance improvement. PCH adds initial build work,
memory and disk use, so benchmark clean and incremental builds before
claiming a speedup.

Bundled Ninja ARM64e admission and reuse
---------------------------------------

The pinned Ninja host helper chooses ``arm64e`` in
``NINJA_MACOS_ARCH=auto`` mode only when its selected C++ compiler
exposes the pointer-authentication ABI and a compiled indirect-call
probe has the ``arm64e`` Mach-O slice **and executes successfully**.
Otherwise Apple Silicon retains the ordinary ``arm64`` fallback.
An explicit ``NINJA_MACOS_ARCH=arm64`` remains authoritative, and an
explicit ``arm64e`` request must pass the active runtime probe.

For an unchanged, already-installed automatic ``arm64e`` Ninja,
``scripts/ensure-ninja.py`` first verifies the exact bootstrap marker,
Mach-O slice and actual executable, then reuses that binary without
compiling and linking another temporary probe. A stale marker, wrong
slice or failed execution restores the normal admission path. The
bootstrap does not modify the pinned Ninja submodule, invoke a new
linker policy or change any QEMU build jobs.

The bundled-Ninja workflow tests the direct ``posix_spawn`` lane, the
shell fallback and a no-op incremental build when its selected binary
is ``arm64e``. These checks establish runtime behavior, **not** a
wall-clock performance advantage over ``arm64``.

Incremental LLVM builds and Ninja scheduling
-------------------------------------------

The pinned WHP Ninja fork can prioritize the longest remaining dependency
chains using previous command durations from ``.ninja_log``. The native LLVM
distribution build enables this scheduler hint by default when it invokes
CMake/Ninja; a clean build has no timing history, so it retains the normal
depth-based priorities. Ninja parallel job limits, LLVM compile/link pools,
and the installation cache identity are unchanged.

To compare the old and new scheduling policy, set
``NATIVE_LLVM_CRITICAL_PATH_TIMES=0`` to disable the hint or
``NATIVE_LLVM_CRITICAL_PATH_TIMES=1`` to enable it. The setting only affects
build scheduling, not the generated machine ABI. System Ninja binaries that
lack the WHP extension ignore ``NINJA_CRITICAL_PATH_TIMES``. This is a
potential incremental-build speedup, not a verified wall-clock improvement;
measure before adopting a tighter job limit or changing the LLVM cache.

LLVM ar / ranlib ARM64e archive and ABI integrity
-----------------------------------------------

LLVM's ``llvm-ar`` packages object files, while ``llvm-ranlib`` builds
the archive symbol index consumed by the linker. A normal successful archive
command does **not** establish that all members use the same Mach-O ABI.
Unlike ``llvm-lipo``'s fat-archive slice validation, a regular archive
may contain both plain ``arm64`` and ``arm64e`` members. Such mixing
is not automatically a defect in ``llvm-ar``; it is a reason to validate
the actual members before admitting an ARM64e QEMU static library.

The WHP regression compiles two signed ARM64e Mach-O objects without an
Apple SDK. It builds Darwin-format archives using the selected LLVM
``llvm-ar`` and ``llvm-ranlib``, then checks that member bytes are
unchanged, the CPU type is ARM64, the subtype is the versioned
``0x80000002`` (ARM64e pointer-authentication ABI version 0), and the
BSD ``__.SYMDEF`` symbol index points to the actual defining members.
It checks deterministic output, updates a member and reindexes it, then
deliberately mixes an ``arm64`` member and corrupts an index offset to
ensure both faults are rejected by the independent reader.

Run the SDK-independent test with the pinned toolchain::

  python3 scripts/tests/test-llvm-ar-arm64e.py \
    --clang "$NATIVE_LLVM_DIR/bin/clang" \
    --ar "$NATIVE_LLVM_DIR/bin/llvm-ar" \
    --ranlib "$NATIVE_LLVM_DIR/bin/llvm-ranlib"

On a real Mac, add ``--sdkroot "$SDKROOT"``,
``--deployment-target "$MACOSX_DEPLOYMENT_TARGET"`` and
``--objdump "$NATIVE_LLVM_DIR/bin/llvm-objdump"``. The extended check
links an executable with **Apple ld** and confirms that both indexed
members are extracted and the final Mach-O subtype survives. It deliberately
does not execute the image: runtime eligibility for third-party ARM64e
binaries is a separate macOS policy issue.

The native macOS workflow now runs this test with the **installed pinned
LLVM tools** and audits the actual pinned libisofs ``arm64e`` static
archive using ``--audit-archive PATH``. That check reads real Mach-O
members and confirms indexed symbols resolve to the correct members, rather
than relying only on the ``lipo -archs`` label. It is an archive integrity
check, not permission to combine ARM64e with ARM64, change PAC semantics,
or select Mach-O LLD before its authenticated-link gate passes.

ARM64e Mach-O LLD authenticated import linking
----------------------------------------------

The pinned ``ld64.lld`` implements ARM64e authenticated-pointer
relocations and USERLAND24 chained fixups, but its ability to *link* is
distinct from Apple's willingness to execute a third-party arm64e image.
WHP therefore keeps Apple ld as the native arm64e default and admits
Mach-O LLD only with explicit ``WHP_ARM64E_USE_LLD=1`` and a real
link-only PAC capability test. Do not automatically promote LLD based on
its version or the existence of ``ld64.lld`` alone.

The shared ``scripts/whp-build/arm64e-lld-probe.bash`` previously
validated four authenticated **local rebases** and authenticated indirect
call generation. That does not test dyld's imported-symbol binding path.
The probe now builds an ARM64e producer dylib plus a consumer dylib
containing four local authenticated rebases and four authenticated
**imported binds**, covering IA, IB, DA and DB keys, 16-bit discriminator
values and address-diversity bits. It checks the imported symbol and the
USERLAND24 chained-pointer format, then runs the pinned LLVM fork's
existing ``lld/test/MachO/Inputs/arm64e-auth-metadata.py`` decoder
against the *linked Mach-O bytes*, including eight-byte chain-next
fields and bind/rebase markers. It also links a branch to the imported
function and disassembles ``__TEXT,__auth_stubs``: the branch must
pass through a ``BRAA x16, x17`` authentication stub rather than
an unsigned ARM64 ``BR``. A failing or missing decoder, or an
unauthenticated import stub, prevents LLD selection; Apple ld remains
available for the default host build.
No ABI version, code-signing policy or executable-runtime acceptance is
inferred from a successful link-only test.

The macOS CI workflow now includes a portable source/Bash-syntax guard::

  python3 scripts/tests/test-arm64e-lld-binding-policy.py

After building the pinned native compiler, that workflow also runs the
real ARM64e LLD probe as a **nonfatal capability diagnostic**. It does
not silently turn on ``WHP_ARM64E_USE_LLD``. Explicit LLD selection in
``macos-arch-policy.bash`` still requires the same strict test to pass.
A diagnostic failure cannot mark a working Apple-linked Clang toolchain
incomplete. The macOS CI marker check also distinguishes the current
macOS default ``clang;lld;lldb`` project list from a deliberately
LLDB-disabled ``clang;lld`` build.

Native LLVM installation versus linker capability
-------------------------------------------------

The managed native LLVM bootstrap first completes the ``distribution`` build
and then installs it under a temporary ``DESTDIR``. Only after Clang and
Clang++ compile host-ABI objects and the installed tools pass usability checks
does WHP replace the live toolchain. A failure never publishes that partial
installation; the existing LLVM CMake/Ninja tree remains available for an
incremental retry.

The old usability check mixed two different linker contracts: native macOS
runtime validation and the optional Mach-O LLD capability. On ``arm64``
(not ``arm64e``) it forced ``-fuse-ld=lld`` for both UBSan and Objective-C
Cocoa framework links. That could reject an otherwise working native Clang
and compiler-rt distribution when the fork's ``ld64.lld`` could not yet
handle a newer Apple SDK. The bootstrap already had an independent probe
before selecting Mach-O LLD for the LLVM build; the usability check must not
silently override that choice.

The required native macOS UBSan and Cocoa probes now use the installed Clang
driver's normal **Apple linker** selection. They still require the correct
macOS SDK, architecture, deployment target, installed ``libLTO.dylib``,
compiler-rt runtime linking and libobjc/framework resolution. The ``ld64.lld``
executable must still exist; explicit LLD use retains the independent
capability checks. Windows cross-object/link validation, backend coverage,
and the opt-in ASan check are unchanged. This fixes the overly strict
*linker selection*, not the completeness rules for required artifacts.

Missing required executables, Windows COFF/MinGW probe failures, and UBSan
link failures now report which check failed rather than only the final
``staged WHP native LLVM toolchain is incomplete`` message. UBSan compiler
diagnostics are preserved in the failure output, while temporary probe files
are deleted. A genuine failed UBSan or Cocoa test is still fatal.

The focused regression extracts the real bootstrap usability function and
runs it against a deliberately constrained fake Clang that rejects
``-fuse-ld=lld``; it covers both ``arm64`` and ``arm64e``, missing
required tools, and a failed UBSan link::

  python3 scripts/tests/test-native-llvm-install-validation.py

This fixture cannot establish that a full real Apple SDK/LLD toolchain builds.
The normal native macOS CI path remains the integration verification gate.

Avoiding repeated LLVM CMake configuration
-------------------------------------------

Native LLVM retains its generated Ninja build tree between interrupted builds,
source updates and failed installation checks. If CMake was successfully
configured previously, the bootstrap now compares the current CMake executable
and version, compiler versions, configuration arguments and relevant discovery
environment against a marker stored alongside ``CMakeCache.txt`` and
``build.ninja``. When these match, it avoids an extra CMake configuration
pass. Ninja still regenerates its build graph automatically when tracked CMake
inputs change, including changes to LLVM's ``CMakeLists.txt`` files.

The marker is not the installed-compiler ABI marker: neither an incomplete
installation nor an interrupted build invalidates reusable object files. A
failed configure removes the reuse marker, and an explicit
``NATIVE_LLVM_FORCE_REBUILD=1`` retains the existing forced clean/reconfigure
behavior. When discovery inputs change outside the recorded policy, removing
``.whp-native-llvm-cmake-config`` from the LLVM build directory forces the
next incremental invocation to configure again without cleaning its objects.

The ``distribution`` build and staged ``install-distribution`` remain
separate on purpose. Compilation failures must not trigger installation, and
the staged toolchain still passes its ABI/runtime checks before publication.
Skipping redundant CMake configuration saves a potential setup pass, not the
underlying LLVM C++ compilation or linking work.

Compiler-rt iPhoneOS SDK detection in native macOS builds
---------------------------------------------------------

The WHP native LLVM bootstrap builds ``compiler-rt`` for **macOS**, with
``compiler-rt`` builtins and runtimes configured as separate CMake projects.
The macOS host compiler and sanitizer libraries do not require iPhoneOS,
iPhoneSimulator, watchOS, tvOS or xrOS SDKs. Lack of an iPhoneOS SDK is
therefore not itself a build defect.

Compiler-rt's ``cmake/base-config-ix.cmake`` previously called
``find_darwin_sdk_dir(HAS_IOS_SDK "iphoneos")`` and emitted
``iOS SDK not found! Building compiler-rt without iOS support.`` even
when ``COMPILER_RT_ENABLE_IOS=OFF`` had been explicitly requested.
The fork now skips that SDK discovery and warning when iOS is disabled.
Unspecified iOS support retains automatic SDK detection; an explicit
iOS-enabled cross-target build retains its previous probe behavior.

The native macOS bootstrap sends ``-DCOMPILER_RT_ENABLE_IOS=OFF`` through
**both** ``BUILTINS_CMAKE_ARGS`` and ``RUNTIMES_CMAKE_ARGS``. The
runtime-only flags still enable macOS sanitizers, libFuzzer and profiling.
The selected ``MacOSX.sdk``, ``CMAKE_OSX_ARCHITECTURES``, deployment
target and ARM64e policy are unchanged. The updated LLVM gitlink contains
the fork fix; existing CMake/Ninja graphs remain incremental.

Run the focused policy test from an initialized LLVM submodule::

  python3 toolchains/llvm-project/compiler-rt/cmake/tests/ios-sdk-option-isolation.py

It executes the production CMake option block with a mocked SDK locator
for six explicit/automatic iOS configurations, including when the iPhoneOS
SDK is missing. Native Apple Silicon runtime compilation and published
sanitizer tests still require a real macOS SDK and build environment.

LLVM CPPFLAGS and cached global compiler flags
---------------------------------------------

The native LLVM bootstrap deliberately unsets inherited ``CPPFLAGS``,
``CFLAGS``, and ``CXXFLAGS``. CMake does not automatically consume
``CPPFLAGS`` as a compilation flag; setting it in the outer QEMU shell
therefore does not speed up the LLVM compiler build. The native Release
profile already passes ``-DNDEBUG`` explicitly in both C and C++ flags.

CMake does, however, retain global ``CMAKE_C_FLAGS`` and
``CMAKE_CXX_FLAGS`` from older configurations. The bootstrap clears
these cached fields explicitly and keeps all native LLVM C/C++ optimization
flags in its controlled Release profile. This prevents stale QEMU or host
preprocessor definitions and instrumentation switches from changing ABI
assumptions on later incremental compilations.

The earlier C/C++ cleanup invalidated the old schema-12 LLVM installation
marker. The current installation marker is schema 14; its explicit flag
identity determines whether an existing staged toolchain remains reusable.
An identity change does not by itself delete the persistent LLVM Ninja tree.
These are correctness and reproducibility repairs, not demonstrated
CPPFLAGS-based compilation speedups.

LLVM x86 SSE4.2 and non-x86 assembler isolation
-----------------------------------------------

The WHP LLVM host toolchain enables ``AArch64;X86;PowerPC`` backends
together. Backend selection is **not** a license to pass x86-only instruction
flags into the host compiler on Apple Silicon or PowerPC. QEMU's own
``-msse4.2`` Meson setting is scoped to an ``x86_64`` **host**
and does not govern LLVM's embedded compilation targets.

The native LLVM bootstrap already clears C/C++ flag caches and uses
``-O2 -DNDEBUG`` for Release. It now also unsets inherited ``ASMFLAGS``
and explicitly empties ``CMAKE_ASM_FLAGS`` and
``CMAKE_ASM_FLAGS_RELEASE`` on every CMake configure. This closes a
separate stale-assembly-cache path through which old ``-msse4.2``
flags could enter a non-x86 LLVM build graph. The new values are included
in the installed-toolchain marker and CMake configuration identity, so a
changed policy reconfigures the existing tree without a general reset.

Run the targeted check::

  python3 scripts/tests/test-native-llvm-isa-boundary.py

The test checks the QEMU host-only guard and LLVM bootstrap boundaries,
then (when CMake and Ninja are installed) reproduces a poisoned assembly
CMake cache and verifies that the generated Ninja commands lose
``-msse4.2`` after reset. It does not claim the previously installed
WHP LLVM compiler was actually contaminated. A native arm64e build and
compile-command audit remain required to confirm the live generated graph.

LLDB incomplete Clang expression ownership on macOS
--------------------------------------------------

``NATIVE_LLVM_ENABLE_LLDB=auto`` enables LLDB for the managed macOS native
LLVM host build. Apple's libc++ diagnoses a C++ ``std::unique_ptr<T>``
deletion when the owning constructor, destructor or ``reset()`` is
instantiated in a translation unit where ``T`` is only forward-declared.
An error mentioning ``sizeof(_Tp) >= 0`` and
``lldb_private::ClangExpressionDeclMap`` is this source-level
incomplete-type issue, **not** evidence that the macOS SDK or Apple ABI is
wrong. Do not disable the static assertion or alter SDK headers.

The pinned LLVM fork already moved the ``ClangUserExpressionHelper`` owner
lifetime out of the header. The second owner,
``ClangUtilityFunctionHelper``, also held a
``unique_ptr<ClangExpressionDeclMap>`` with an inline ``reset()`` and an
implicit destructor. Both lifetime operations, and the constructor, now
reside in ``ClangUtilityFunction.cpp`` after the complete declaration-map
include. The adjacent ``ClangFunctionCallerHelper`` similarly owns a
forward-declared ``ASTStructExtractor``; its constructor and destructor
are now defined in ``ClangFunctionCaller.cpp``, which includes that type.
These are ordinary out-of-line C++ definitions, with no new macOS-only
branches or layout changes.

A separate diagnostic, ``unknown type name 'ClangPersistentVariables'``,
came from ``ClangUserExpression.h`` storing a
``ClangPersistentVariables *m_clang_state`` pointer without declaring the
plugin-local class. The LLVM fork now forward-declares that type alongside
``ClangExpressionDeclMap`` and ``ClangExpressionParser`` in
``namespace lldb_private``. Only ``ClangUserExpression.cpp`` needs to
include the complete ``ClangPersistentVariables.h`` definition for casts
and member calls; adding the full header to the public expression header
would increase dependencies and obscure the actual include contract. This
repair does not change the member layout or the LLVM/macOS ABI.

Run the fork's quick source contract check after initializing the submodule::

  python3 toolchains/llvm-project/lldb/scripts/test-declmap-incomplete-lifetime.py

The native macOS bootstrap performs the actual Clang/LLDB compile when LLDB
is enabled; the upstream fork also has an opt-in native macOS LLDB smoke
workflow. A source-contract check is not proof that Apple's complete SDK
build passes. Preserve the incremental Ninja tree on failure and examine the
first compiler instantiation stack to distinguish a remaining incomplete
owner from a stale object, header or CMake configuration.

ARM64E_X1 Mach-O subtype and Apple SDK macro collision
-----------------------------------------------------

The Apple Mach-O SDK uses ``#define CPU_SUBTYPE_ARM64E_X1
((cpu_subtype_t) 12)`` while LLVM models the same subtype as the
``CPU_SUBTYPE_ARM64E_X1 = 12`` enum member in
``llvm/BinaryFormat/MachO.h``. Both denote **the same numeric subtype**;
the SDK's ``cpu_subtype_t`` cast is not a conflicting architecture code.
However, including ``mach/machine.h`` first can cause the preprocessor
to replace LLVM's enum member name with a cast expression, breaking C++
compilation.

LLDB's ``lldb/Host/SafeMachO.h`` already removes colliding SDK CPU
subtype macros before including LLVM's Mach-O header. The pinned LLVM fork
extends that existing cleanup to ``CPU_SUBTYPE_ARM64E_X1`` instead of
changing the SDK, renaming the LLVM enum, or altering the Mach-O binary
format. The rule is to include required Darwin system headers **before**
``SafeMachO.h`` when a translation unit needs both; the wrapper does not
promise safety if an Apple header redefines a macro afterward.

The fast portable regression injects the typed macro, demonstrates the raw
enum collision, and verifies the same source compiles through the real
``SafeMachO.h`` wrapper using a minimal header fixture::

  python3 toolchains/llvm-project/lldb/scripts/test-safemacho-arm64e-x1.py

The opt-in LLVM fork macOS host smoke also compiles the **real** Apple SDK
``mach/machine.h`` and LLVM ``MachO.h`` after the SafeMachO wrapper,
simulating the X1 macro on SDKs that do not yet provide it. These tests
check header compatibility, not arm64e.x1 instruction emission or pointer
authentication. They do not authorize changing WHP's selected macOS host
ABI or the LLVM target triple.

Clang++ flag validation on Apple Silicon
----------------------------------------

Native LLVM bootstrap C++ flags are intentionally separate from QEMU's
host-object ``CXXFLAGS``. The LLVM Release profile uses ``-O2 -DNDEBUG``
for both C and C++; it does not add CPU-native tuning by default. This keeps
the installed compiler reproducible across machines with the same host
architecture without assuming they use the same CPU microarchitecture.
The bootstrap still tests the requested Mach-O ``-arch``, ``-isysroot``,
and ``-mmacosx-version-min`` together for C and C++ when admitting an
Apple ``arm64e`` build.

``NATIVE_LLVM_CXX_STANDARD=26`` accepts the compiler's ``-std=c++26``
or historical ``-std=c++2c`` spelling only when the ``__cplusplus``
macro reports the corresponding language mode. It does not imply complete
implementation of all C++26 library or language features. CMake is still
configured with ``CMAKE_CXX_STANDARD=26`` and
``CMAKE_CXX_STANDARD_REQUIRED=ON``.

QEMU's ``QEMU_HOST_CPU_TUNING=native`` mode deliberately uses
``-mtune=<detected CPU>`` on AArch64 rather than ``-mcpu=native``.
Its C, C++, and Objective-C probes now consume the managed Mach-O target
arguments, rejecting malformed architecture/SDK tuples. The optional Mach-O
LLD ``--read-workers`` link flag is admitted only if **both** Clang and
Clang++ accept it. These are build-policy checks, not instructions to add
ARMv9.2-A or ARM64e-specific ISA extensions globally.

Run the isolated regression checks using::

  python3 scripts/tests/test-native-llvm-cxx-flag-probes.py
  python3 scripts/tests/test-host-cpu-tuning.py
  bash scripts/tests/test-host-cpu-tuning.bash
  python3 scripts/tests/test-macos-lld-clangxx-flags.py

Apple dyld: ARM64e rebases, binds and runpaths
------------------------------------------------

Apple's open-source dyld separates rebases within an image from binds to
symbols in other Mach-O images. Authenticated ARM64e chained pointers
add PAC key, diversity and address-diversity metadata. The WHP Mach-O LLD
probe checks the four PAC keys in authenticated **rebases**, while the
existing LLD fixture validates chained authenticated binds. Neither
metadata check by itself proves that dyld accepts and executes a linked
process on the selected macOS release.

On macOS, run the native load/link test::

  bash scripts/tests/test-darwin-dyld-arm64e.bash arm64 apple
  bash scripts/tests/test-darwin-dyld-arm64e.bash arm64e apple

After explicitly building a compatible Mach-O LLD, its own runtime lane is::

  WHP_DYLD_LLD_DIR=/absolute/path/to/llvm/bin \
    bash scripts/tests/test-darwin-dyld-arm64e.bash arm64e lld

The test builds a separate dynamic library with a global function pointer,
links its client through ``@rpath``, then builds a QEMU-style late-loaded
module with a *different* private dylib dependency, reachable only through
the module's ``@loader_path/../plugin-private/lib`` runpath. Reusing
the executable's already loaded dylib would give a false positive. It
verifies ``LC_RPATH``,
``LC_LOAD_DYLIB`` (via ``otool -L``) and ``LC_ID_DYLIB``, then relocates
the executable and both libraries to a path containing spaces. With
``DYLD_LIBRARY_PATH`` and ``DYLD_FALLBACK_LIBRARY_PATH`` unset,
dyld must still resolve the direct call, imported pointer, both
``dlopen`` calls, ``dlsym`` and their indirect calls. A non-zero result
is an unresolved runtime failure, not a reason to silently accept the
earlier static LLD probe.

The final QEMU macOS build adapter no longer reintroduces the private SDL3
directory through ``DYLD_FALLBACK_LIBRARY_PATH`` after sanitation. QEMU
and its modules already receive ``@loader_path/deps/sdl3/lib`` and
``@loader_path/../deps/sdl3/lib`` runpaths, and the SDL3 dylib uses an
``@rpath`` install name. Keep the bootstrap-only host-library environment
separate; a binary that works only with a DYLD_* override is not a verified
relocatable QEMU binary.

References: Apple dyld ``include/mach-o/fixup-chains.h`` and
``dyld/Loader.cpp``, and Apple's *Run-Path Dependent Libraries* and
*Embedding nonstandard code structures in a bundle* documentation.

Apple ld64 flag compatibility: chained fixups
---------------------------------------------

Apple's public ``ld64`` source distinguishes ``-fixup_chains`` (force on)
from ``-no_fixup_chains`` (force off), with force-on taking precedence if
both appear, regardless of argument order. Apple's
``ld::supportsChainedFixups`` target-version table sets the default macOS
boundary at **12.0**. The pinned WHP ``ld64.lld`` used to assume macOS
13.0 and interpret conflicting options using the last flag. Both
differences have been corrected in the LLVM fork.

This change affects ordinary ARM64's default dynamic-linker load commands.
It does **not** relax the ARM64e requirement for PAC-compatible chained
fixups: ``-no_fixup_chains`` alone remains an error on ARM64e; an explicit
``-fixup_chains`` overrides the negative flag even when it appeared first.
A macOS 11 ARM64 build defaults to classic ``LC_DYLD_INFO_ONLY``; an
ordinary macOS 12 ARM64 dylib defaults to ``LC_DYLD_CHAINED_FIXUPS``.

On a macOS host with the lean LLD test toolchain, compare Apple ``ld``
with the pinned ``ld64.lld`` using the exact same ARM64 object file::

  bash scripts/tests/test-macos-ld64-fixup-flags.bash \
    /path/to/llvm/bin/ld64.lld /path/to/llvm/bin/llvm-objdump

The comparison exercises macOS 11/12 default behavior, both explicit
flags, and both conflicting-flag orders; it is wired into the existing
``lld-arm64e-auth.yml`` CI lane, which builds LLD once. The upstream
LLD Lit tests separately guard ARM64e mandatory PAC fixups.

Not all Apple ld flags are equivalent to LLD merely because an option
exists in ``Options.td``. For example, Apple documents
``-fixup_chains_section_vm`` for static/preload outputs; treating it as
an alias for dynamic dylib chained fixups would be incorrect. Keep that
special format outside this change until a verified writer and tests exist.
Likewise, do not claim ``-mac_public_arm64e`` compatibility based solely
on compiler-rt probing the flag. The test validates linker metadata,
not a fully successful dyld load or code-signing contract.

Sources: Apple ``ld64/src/ld/Options.cpp``,
``ld64/src/ld/ld.hpp``, and Apple's ``ld(1)`` option reference.

ARM64e LLD development lane
---------------------------

The pinned LLVM Mach-O LLD implements authenticated ARM64e relocations and
chained fixups. The ordinary QEMU ARM64e build still uses Apple ``ld``
until the full C/C++/Objective-C/TCG runtime path is verified. To select
LLD *explicitly* for a non-ASan ARM64e experiment::

  WHP_MACOS_ARCH=arm64e WHP_ARM64E_USE_LLD=1 \
    BOOTSTRAP_NATIVE_LLVM=1 ./build.sh qemu-system-ppc

This is a developer option, **not** an unconditional ARM64e default. It validates
``-arch arm64e`` with Clang, the actual Clang and Clang++ linker selection,
and an authenticated ``ARM64_RELOC_AUTHENTICATED_POINTER`` link through the
installed ``ld64.lld``, checking its chained-fixup pointer format using
``llvm-objdump``. A trivial ``main()`` link is not sufficient. The
native LLVM bootstrap can also reuse a previously installed ARM64e-capable
LLD when this option is enabled; otherwise it preserves Apple ``ld``.

An explicit ARM64e LLD request requires the managed native LLVM compiler
and cannot be combined with ``QEMU_ASAN=1`` or ``QEMU_ASAN=y``.
A failed capability probe must stop the requested QEMU host link rather
than silently substituting Apple ``ld``. The shared probe only links an
ARM64e dylib; it does not prove runtime compatibility or TCG correctness.
The separate macOS CI workflow ``lld-arm64e-auth.yml`` runs a focused
native link check before this lane can be promoted.

Profile-guided optimization (PGO)
---------------------------------

``QEMU_HOST_PGO=off|generate|use`` is an opt-in host-only setting exposed
through menuconfig and both WHP build adapters. Its default is ``off``;
the adapters pass Meson's ``-Db_pgo=<mode>`` to the QEMU build. It does
not instrument OpenBIOS, SeaBIOS, LLVM's native bootstrap, or other
out-of-tree toolchain preparation. Use a stable compiler, architecture,
optimization level and LTO configuration across both PGO passes.

For LLVM/Clang, ``QEMU_HOST_PGO=use`` now implies ``generate``
when there is neither a nonempty ``default.profdata`` nor any nonempty
``pgo-raw/*.profraw``. The public ``build.sh`` automatically starts a
``QEMU_HOST_PGO=generate`` build of the same requested targets, without
running the normal test suites or installation during the intermediate pass.
The direct portable Python core performs the same generate pass in process,
without repeating its build-environment preparation. Both preserve the
existing build tree and any prior profile files.

**Generation is not training.** The instrumented QEMU must execute
representative guest workloads before ``use`` is meaningful. To make all
three stages automatic, set ``QEMU_PGO_TRAIN_SCRIPT`` to an **executable
script** that boots/exercises the generated QEMU binary. Relative script
paths resolve from the source checkout. The script receives the requested
targets as arguments and the following environment variables:

- ``WHP_PGO_BUILD_DIR``: the validated build directory holding the
  instrumented emulators.
- ``LLVM_PROFILE_FILE``: ``$BUILD_DIR/pgo-raw/%m-%p.profraw``, using
  LLVM module/process substitutions to keep raw profile files distinct.

If a training script is configured, ``use`` generates, trains, verifies
that nonempty profiles exist, merges them with the selected compiler's
``llvm-profdata``, and runs the final ``b_pgo=use`` build. If no script
is configured, the first ``use`` invocation builds the instrumented
emulator but **stops with clear instructions** rather than pretending a
version check or an untrained boot is representative. Run that emulator on
the normal guest workloads with ``LLVM_PROFILE_FILE`` set, exit cleanly
to flush the raw data, then repeat ``QEMU_HOST_PGO=use``. The next
invocation will skip generation and use the collected profiles.

On either path, existing indexed profiles are reused. Newer nonempty raw
profiles are merged automatically into ``default.profdata``. A failed
merge preserves an older indexed profile and stops the build. Clang, host
ABI, LTO and source revision compatibility still matter; an incompatible
profile is not repaired by manufacturing artificial training traffic.
Meson itself does not merge Clang's raw profiles; see
``scripts/whp-build/pgo-profile.py`` for the validated merge.


Use an identical ``off`` baseline for benchmarks (same host ABI, compiler,
LTO, optimization level, guest image, QEMU options and test machine), and
compare repeated **guest execution** times, not instrumented training times.
Keep raw profiles and merged profile data in the owned build directory;
do not commit generated profile files to the source tree. Clang's indexed
profile format is distinct from GCC's ``.gcda``/profile-use workflow;
the steps above are for LLVM/Clang. PGO is experimental until native macOS
link/runtime and representative TCG speedup tests succeed.

LLD-specific LDFLAGS
--------------------

The macOS wrapper keeps Apple ``ld`` and LLVM ``ld64.lld`` flag policies
separate. ``-Wl,-dead_strip`` is supported by both. The Apple-style
``-Wl,-O2`` is not automatically added when the managed Mach-O LLD linker
is active: LLD's ``-O`` option is documented as an output-size option,
not the same Apple linker optimization contract.

``-Wl,--read-workers=N`` is an optional Mach-O LLD input-prefetch
extension. The wrapper first checks that the **selected Clang and linker**
can complete an actual link with it. If the default job-budget value is
unsupported, it omits the flag with a warning; it never forwards that
argument to Apple ``ld``. An explicitly requested unsupported positive
``NATIVE_LLVM_READ_WORKERS`` fails with an error rather than being silently
ignored. Setting ``NATIVE_LLVM_READ_WORKERS=0`` omits the option.

The WHP LLVM fork's Mach-O ``ld64.lld`` now recognizes the compatibility
spellings ``-threads`` (retain the default parallel linking policy) and
``-threads=N`` (alias for ``--threads=N``). The LLVM option parser uses
the existing positive-integer validation and ThinLTO default for the numeric
alias; this is not a second threading implementation.

The WHP Clang Darwin driver forwards ``-flto-jobs=N`` to Mach-O LLD as
``--threads=N``, rather than incorrectly passing ``-threads=N`` through
the linker's ``-mllvm`` backend option. It also recognizes raw
``-threads``, ``--threads``, and their ``=N`` variants for LLD links.
Apple ``ld`` retains its existing LTO backend forwarding.

The macOS QEMU wrapper accepts both raw and ``-Wl,`` spellings, normalizing
raw forms to ``-Wl,--threads[=N]`` before probing the selected native LLD.
Older linker builds and Apple ``ld`` are rejected by a link probe;
malformed ``-Wl,-threads,N`` and ``-Xlinker -threads`` are not accepted.
Use the build's established job budget rather than assuming that bare
``-threads`` limits concurrency. The option is distinct from input prefetch
``--read-workers=N`` and from Meson's ``b_lto_threads`` setting.

The native LLVM bootstrap independently probes whether the previously
installed ``ld64.lld`` can link before trying the optional worker
extension. A missing extension must not force an otherwise usable linker
back to Apple ``ld``. These rules protect both the QEMU host link and
the LLVM bootstrap; they do not imply that all linker arguments are
interchangeable between ELF ``ld.lld`` and Mach-O ``ld64.lld``.

Cocoa multi-monitor and multi-head windows
------------------------------------

The native Cocoa backend now opens a separate ``NSWindow`` for each
additional graphical QEMU console present at display initialization.
Each head has its own ``DisplayChangeListener``, keyboard state, Cocoa view,
Metal rendering state (when available), and windowed/fullscreen lifecycle.
The original window remains the primary display; text consoles remain in
the existing View menu. Closing an extra window hides that guest head
without stopping the VM, and the Window menu can reopen it.

Physical macOS monitors and guest graphics heads are separate concepts.
``NSScreen screens`` provides host display placement, not extra guest
graphics hardware. When two or more physical monitors are connected, the
additional graphical windows start on other host displays. Additional
guest heads still require hardware exposing multiple QEMU consoles (for
example a suitable multi-output guest graphics device). With one physical
monitor, multiple guest windows share the host desktop.

Monitor movements and resize callbacks update the active head's host
screen geometry and refresh metadata. A disappearing ``NSScreen`` does not
make the UI dereference a null screen. Guest-head creation after the Cocoa
backend has initialized, automatic guest-desktop positioning, and the
behavior of multiple simultaneous fullscreen Spaces require separate
native macOS runtime validation. This is *not* a claim that a single-head
virtual graphics card becomes a multi-head card.

Dynamic QEMU modules
--------------------

``QEMU_HOST_MODULES`` controls QEMU's existing loadable-module layer. Its
default is ``auto``; on macOS WHP resolves that to ``--enable-modules`` so
optional backends and devices that QEMU already marks as module-safe are emitted
as Mach-O ``.dylib`` modules and loaded through GLib/GModule and dyld instead of
being folded into every emulator executable. Explicit ``QEMU_HOST_MODULES=0``
keeps the monolithic behavior, while ``1`` requests modules on any QEMU host
where they are supported.

This policy does not turn QEMU's internal staging archives into public shared
libraries. Core implementation layers such as QOM, TCG, the target library, and
the current Cocoa/AppleGFX Metal path remain linked into the emulator. Existing
module boundaries include host audio backends such as CoreAudio, optional UI and
block backends, USB host/redirect support, and several display devices.

Named emulator builds also request Meson's ``modules`` alias when that target
exists. This is necessary because a targeted ``qemu-system-*`` Ninja build does
not otherwise traverse unrelated build-by-default module targets. The normal
build-tree ``qemu-bundle`` supplies the same relocated module layout used before
installation.

Useful overrides
----------------

``MACOS_ALLOW_ROSETTA``
  Permit an x86_64 process translated on Apple Silicon.

``MACOS_ALLOW_MIXED_HOMEBREW``
  Permit a nonstandard Homebrew layout.

``MACOS_ALLOW_INHERITED_SEARCH_PATHS``
  Preserve externally supplied compiler/library search paths intentionally.

``MACOS_AUTO_CLEAN``
  Control whether a changed macOS build identity recreates the owned QEMU
  build tree automatically.

``MACOS_VERIFY_TOOLCHAIN``
  Enable compiler and Mach-O identity probes. It defaults to ``1``.

``MACOS_ALLOW_NONCLANG``
  Permit an explicitly selected non-Clang QEMU C/C++ compiler pair after the
  same architecture and link checks.

``MACOS_ALLOW_COMPILER_CONFIG``
  Permit an automatically loaded Clang configuration file when intentional.

``QEMU_HOST_LTO``
  Enable or disable QEMU host LTO without leaking the policy into firmware.

``QEMU_HOST_LTO_MODE``
  Select ``auto``, ``thin``, or ``full`` through menuconfig. Defaults to
  the original host policy; explicit modes require LTO to be enabled.

``QEMU_HOST_MODULES``
  Select dynamic QEMU modules. ``auto`` enables them on macOS, ``1`` forces
  them on supported hosts, and ``0`` keeps module-capable code built in.

``CC``, ``CXX``, ``OBJC``
  QEMU host compiler roles.

``CC_FOR_BUILD``, ``CXX_FOR_BUILD``, ``STRIP_FOR_BUILD``
  Build-machine tool roles used by helper and firmware stages.

``SDKROOT``, ``DEVELOPER_DIR``, ``MACOSX_DEPLOYMENT_TARGET``
  Apple SDK and deployment policy.

Diagnostics
-----------

Compiler identity is recorded in ``.whp-macos-toolchain`` and LTO capability in
``.whp-macos-lto``. Both signatures participate in the main WHP configuration
stamp. When a macOS build fails, classify the first divergence as SDK,
architecture, compiler, dependency search, linker/LTO, QEMU configuration, or
firmware/toolchain before changing unrelated build variables.
