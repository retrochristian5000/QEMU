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
``xcrun`` unless ``DEVELOPER_DIR`` or ``SDKROOT`` is supplied. It defaults
``MACOSX_DEPLOYMENT_TARGET`` to the running macOS major/minor version, rejects a
deployment target newer than the selected SDK, and requires macOS 11.0 or newer
for arm64 builds.

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

When LTO is enabled, ``scripts/verify-macos-lto.sh`` compiles and links a small
multi-file program, verifies the Mach-O architecture, executes the result, and
records the effective linker pipeline. A failed preflight is a compiler/linker
policy problem, not a reason to inject raw LTO flags globally.

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
