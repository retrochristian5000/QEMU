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

Cirrus GD5446 display timing
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For an opt-in comparison of the GD5446 display clock and retrace
behavior, replace the existing primary VGA selection with::

    -vga none -device cirrus-vga,precise-timing=on

Do not add this as a second VGA adapter. The PCI Cirrus profile derives
the character clock from the selected VCLK synthesizer registers and
SR1 clocking mode, and computes standard CRTC blanking and vertical
retrace status from virtual time. The timing state is reconstructed
from the register values after reset and migration.

The default profile and ISA/VLB variants retain their previous retrace
behavior. This option does not model extended/interlaced CRTC timing,
PLL lock latency, memory-clock arbitration, or BitBLT execution time.
It changes guest-visible status timing, not host display refresh
scheduling. Use identical powered-off configurations for comparisons
and keep this property consistent when restoring saved states.

Fixed-resource NE2000 ISA adapters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``ne2k_isa`` device models a fixed-resource NE2000-compatible card,
not an ISA Plug and Play device. The default I/O base is 0x300 and the
adapter occupies 32 consecutive ports. The base must be aligned to 32
ports and must not overlap an already mapped I/O region. Supported IRQ
selections are 3, 4, 5, 9, 10, 11, 12, 14 and 15.

The historical default IRQ9 is retained, but QEMU warns if a PIIX ACPI
power-management function also uses IRQ9. IRQ2 is the AT interrupt
cascade and is not a separate selectable NIC interrupt. Select a free
IRQ and match the I/O base and IRQ in the guest's network adapter
properties. For example, IRQ3 is usable only if COM2 and any other
IRQ3 users are absent. IRQ5 may be occupied by a sound card, and IRQ10
and IRQ11 may be used by PCI interrupt steering.

The I/O overlap check detects devices mapped before the NIC is realized.
It is not a general resource allocator and does not prevent a later
device or reprogrammed PCI BAR from using the same range.

Explicit ISA timer profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The software PIT exposes a generic ``isa-pit`` profile and fixed-model
``i8253`` and ``i8254`` profiles. They share the existing counter engine.
The chip-specific profiles select the existing model-specific behavior;
BCD counting, gate timing and deferred reloads are not fully modeled.
The legacy Windows system timer identity remains unchanged.

For isolated testing, disable the motherboard PIT and HPET first::

    -machine pc,pit=off,hpet=off -device i8254

Explicit attachment defaults to I/O ports 0x40-0x43 and IRQ0. Only one
system PIT is permitted on the ISA bus. These explicit configurations
are not equivalent to motherboard initialization: the PC speaker and
HPET wiring are not automatically recreated. For normal PC guests, keep
the motherboard PIT and select a model using::

    -global isa-pit.model=i8254

Existing machine defaults and the KVM in-kernel PIT remain unchanged.

Creative Sound Blaster AWE32
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Windows 9x SB16/AWE32 driver name describes a shared PCM interface,
not proof of an EMU8000. The existing ``sb16`` profile remains the
legacy ISA DSP/mixer implementation. The ``awe32`` profile is reserved
and deliberately rejects realization until the synthesizer and sound
memory are implemented. It does not register an audio backend or claim
any I/O, DMA or IRQ resources.

The legacy AWE32 board should compose the SB16-compatible PCM engine
with a distinct EMU8000 component. For a DSP base of 0x220, the three
synthesis I/O windows are 0x620-0x623, 0xa20-0xa23 and 0xe20-0xe23.
The pointer register at 0xe22 selects a register and channel; accesses
are 16-bit words or pairs of words, not byte-wide DSP commands. Later
ISA PnP boards can assign the synth base independently of the DSP.

Implement the EMU8000 register decoding, sample ROM/RAM, voice timing,
envelopes, filters and effects separately from the SB16 DSP. Keep the
ISA PnP enumeration and activation separate from legacy board wiring.
Validate each I/O window with the ISA resource API before mapping it.
Do not fabricate a successful hardware detection or silently substitute
FM or host MIDI for the wavetable engine. Sample ROM images must be
provided from an appropriate authorized source; none are bundled here.

Reference: E-mu/Creative, AWE32/EMU8000 Programmer's Guide (1994-1996),
sections 1-3, https://www.dosdays.co.uk/media/creative/emu8kpgm.pdf.

Historical ATA HDD identity profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The generic ``ide-hd`` remains unchanged. Three optional IDE disk types
supply manufacturer model strings in IDENTIFY DEVICE words 27-46 and
nominal rotation rates in word 217:

* ``seagate-st31640a``: ST31640A, 5376 RPM, original 3175200 sectors.
* ``seagate-st32140a``: ST32140A, 5376 RPM, original 4127760 sectors.
* ``ibm-dtta-351010``: IBM-DTTA-351010, 5400 RPM, original 19807200 sectors.

For example, with an existing disk image and an available IDE unit::

    -drive if=none,id=hdd0,file=/path/to/disk.img,format=raw \
        -device seagate-st32140a,bus=ide.0,unit=0,drive=hdd0

Replace the original attachment rather than attaching the image twice.
The image format must match the actual image. Capacity and geometry
continue to follow the backend and existing geometry options; the profiles
never resize an image. Model, serial, firmware revision and rotation rate
can still be overridden using the existing properties.

These are identity profiles, not complete ATA-2 or ATA/ATAPI-4 hardware
emulations. They retain the generic engine's command set and advertised
capabilities, including newer features, and do not model seek time or
vendor firmware. The rotation field is a later ATA identification field.
Keep the device profile and overrides identical when restoring a VM.

References: Seagate Medalist 1640 and 2140 Product Manual, January 1996,
sections 1.1 and 3.2 (https://www.seagate.com/support/disc/manuals/ata/36314-21.pdf);
IBM DTTA-3xxxxx OEM specifications, sections 1 and 3.2
(https://www.manualowl.com/m/IBM/DTTA-351010/Manual/335209).
