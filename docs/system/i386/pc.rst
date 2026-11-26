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


Experimental Intel 440BX PC
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The fork includes an opt-in ``pc-i440bx`` machine with the 82443BX
host bridge in its AGP-disabled strap configuration (8086:7192) and
the existing PIIX4 southbridge. The legacy PC configuration mechanism
and PAM/compatible SMRAM memory mappings are shared with i440FX.

This is an initial functional subset, not an electrically complete
440BX motherboard. RAM is fixed at machine creation (8 MiB through
1 GiB in 8 MiB increments); the DRB registers report synthetic
configured row boundaries and do not change physical RAM decoding.
DRAM timing, extended SMRAM, AGP/GART, chipset error signaling,
power management straps beyond AGP disable, and physical SPD topology
are not implemented. The existing PAM helper also has limitations
for write-only shadow RAM. Do not use this experimental machine
for production migration or assume compatibility with physical BIOS ROMs.

Build the matching X86-Firmware/SeaBIOS source with the 440BX host
ID support (commit 5379a7d5f98524104e35216e84c1d57619f88c43)
and specify that BIOS explicitly, for example::

    qemu-system-i386 -machine pc-i440bx -m 128M \
        -bios /path/to/seabios/out/bios.bin

The default firmware name is ``bios-440bx.bin``, intentionally distinct
from the stock i440FX/Q35 BIOS; no such prebuilt binary is included
by this change. Existing PC machine defaults remain unchanged.

Hardware reference: Intel 82443BX Host Bridge/Controller datasheet,
order 290633-001, April 1998, chapter 3.

Legacy Windows timing diagnostics
---------------------------------

Windows 95 and Windows 98 can report a protection error while initializing
NDIS when their timing calibration encounters an effective CPU speed above
its supported range (Microsoft Knowledge Base Q312108). This is not by
itself evidence of a defective emulated network adapter.

Windows 95 and Windows 98 use one processor even when additional processors
are installed (Microsoft Knowledge Base Q193645). Start by replacing the
existing SMP option with a single CPU, without changing the accelerator,
CPU model, or clock options::

    -smp cpus=1,sockets=1,cores=1,threads=1,maxcpus=1

Compare repeated cold boots with the original SMP configuration. This avoids
confounding CPU topology with virtual timing changes. More vCPUs do not
increase the speed of the single-processor Windows 9x kernel.

If the error persists, compare the same guest and device configuration
using a single vCPU and fixed instruction-count virtual time::

    -accel tcg,thread=single -smp 1 -icount shift=3,align=off,sleep=on

Replace existing accelerator, SMP and icount options rather than appending
conflicting values. This diagnostic advances virtual time by eight nanoseconds
per guest instruction; it does not model a physical CPU's clock frequency or
instruction latencies. Keep the NIC, IRQ, firmware, and disk configuration
unchanged between runs. Do not use a network adapter change as a substitute
for verifying guest timer and interrupt behavior.

Compare repeated cold boots, virtual PIT progress and the first x86 divide
exception during startup if the error persists. Fixed icount is a diagnostic
and optional compatibility configuration, not a change to TCG defaults or a
verified fix for every NDIS initialization failure.

Pentium MMX topology and TSC
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing ``pentium`` CPU model identifies family 5, model 4
(Pentium with MMX technology). Use one core and one thread per socket
to avoid synthesizing a multicore or SMT Pentium package. For a Windows
9x cold-boot timing comparison, replace the CPU and SMP options with::

    -cpu pentium,tsc-frequency=200000000
    -smp cpus=1,sockets=1,cores=1,threads=1,maxcpus=1

With system TCG, a positive configured TSC frequency now scales the VM's
virtual nanosecond clock. This changes the counter rate, not the number
of executed instructions per second, and does not guarantee that a
guest busy-loop calibration will succeed. Without an explicit frequency
the historical TCG tick source is unchanged. Do not mix saved states from
before and after this change when a nonzero frequency was configured;
use a cold boot. Hardware accelerator behavior is unchanged.

For a topology-only four-vCPU comparison, use four sockets with one core
and thread each. This is a synthetic SMP diagnostic, not a claim that
a particular Pentium MMX motherboard supported four sockets::

    -smp cpus=4,sockets=4,cores=1,threads=1,maxcpus=4
