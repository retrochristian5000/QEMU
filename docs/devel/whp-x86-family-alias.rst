WHP x86 system-family binary alias
==================================

For a POSIX host, ``qemu-system-x86_64`` can emulate ordinary 16-bit and
32-bit x86 guests as well as 64-bit ones. Building it alone and using a
relative symlink for ``qemu-system-i386`` avoids **linking and installing**
a second large system emulator. A symlink alone, when both binaries were
already built, does **not** reclaim the space used by the existing i386
binary.

This is an explicit optimization, **not a drop-in target-ABI replacement**.
QEMU's x86_64 system binary still reports its compiled architecture as
x86_64 (including QMP and GDB target details); migration compatibility and
any target-specific behavior must be tested independently. The WHP system
emulator recognizes invocation through the exact ``qemu-system-i386``
filename and selects the ``qemu32`` default CPU where a machine would
otherwise default to ``qemu64``. Explicit ``-cpu`` choices and
machine-specific defaults such as an 8086 board take precedence.

Procedure
---------

Build ``x86_64-softmmu`` and **do not** build ``i386-softmmu`` in the same
output directory. For example, with an independently configured QEMU build
directory, use ``--target-list=x86_64-softmmu`` and build
``qemu-system-x86_64``. The WHP launcher can request this executable by
name, but an existing incremental build may preserve previous i386 targets.
Do not remove old WHP builds merely to enable this optimization.

After building, run from the source tree::

    python3 scripts/whp-build/x86-family-alias.py --directory BUILD_DIR --check-only
    python3 scripts/whp-build/x86-family-alias.py --directory BUILD_DIR

When installing, run the same command with ``--directory PREFIX/bin``
*after* installing ``qemu-system-x86_64``. The tool checks that the backend
advertises the ``qemu32`` CPU model, creates a relative symbolic link, and
never replaces an existing emulator or a foreign symlink. No user file is
deleted or silently overwritten. Windows is unsupported in this mode.

Validate ``qemu-system-i386 --version``, ``-cpu help``, and ``-machine
help``; then smoke-test representative 8086/286/386/486 and later PC
guests. The alias does not change the CPU architecture reported by QMP.
For architecture-sensitive tooling, migrations, and accurate i386 target
metadata, retain the separately built i386 emulator.

Other architectures must not be aliased merely because they share a CPU
family: ABI, endianness, machine models, firmware, and migration formats
can differ.

Menu-driven builds
------------------

Set ``QEMU_X86_FAMILY_LINK=y`` in WHP menuconfig to substitute
``x86_64-softmmu`` when ``BUILD_QEMU_SYSTEM_I386=y``. The Bash and
portable runners build the x86_64 backend, create the legacy i386 symlink,
and repeat that operation after opt-in installation.

This option defaults to **off**. It refuses to reuse a build directory
already configured with ``i386-softmmu``, and it does not silently
discard explicit i386 audio Kconfig choices. Select a distinct build
directory without modifying or deleting your previous WHP output.
