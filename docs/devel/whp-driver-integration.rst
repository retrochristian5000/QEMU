WHP-Drivers: QEMU hardware test bridge
======================================

Purpose
-------

This bridge pins the independent WHP-Drivers repository at
tests/whp-drivers.  Do not compile Windows 95 or DOS guest drivers into the
QEMU host executable.  The QEMU fork implements virtual devices; the driver
repository owns guest code, evidence ledgers, and hardware-specific tests.

This deliberately small first stage tests PCI controller enumeration through
QMP without running a guest operating system or touching physical hardware.
The source checkout is pinned by a Git mode 160000 gitlink; its nested LLVM,
OpenWatcom, and Water submodules are not initialized by the bridge workflow.

Test coverage and negative evidence
-----------------------------------

* QEMU ich9-ahci exposes PCI mass-storage/SATA class 01:06.  This does NOT
  emulate AMD FCH SATA or prove a Windows 95 storage driver works.
* QEMU intel-hda exposes PCI multimedia/HDA class 04:03.  This does NOT
  emulate the exact AMD audio controller or prove a codec/driver works.
* QEMU usb-ehci exposes PCI serial-bus/USB class 0c:03.  It does NOT
  emulate Brother MFC-290C (USB identity 04f9:01fd), its interfaces, or
  its printer, scanner, fax, or storage commands.
* The Realtek RTL8111E Ethernet and Radeon HD 6410D devices investigated
  in WHP-Drivers do not acquire exact emulation from this bridge.
* DOS WHPPROBE.EXE must run inside an appropriate DOS guest to observe
  guest-visible BIOS/PCI state.  Host-side C tests, QMP queries, and a
  successfully linked DOS MZ executable are distinct validation stages.

Running checks
--------------

Initialize only the test input source, without its heavyweight toolchains::

    git submodule update --init -- tests/whp-drivers
    git rev-parse HEAD:tests/whp-drivers
    git -C tests/whp-drivers rev-parse HEAD

The two revision values must match.  Then run the portable parser tests and
the existing host-side driver checks::

    python3 -m unittest discover -s scripts/tests -p test_whp_drivers_qmp.py
    sh tests/whp-drivers/build test-probe-scope
    sh tests/whp-drivers/build test-usb-pci-hci
    sh tests/whp-drivers/build test-hda-probe
    sh tests/whp-drivers/build test-brother-mfc290c

With a separately built QEMU fork system emulator::

    python3 scripts/tests/whp_drivers_qmp.py --qemu build/qemu-system-i386

The runtime script creates only three emulated controller instances, suspends
the VM before guest execution, disables default devices and networking, and
asks QMP for their PCI identities/class codes.  It terminates the QEMU
process and removes its temporary Unix socket.  The output status is
generic-controller-enumeration-only, not a driver pass.

The workflow whp-driver-bridge.yml runs parser and driver host tests on
relevant pushes.  A manually dispatched workflow additionally builds this
QEMU fork's i386 system emulator and runs the QMP smoke test.  It intentionally
does not require a full LLVM/OpenWatcom bootstrap for every CI check.

Next gate
---------

Once a freely redistributable or locally supplied DOS boot image and a
verified, built WHPPROBE.EXE are available, create a separate optional guest
execution test.  Use a copy-on-write guest disk, an explicit serial-output
contract, and bounded timeouts.  Do not claim a successful DOS run based on
QMP inventory or PCI class matches, and do not silently attach USB host
devices, write firmware, print, scan, or dial a fax number.
