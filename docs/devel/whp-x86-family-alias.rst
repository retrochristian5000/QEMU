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

With ``QEMU_X86_FAMILY_LINK=y``, the WHP runner builds the
``x86_64-softmmu`` backend. A previously configured, WHP-owned incremental
build may contain ``i386-softmmu``: its target-graph entry is converted to
``x86_64-softmmu`` during reconfiguration, without cleaning the other
compiled targets. The old ``qemu-system-i386`` remains untouched until the
new backend has built and passed its CPU-model probe.

After building, run from the source tree::

    python3 scripts/whp-build/x86-family-alias.py --directory BUILD_DIR --check-only
    python3 scripts/whp-build/x86-family-alias.py --directory BUILD_DIR

When installing, run the same command with ``--directory PREFIX/bin``
*after* installing ``qemu-system-x86_64``. The tool checks that the backend
advertises the ``qemu32`` CPU model, then publishes the relative
``qemu-system-i386`` symbolic link atomically. In this explicitly enabled
mode, an existing regular i386 executable or unrelated symlink at that
destination is replaced; the unrelated symlink's target is not modified.
Directories and special files are never replaced, and a failed probe leaves
the previous executable untouched. The ``--check-only`` option reports
``replace-ready`` without changing files. Windows is unsupported.

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

This option defaults to **off**. When explicitly enabled, existing
``i386-softmmu`` target entries are replaced with ``x86_64-softmmu`` in
the WHP-owned incremental build graph; no unrelated build artifacts are
removed. In the Bash build path,
explicit x86-family audio choices are now carried to a generated
``configs/devices/x86_64-softmmu/whp-user.mak`` preset via
``--with-devices-x86_64=whp-user``; the x86_64 default includes the
i386 device defaults and can use the same ISA/PCI hardware models.
In particular, ``I386_AUDIO_GAMEBLASTER`` controls one shared
``gameblaster`` ISA implementation, not an i386-only CPU variant.
An unchanged ``auto`` choice leaves the tracked defaults alone.
The portable Python fallback still rejects explicit hardware filters
because it does not generate device presets. Build-directory ownership and
host-ABI checks remain in force; this change only relaxes replacement of the
requested emulator filename.

Firmware mapping for original 16-bit, i386, and x86_64 guests
-------------------------------------------------------------

The emulator executable family must **not** be confused with the BIOS's
CPU execution modes:

* ``x86-softmmu`` is the distinct original 8086/8088 target. Its
  ``x86-8086`` and ``x86-8088`` boards require an explicit, genuine
  8086/8088-compatible ``-bios FILE`` ROM of up to 64 KiB. The current
  SeaBIOS binary is **not** such a ROM: its POST switches to 32-bit
  protected mode and requires 80386-class instructions. The names
  ``bios.bin`` and ``bios-256k.bin`` do not indicate a 16-bit-only ROM.
* ``i386-softmmu`` uses standard SeaBIOS for legacy PC boot, including
  its real-mode BIOS entry points and 32-bit initialization code.
* ``x86_64-softmmu`` uses the same SeaBIOS images for legacy BIOS boot,
  including through the opt-in ``qemu-system-i386`` symlink. A 64-bit
  guest is entered by its operating-system boot loader; SeaBIOS itself is
  **not** built as an x86_64 firmware executable.
* IA32 UEFI and x86_64 UEFI are different firmware ABI targets, provided
  separately by EDK2/OVMF. Do not replace them with a SeaBIOS symlink.

The WHP ``BUILD_SEABIOS=auto`` selection and Meson firmware target
now check both ``i386-softmmu`` and ``x86_64-softmmu`` without
matching ``x86-softmmu``. The SeaBIOS compiler remains the
``i386-none-elf`` toolchain. The three named ROM outputs
(``bios.bin``, ``bios-256k.bin``, and ``bios-microvm.bin``)
are distinct **machine-profile** images and must not be deduplicated
based only on the guest CPU bitness.
