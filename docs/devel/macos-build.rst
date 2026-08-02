macOS host builds
=================

The WHP build wrapper supports native Apple Silicon and Intel macOS builds.
It keeps the machine that runs build tools separate from the architecture of
the QEMU executable and from firmware targets such as ``powerpc-elf``.

Machine identities
------------------

A PowerPC system-emulator build on Apple Silicon has three relevant CPU
architectures:

* the macOS build and QEMU host architecture, normally ``arm64``;
* the QEMU emulation target, for example ``ppc-softmmu``;
* the OpenBIOS firmware target, ``powerpc-elf``.

``CC`` and ``CXX`` build QEMU host objects.  ``CC_FOR_BUILD`` and
``CXX_FOR_BUILD`` build executable tools that must run during compilation.
OpenBIOS and the PowerPC cross-toolchain bootstrap use the latter pair for
host utilities and use ``OPENBIOS_CROSS_COMPILE`` for firmware objects.

Native Apple Silicon
--------------------

Run the wrapper from a native Arm shell::

  arch -arm64 ./builder.sh

The default build directory is
``build/whp-ppc-arm64-apple-darwin``.  The wrapper selects the active macOS SDK
with ``xcrun``, enables Cocoa and CoreAudio, uses the Arm Homebrew prefix, and
records the SDK and toolchain identity in ``.whp-config``.

Intel macOS and Rosetta
-----------------------

An Intel Mac uses ``build/whp-ppc-x86_64-apple-darwin`` automatically.
An x86_64 build on Apple Silicon is permitted only when Rosetta use is
explicit::

  arch -x86_64 env MACOS_ALLOW_ROSETTA=1 ./builder.sh

This prevents an accidentally translated shell from silently mixing Arm and
Intel dependencies.  Rosetta builds expect the Intel Homebrew prefix
``/usr/local``; native Arm builds expect ``/opt/homebrew``.

Custom Homebrew layouts
-----------------------

A nonstandard prefix must be deliberate::

  HOMEBREW_PREFIX=/custom/brew \
  MACOS_ALLOW_MIXED_HOMEBREW=1 \
  ./builder.sh

The override disables only the prefix guard.  It does not make libraries of
the wrong Mach-O architecture usable.

Architecture flags
------------------

The wrapper appends the selected architecture to ``CFLAGS``, ``CXXFLAGS``,
``OBJCFLAGS``, and ``LDFLAGS``.  Set ``MACOS_ARCH_FLAGS=0`` only when an
external toolchain file supplies equivalent flags.

Cross-host and universal builds
-------------------------------

``builder.sh`` intentionally rejects a requested ``MACOS_HOST_ARCH`` that
differs from the architecture of the running process.  A true cross-host build
needs a Meson cross file, separate host and build dependency paths, and a rule
for executing build-machine tools.  Running the wrapper under ``arch -arm64``
or ``arch -x86_64`` keeps those roles unambiguous.

Universal binaries should be assembled from two independently configured and
tested build directories.  Do not merge only the main executable: loadable
modules, helper programs, firmware tools, and linked libraries must be checked
for matching slices as well.

Useful overrides
----------------

``MACOS_ALLOW_ROSETTA``
  Permit an x86_64 build process translated on Apple Silicon.

``MACOS_HOST_ARCH``
  Require ``arm64`` or ``x86_64``.  It must match the running process.

``MACOS_ALLOW_MIXED_HOMEBREW``
  Permit a custom Homebrew prefix instead of the architecture-standard prefix.

``CC_FOR_BUILD``, ``CXX_FOR_BUILD``
  Compilers for tools that execute on the build machine.

``CC``, ``CXX``, ``OBJC``
  Compilers for QEMU host code.

``SDKROOT``, ``DEVELOPER_DIR``, ``MACOSX_DEPLOYMENT_TARGET``
  Select the Apple toolchain, SDK, and minimum deployment version.

``PKG_CONFIG_PATH_FOR_BUILD``
  Dependency metadata for build-machine tools.  ``PKG_CONFIG_PATH`` remains
  the dependency path for QEMU host objects.

Diagnostics
-----------

The configuration stamp records the physical architecture, process
architecture, Rosetta state, Apple developer directory, SDK version, host
compilers, build-machine compilers, dependency paths, and firmware toolchain.
Changing any of these values forces QEMU configuration to run again.
