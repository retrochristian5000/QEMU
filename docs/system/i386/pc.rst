i440fx PC (``pc-i440fx``, ``pc``)
=================================

Peripherals
~~~~~~~~~~~

.. include:: ../target-i386-desc.rst.inc

Monorail PC 133 compatibility profile (``monorail-pc133``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

WHP includes a **distinct, non-default** Monorail PC 133 machine type
as an initial late-1990s hardware reference. The contemporary
`June 1997 Windows Magazine review
<https://www.kaisernet.org/library/1997/0601/winla133.htm>`_
describes the integrated Monorail PC 133 with a MiTAC-designed board,
AMD processor, 16 MiB EDO RAM (expandable to 80 MiB), a 10.4-inch
640x480 LCD, Chips & Technologies 65548 video, Crystal 16-bit/FM audio,
a Rockwell modem and a half-length ISA slot.

The profile is an **approximation**, not yet a component-accurate
reconstruction. It uses QEMU's i440FX/PIIX PC device model and a
Pentium-class emulated CPU, defaults to one CPU and 16 MiB RAM, and
accepts 16--80 MiB. Standard VGA is a temporary video substitute.
The legacy NE2000 ISA model is available as an optional expansion NIC,
**not** a claim that Monorail installed one by default. Crystal audio,
the C&T 65548 LCD controller, Rockwell modem, exact MiTAC chipset and
the original BIOS ROM are **not** emulated by this machine. Firmware
comes from QEMU's normal SeaBIOS path; optional WHP extended POST tests
can be requested separately.

To list the machine and start it with no additional NIC::

    qemu-system-i386 -machine help
    qemu-system-i386 -machine monorail-pc133 -m 16M -cpu pentium \
      -nic none

The **Monorail Series 8005** mini-tower recalled from our earlier
hardware research is a *separate 1998 target*. Its precise motherboard,
BIOS, CPU and onboard hardware configuration still require verification;
do not silently reuse the PC 133's MiTAC board or integrated LCD for it.


Host laptop battery snapshot for legacy SeaBIOS APM
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On supported laptop hosts, the WHP QEMU fork can opt in to reading the
**host's internal battery** at VM startup and forward an eight-byte APM 1.2
snapshot to the matching WHP SeaBIOS firmware::

    qemu-system-i386 -machine pc,host-battery=on

This option is disabled by default. On macOS, QEMU uses IOKit's power-source
API and ignores external UPSs. On Linux, it reads the host's
``/sys/class/power_supply`` interface. It reports the observed AC line,
charge percentage, charging status, and remaining discharge time (when
available), without giving the guest access to host battery control.

The interface requires exactly one readable internal host battery. If none
is found, multiple internal batteries are present, or the host platform does
not support the reader, ``host-battery=on`` fails explicitly instead of
fabricating an emulated battery. Without the option, no host power source
is exported. This is intentionally independent of the Dell-style POST UI
and works with the existing SeaBIOS APM 1.2 overlay protocol.

**Runtime limitation:** the current SeaBIOS firmware caches this record
once during POST. The guest does not receive ongoing updates, lid events,
hot-swap notifications, or charge changes after boot. Host state is sampled
when QEMU creates the firmware configuration, not continuously. The
``opt/org.seabios/whp-laptop-apm`` fw_cfg entry holds the protocol version
and battery fields documented in ``roms/seabios/docs/Runtime_config.md``.
Use a separate future runtime/ACPI device protocol for live monitoring;
do not confuse this static bridge with battery hardware passthrough or
host sleep/suspend passthrough.

For deterministic test scenarios, leave ``host-battery`` off and provide
a deliberately constructed firmware record using ``-fw_cfg``. Do not specify
the record manually at the same time as ``host-battery=on`` because both
paths would attempt to publish the same fw_cfg filename.
