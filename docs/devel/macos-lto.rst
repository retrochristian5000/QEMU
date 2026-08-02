macOS link-time optimization
===========================

The WHP build wrapper treats link-time optimization as a property of QEMU's
Meson-built host artifacts.  It is not a generic compiler flag for every
program or firmware image built during the same invocation.

Selecting LTO
-------------

Use ``QEMU_HOST_LTO=1`` to enable LTO and ``QEMU_HOST_LTO=0`` to disable it.
On a native Apple Silicon build the default is enabled.  ``TCG_ENABLE_LTO`` is
accepted as a compatibility alias, but the build stops if both names are set
to different values.

The name is deliberately ``QEMU_HOST_LTO`` rather than ``TCG_ENABLE_LTO``.
QEMU's ``--enable-lto`` option maps to Meson's project-wide host LTO option;
it is not limited to files under ``tcg/``.

Flag isolation
--------------

Do not place ``-flto``, ``-fno-lto``, or Darwin LTO linker options in
``CFLAGS``, ``CXXFLAGS``, ``OBJCFLAGS``, ``CPPFLAGS``, or ``LDFLAGS``.
``builder.sh`` rejects those forms because process-wide flags can escape into
build-machine utilities, firmware builds, and nested toolchain bootstraps.
Meson is the only component allowed to add LTO flags to QEMU host objects.

The OpenBIOS invocation is launched with the generic host compilation and
link flags removed.  Its host utilities and PowerPC cross compiler therefore
do not inherit QEMU's optimization policy.

macOS LTO preflight
-------------------

When macOS LTO is enabled, ``scripts/verify-macos-lto.sh`` runs before QEMU is
configured.  The probe:

* compiles two separate C translation units with ``-flto``;
* links them with the configured compiler driver and linker;
* verifies the resulting Mach-O architecture with ``lipo``;
* executes the result on the build machine;
* records the actual link-driver pipeline produced by ``-###``.

The manifest is stored at
``build/whp-ppc-<arch>-apple-darwin/.whp-macos-lto``.  Probe sources, objects,
the linked executable, and the linker pipeline are stored in the adjacent
``.whp-macos-lto.d`` directory.  The manifest signature participates in the
main WHP configuration stamp, so a change in LTO capability forces QEMU to
reconfigure.

Failure policy
--------------

An enabled LTO build fails before Meson setup when the compiler can emit LTO
objects but the selected linker cannot consume them, the output architecture
is wrong, or the linked program cannot execute.  Disabling LTO is explicit::

  QEMU_HOST_LTO=0 ./build.sh

Do not work around a failed preflight by adding raw LTO flags to the global
environment.  Diagnose the compiler, linker, SDK, and deployment target as one
toolchain instead.
