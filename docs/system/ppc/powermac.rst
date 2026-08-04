PowerMac family boards (``g3beige``, ``mac99``, ``powermac3_1``)
==================================================================

Use the executable ``qemu-system-ppc`` to simulate a complete PowerMac
PowerPC system.

- ``g3beige``              Heathrow based OldWorld Power Mac G3
- ``mac99``                Generic Core99 based PowerMac
- ``powermac3_1``          1999 Power Mac G4 AGP (Sawtooth)

The ``powermac3_1`` machine is a historical profile built on the ``mac99``
device implementation.  It selects a PowerPC 7400 processor, a KeyLargo PMU
without ADB, USB keyboard and mouse input, and 128 MiB of default RAM.  It also
inherits the Mac99 firmware compatibility loader and its ``firmware-entry``
override.

A typical Mac OS 9 test command is::

  qemu-system-ppc -machine powermac3_1 -m 128M \
    -bios pc-bios/openbios-ppc -boot d -cdrom macos9.iso

Supported devices
-----------------

QEMU emulates the following PowerMac peripherals:

 *  UniNorth or Grackle PCI Bridge
 *  PCI VGA compatible card with VESA Bochs Extensions
 *  2 PMAC IDE interfaces with hard disk and CD-ROM support
 *  Sungem or NE2000 PCI network adapters
 *  Non Volatile RAM
 *  VIA-CUDA with ADB input, or KeyLargo PMU with USB input.


Missing devices
---------------

 * Native AGP graphics hardware such as the ATI Rage 128
 * On-board FireWire and AirPort hardware
 * Hardware-exact audio and power-management behavior

Firmware
--------

Since version 0.9.1, QEMU uses OpenBIOS https://www.openbios.org/ for
the g3beige, mac99, and powermac3_1 PowerMac machines and the 40p machine.
OpenBIOS is a free (GPL v2) portable firmware implementation. The goal is to
implement a 100% IEEE 1275-1994 (referred to as Open Firmware) compliant
firmware.

The historical profile does not embed or require an Apple ROM.  It uses the
same OpenBIOS image as ``mac99`` while presenting a less ambiguous machine
configuration to the firmware and guest.  A firmware-specific reset entry may
be selected with::

  qemu-system-ppc -machine powermac3_1,firmware-entry=0xfff00200 ...
