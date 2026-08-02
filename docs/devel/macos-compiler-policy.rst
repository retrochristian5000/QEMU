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
families from their reported version, not from the executable basename.

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
programs, ``toke``, and other programs that execute during the build must not
silently change compiler family merely because the QEMU host compiler changed.

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

Changing the compiler that builds the GNU PowerPC cross-toolchain is a separate
experiment from changing QEMU's host compiler.

For the integrated OpenBIOS build, use matching build-host compilers through::

  OPENBIOS_HOSTCC=/path/to/gcc-<major> \
  OPENBIOS_HOSTCXX=/path/to/g++-<major> \
  sh scripts/macos-builder.sh

For a direct invocation of ``scripts/bootstrap-powerpc-toolchain.sh``, the
corresponding variables are ``TOOLCHAIN_HOST_CC`` and
``TOOLCHAIN_HOST_CXX``.  The QEMU and Cocoa compilers may remain Apple Clang
while this isolated bootstrap experiment uses GNU GCC.

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
  experiment instead.

``GNU GCC was selected``
  Add ``MACOS_ALLOW_NONCLANG=1`` only when the experimental path is
  intentional.

Verification
------------

The compiler policy runs before ``builder.sh`` chooses its LTO default.  The
existing macOS compiler verifier then compiles C, C++, Objective-C, and
build-machine probes and checks their Mach-O architecture with ``lipo``.  The
PowerPC bootstrap separately verifies its staged assembler, linker, and final
cross compiler.
