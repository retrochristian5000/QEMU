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

Replace the SDK/deployment target with those of the actual build. On
``arm64e``, omit ``--use-lld`` while the WHP profile selects Apple
``ld`` for authenticated relocations. The probe does not claim to repair
the missing symbol; its output identifies whether the next code change
belongs in Clang instrumentation, compiler-rt distribution, or Mach-O LLD.

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
