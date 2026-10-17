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

LLVM CPPFLAGS and cached global compiler flags
---------------------------------------------

The native LLVM bootstrap deliberately unsets inherited ``CPPFLAGS``,
``CFLAGS``, and ``CXXFLAGS``. CMake does not automatically consume
``CPPFLAGS`` as a compilation flag; setting it in the outer QEMU shell
therefore does not speed up the LLVM compiler build. The native Release
profile already passes ``-DNDEBUG`` explicitly in both C and C++ flags.

CMake does, however, retain global ``CMAKE_C_FLAGS`` and
``CMAKE_CXX_FLAGS`` from older configurations. The bootstrap now clears
these two cached fields explicitly and keeps all native LLVM optimization
flags in its controlled Release profile. This prevents stale QEMU or host
preprocessor definitions and instrumentation switches from adding work or
changing ABI assumptions on later incremental compilations.

The policy changes the installed LLVM cache marker to schema 13. An older
schema-12 installed compiler will be rebuilt once; its persistent CMake/Ninja
build tree is retained. This is a correctness and reproducibility repair,
not a demonstrated standalone CPPFLAGS-based compilation speedup.

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
