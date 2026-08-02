Clang and GCC roles on macOS
============================

The macOS build uses several compiler roles.  They are related, but they are
not interchangeable environment variables.

Default policy
--------------

The supported default is Apple Clang for:

* QEMU C compilation (``CC``);
* QEMU C++ compilation (``CXX``);
* QEMU Cocoa/Objective-C compilation (``OBJC``); and
* build-machine tools (``CC_FOR_BUILD`` and ``CXX_FOR_BUILD``).

The selected programs come from ``xcrun --sdk macosx --find`` so they match the
active Xcode or Command Line Tools installation.  On macOS, an executable named
``gcc`` is not proof that GNU GCC was selected; Apple's unversioned ``gcc``
entry point normally invokes Apple Clang.  The wrapper identifies compiler
families from their reported version or predefined macros, not from the
executable basename.

``CC`` and ``CXX`` must be selected together and must report the same compiler
family.  A configuration such as ``CC=gcc-14`` with an inherited
``CXX=clang++`` is rejected before QEMU configuration.  It otherwise creates a
mixed ABI, option, linker, and LTO policy whose failure may appear much later.

Objective-C remains Apple Clang
-------------------------------

The Cocoa frontend is kept on Apple Clang even during an experimental GNU GCC
C/C++ build.  This preserves the compiler path tested against the active Apple
SDK and frameworks.  Replacing ``OBJC`` with GNU GCC is not part of the
supported non-Clang escape hatch.

Build-machine tools also remain Apple Clang.  QEMU configure probes, helper
programs, ``toke``, and other programs that execute during the main QEMU build
must not silently change compiler family merely because the QEMU host compiler
changed.

Experimental GNU GCC QEMU host build
------------------------------------

GNU GCC can be tested explicitly by setting a matching compiler pair and the
non-Clang opt-in::

  CC=/path/to/gcc-<major> \
  CXX=/path/to/g++-<major> \
  MACOS_ALLOW_NONCLANG=1 \
  sh scripts/macos-builder.sh

This is an experimental path.  It does not change ``OBJC``,
``CC_FOR_BUILD``, or ``CXX_FOR_BUILD`` from Apple Clang.

The wrapper forces ``QEMU_HOST_LTO=0`` for this path.  Clang LTO and GCC LTO
use different linker-plugin and archive-tool contracts.  Reusing the native
Apple Silicon Clang-LTO default with GNU GCC could combine GCC LTO objects with
Apple or LLVM ``ar``, ``nm``, and linker assumptions.  GCC host LTO should only
be enabled after a separate plugin-aware tool policy and smoke test exist.

PowerPC bootstrap host compiler
-------------------------------

Changing the compiler that builds the GNU PowerPC cross-toolchain is separate
from changing QEMU's host compiler.  QEMU and Cocoa remain on Apple Clang.

When ``scripts/macos-builder.sh`` starts without explicit firmware-host
compiler settings, it searches the active Homebrew GCC prefix and ``PATH`` for
a matching versioned GNU pair, currently ``gcc-16``/``g++-16`` through
``gcc-12``/``g++-12``.  It confirms GNU GCC from predefined compiler macros so
Apple's Clang-backed unversioned ``gcc`` command is not mistaken for GNU GCC.
The selected pair is exported as ``OPENBIOS_HOSTCC`` and
``OPENBIOS_HOSTCXX``.  ``scripts/build-openbios.sh`` then passes the same pair
to the nested binutils and GCC bootstrap.

Explicit settings always override automatic selection::

  OPENBIOS_HOSTCC=/path/to/gcc-<major> \
  OPENBIOS_HOSTCXX=/path/to/g++-<major> \
  sh scripts/macos-builder.sh

The two variables must be supplied together.  If no versioned GNU pair is
available, the integrated build retains the Apple Clang build-machine
compiler rather than changing QEMU's host compiler policy.

For a direct toolchain-only build, use the host-selection wrapper::

  POWERPC_TOOLCHAIN_FORCE_REBUILD=1 \
  bash scripts/bootstrap-powerpc-toolchain-host.sh

The direct wrapper accepts ``POWERPC_TOOLCHAIN_HOST_CC`` and
``POWERPC_TOOLCHAIN_HOST_CXX`` as explicit overrides.  Setting
``POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST=1`` makes the absence of a GNU GCC pair a
fatal error.  Before binutils starts, the wrapper rejects host flags containing
LTO, linker-plugin, or forced-linker selections.  Binutils is built before the
cross GCC exists, so it must not inherit QEMU host LTO or a compiler-specific
plugin contract.

Flag differences
----------------

Both Apple Clang and Darwin-hosted GNU GCC understand the selected SDK and
minimum deployment target, but their architecture and LTO models are not
identical.

Apple Clang
  Integrates directly with the active Apple SDK and supports the wrapper's
  native ``-arch`` policy, Objective-C framework compilation, and LLVM LTO
  checks.

GNU GCC
  Produces the single Darwin architecture for which that GCC was configured.
  Its ``-arch`` option is a compatibility check rather than a mechanism for
  constructing universal binaries.  The wrapper therefore verifies the
  compiler target and generated Mach-O slice instead of assuming that a flag
  can turn an Intel GCC into an Arm compiler or vice versa.

A target-prefixed bare-metal compiler such as ``powerpc-elf-gcc`` or
``arm-none-eabi-gcc`` must never be used as QEMU's macOS host ``CC``.  Apple
SDK flags such as ``-arch arm64`` describe Mach-O host output and do not belong
on a compiler whose output target is ELF firmware.

Failure classification
----------------------

``CC and CXX must be selected as a pair``
  Only one language driver was overridden.  Supply the matching C and C++
  drivers or remove both overrides to use Apple Clang.

``mixed C and C++ compiler families``
  The two drivers identify as different families.  Do not combine Clang and
  GNU GCC in the C/C++ Meson toolchain.

``Cocoa frontend must use Apple Clang``
  ``OBJC`` was changed to a non-Clang compiler.  Restore the ``xcrun`` Clang
  path.

``build-machine tools must use Apple Clang``
  ``CC_FOR_BUILD`` or ``CXX_FOR_BUILD`` was changed globally.  Use the
  OpenBIOS or direct toolchain-bootstrap variables for an isolated GCC-host
  build instead.

``GNU GCC was selected``
  Add ``MACOS_ALLOW_NONCLANG=1`` only when the experimental QEMU-host path is
  intentional.

``PowerPC toolchain host compilers must be set as a pair``
  Only one direct-bootstrap compiler was selected.  Supply both C and C++
  drivers.

``contains an LTO or linker-plugin option``
  A toolchain-host flag would leak a compiler-specific object or linker policy
  into binutils.  Remove it; QEMU host LTO is managed separately by Meson.

Verification
------------

The compiler policy runs before ``builder.sh`` chooses its LTO default.  The
existing macOS compiler verifier then compiles C, C++, Objective-C, and
build-machine probes and checks their Mach-O architecture with ``lipo``.  The
PowerPC bootstrap separately verifies its selected host compiler pair, staged
assembler and linker, and final cross compiler.
