macOS build hygiene
===================

The macOS wrapper treats the compiler, SDK, package search path, and build
cache as one build identity.  This prevents a QEMU tree configured for one
Xcode, architecture, or compiler from being reused silently with another.

Environment isolation
---------------------

By default, ``scripts/macos-builder.sh`` removes inherited variables that can
redirect compiler or package searches outside the selected Apple SDK and the
native Homebrew prefix.  The removed set includes the ``CPATH`` family,
``COMPILER_PATH``, ``GCC_EXEC_PREFIX``, ``LIBRARY_PATH``, ``DYLD_*`` injection
paths, CMake search paths, ``PKG_CONFIG_*`` overrides, ``ACLOCAL_PATH``, and
``ARCHFLAGS``.

The wrapper also removes the opposite-architecture Homebrew ``bin`` and
``sbin`` entries from ``PATH``.  An arm64 process uses ``/opt/homebrew``; an
x86_64 process uses ``/usr/local``.  This check is based on the running process,
not merely the physical machine, so a Rosetta build cannot accidentally select
native arm64 tools.

Set ``MACOS_ALLOW_INHERITED_SEARCH_PATHS=1`` only when external search paths
are intentional.  Set ``MACOS_ALLOW_MIXED_HOMEBREW=1`` only for a custom
Homebrew layout or an explicitly mixed-architecture experiment.  Both choices
become part of the build identity.

Clean reconfiguration
---------------------

The wrapper writes ``.whp-macos-build-identity`` in the QEMU build directory.
The identity records:

* process and requested host architecture;
* Xcode developer directory, SDK path and SDK version;
* deployment target;
* C, C++, Objective-C, and build-machine compiler signatures;
* compile, preprocessor, and linker flags;
* LTO selection;
* Homebrew and package-discovery policy; and
* configure shell.

When that identity changes, the wrapper removes and recreates the QEMU build
directory before configuration.  Meson does not promise that an existing build
tree can safely change compiler, SDK, or target ABI in place.  Automatic
cleaning is enabled by default.  Set ``MACOS_AUTO_CLEAN=0`` to turn an identity
change into a diagnostic instead of deleting the owned build tree.

The wrapper only removes a directory carrying a WHP owner record or a matching
legacy ``.whp-config``.  It refuses to clean an unrelated or foreign directory.
Unsafe values such as the source directory, home directory, or filesystem root
are rejected.

Firmware-tool separation
------------------------

OpenBIOS tools and the bootstrapped PowerPC GNU toolchain now live outside the
QEMU Meson directory by default::

  build/whp-firmware-tools-<arch>-apple-darwin

A legacy ``<QEMU build>/firmware-tools`` directory is moved to the new location
on the first hygienic build.  Keeping downloaded source archives and the
PowerPC toolchain outside the disposable QEMU build tree allows compiler or SDK
changes to trigger a truly clean QEMU rebuild without destroying the expensive
firmware bootstrap.

``OPENBIOS_TOOLS_DIR`` may override this location, but it must remain outside
``BUILD_DIR``.  ``POWERPC_TOOLCHAIN_DIR``, ``POWERPC_TOOLCHAIN_WORK_DIR``, and
``POWERPC_TOOLCHAIN_DOWNLOAD_DIR`` continue to support explicit overrides.
