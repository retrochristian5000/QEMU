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


ISA COM port UART profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~

The default ``isa-serial`` remains a generic 16550A-compatible UART.
The explicit ``ins8250a``, ``ns16450`` and ``ns16550a`` ISA devices
select National Semiconductor-compatible register interfaces. The
INS8250A and NS16450 have a scratch register but do not implement
FIFO control; writes to offset 2 are ignored and IIR bits 6-7 remain
clear. Their ACPI hardware ID is PNP0500 (standard COM port).
The NS16550A and generic device retain 16-byte FIFOs and PNP0501.
Reset returns the common UART engine to character mode.

National Semiconductor application note AN-493, April 1989, sections
1, 3 and 5 describes the differences. The INS8250A and NS16450
currently share register behavior; their electrical bus timing
differences are not emulated. The original INS8250 without a scratch
register, defective NS16550 FIFO behavior, and 64-byte FIFO variants
are not modeled by these profiles.

Each device accepts the existing ``index``, ``iobase``, ``irq``,
``chardev`` and ``baudbase`` properties. Index 0 through 3 selects
COM1 through COM4, respectively. The default bases are 0x3f8, 0x2f8,
0x3e8 and 0x2e8 with IRQs 4, 3, 4 and 3. The existing resource
validation applies to the derived types.

For example, replace automatic serial port creation with::

    -serial none -chardev msmouse,id=mouse0 -device ns16550a,index=0,chardev=mouse0

The serial mouse is a character backend, not a second UART.
Use a separate backend for each port and avoid conflicting IRQ
assignments. Existing IRQ sharing and ACPI interrupt-resource
semantics are unchanged. Use matching UART profiles for migration;
do not switch profiles when restoring saved state.

ISA modem compatibility profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing Hayes-compatible modem engine also supports integrated
ISA device profiles with an owned 16550A-compatible UART:

* ``hayes-accura-2400``
* ``rockwell-voice-14400``
* ``att-paradyne-dataport-3711``
* ``att-paradyne-dataport-3740``

For example, to install a modem on COM2 and leave COM1 available::

    -serial none -device hayes-accura-2400,index=1

The device owns its character backend; do not provide a separate
``chardev`` or a second UART at the same I/O range. The normal COM
index, base and IRQ validation applies. The guest sees a serial
controller (PNP0501), and modem identification is provided by the
existing AT-command engine. No original modem ROM, exact internal
card design, ISA PnP identifier, analog telephone DSP, fax signal
processing or real telephone connection is claimed.

These device profiles represent an unplugged telephone line: dialing
normally returns NO DIALTONE and answering returns NO CARRIER. The
3740 distinguishes blind dialing (X0, X1, X3), which returns
NO CARRIER instead. These are immediate simulated results, not
measurements of physical dial tones. Other models retain the existing
``-chardev modem`` simulated connection behavior; the 3740 requires
an explicit TCP endpoint for that byte-stream substitute. Hardware reset clears
pending modem bytes and resets the AT settings. Live migration,
saved-state loading and hotplug are not supported for the new device
profiles because modem state is not serialized.

DataPort Express 3740 line behavior
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The 3740 compatibility profile supports the documented CTS selection:
``AT\\D0`` forces CTS high; ``AT\\D1`` (default) follows DTR.
DCD is independent of CTS and follows connection state with ``AT&C1``.
An explicit ``AT&C0`` can force DCD high without establishing a
connection. DTR drop with &D2 also cancels pending outgoing TCP
connections. The integrated UART reset drops DTR and RTS and clears
the previous AT command. Without a configured remote transport, the
3740 never synthesizes a successful dial or answer. TCP transport
remains a byte-stream substitute; TCP connection is not V.34 training.
Incoming calls, physical dial tone/busy detection, S6/S7 timing,
ring cadence, V.34 modulation, error correction and fax DSP remain
unimplemented. The model uses the conventional Hayes X0-X4 subset,
as described in the related AT&T DataPort PCX manual (October 1995).
The 3740 CTS settings are documented in the archived DataPort Express
3740 configuration reference.

Future telephone media integration should separate call control,
PCM media and modulation. A SIP/RTP service (for example a separate
process using liblinphone) can handle signaling and G.711 audio, but
does not supply the modem DSP. A separately verified modem engine
must generate and detect waveform and training signals before
asserting carrier. A local-only virtual telephone exchange should be
tested first. Any real network or PSTN route must be explicitly
configured by the host operator, with destination restrictions;
guest dial strings must not create arbitrary host connections.
The optional standalone Liblinphone SDK helper is described in
``tools/sip/README.rst``. It does not yet implement a telephone service
or connect to the modem. No SIP registration, audio transport or
telephone calls are enabled by the modem implementation.

Experimental Intel 440BX PC
~~~~~~~~~~~~~~~~~~~~~~~~~~~

PCI and AGP are distinct physical interfaces. The common PCI bus layer
provides a read-only QOM property ``agp-port`` for host-selected AGP-facing
segments. This preserves existing PCI configuration-space access, bus
names and device attachment behavior; it does not advertise AGP
capabilities or implement graphics address remapping. The 440FX and
current AGP-disabled 440BX root buses report false.

A future AGP-enabled 440BX must expose the 8086:7190 host function and
the 8086:7191 bridge at PCI bus 0 device 1, with a separate graphics
segment, aperture and GART. The existing PIIX placement and associated
interrupt/firmware tables must be considered before adding that bridge.
Do not advertise an AGP device merely by attaching it to the conventional
PCI root. See Intel 82443BX datasheet, sections 3.2, 3.4 and 4.1.

The fork includes an opt-in ``pc-i440bx`` machine with the 82443BX
host bridge in its AGP-disabled strap configuration (8086:7192) and
the existing PIIX4 southbridge. The legacy PC configuration mechanism
and PAM/compatible SMRAM memory mappings are shared with i440FX.
The host-facing QOM type is ``i440BX-pcihost`` and its PCI-facing
function is ``i440BX``. The existing ``i440FX-pcihost`` remains the
440FX machine's controller. The legacy QOM path ``/machine/i440fx``
and root bus ``pci.0`` are intentionally retained on both machines;
ACPI discovers the shared host base type. Neither host is a standalone
expansion card: select the appropriate machine rather than adding a
second host via ``-device``.

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

The ``pentium_mmx`` CPU model identifies family 5, model 4
(Pentium with MMX technology). The unversioned ``pentium`` instead
selects the non-MMX P54C (family 5, model 2). Use one core and one thread per socket
to avoid synthesizing a multicore or SMT Pentium package. For a Windows
9x cold-boot timing comparison, replace the CPU and SMP options with::

    -cpu pentium_mmx,tsc-frequency=200000000
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

Cirrus Logic chipset profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``cirrus-vga-generic`` device keeps the default PCI implementation
for existing command lines. The explicit ``cirrus-vga-generic-pci`` type
shares that implementation, and ``cirrus-vga-generic-isa`` selects ISA.
Their guest-visible identities remain CL-GD5446 and CL-GD5428,
respectively. The chipset-specific device names are:

* ``gd5422``: CL-GD5422 ISA.
* ``gd5426``: CL-GD5426 ISA.
* ``gd5428``: CL-GD5428 ISA, sharing the generic ISA implementation.
* ``gd5430-pci`` and ``gd5430-vlb``: explicit bus variants.
* ``gd5446-pci``: CL-GD5446 PCI, sharing the generic PCI implementation.

The unsuffixed GD5428 profile selects ISA. Cirrus Logic's January 1994
CL-GD542X Technical Reference Manual (feature table and host interface
section 2.3) documents ISA, MicroChannel and local-bus interfaces for
the GD5428, not native PCI. No GD5428 PCI variant is registered; a VLB
variant requires its own bus decoder. See
https://bitsavers.trailing-edge.com/components/cirrusLogic/graphics/CL-GD542X_Technical_Reference_Manual_Jan1994.pdf

Use the listed names in place of the former ``isa-cirrus-*`` and
``cirrus-gd*`` profiles. The default VGA selector ``-vga cirrus``
continues to choose the generic PCI or ISA implementation according
to the machine. Explicit device selection does not change chipset
registers, VRAM defaults, bus mappings or migration section names.

The experimental ``gd5430-pci`` profile uses PCI ID 1013:00a0,
CR27 identification 0xa0, PCI bus straps, 2 MiB VRAM and a 16 MiB
prefetchable BAR0. It models the primary framebuffer aperture only,
with relocatable VGA I/O disabled, and does not expose the GD5446
dedicated MMIO BAR or high BitBLT aperture. The GD5430 PCI and VLB
variants both omit GR12-GR15, GR33 solid-fill and GR31 auto-start.
Other chipset-specific accelerator features and clocks are incomplete.

For a legacy PC guest, replace the existing primary VGA configuration
with the following, supplying a compatible, lawfully obtained GD5430
PCI VGA option ROM::

    -vga none -device gd5430-pci,romfile=/path/to/gd5430.rom

The experimental PCI profile has no default option ROM; it does not
reuse the GD5446 PCI ROM automatically. Boot and guest-driver compatibility
have not yet been established. Keep the same device type and VRAM
configuration when saving/restoring a VM. Use a cold boot to change
chipsets. The GD5446 precise timing property is not available on GD5430.

Hardware reference: Cirrus Logic Alpine Family Technical Reference
Manual, February 1995, sections 4.14, 4.18-4.19, 9.27-9.30,
9.40 and 9.42, and Appendix D8.

Cirrus GD5446 BitBLT register behavior
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The GD5446 height register (GR22-GR23) holds an 11-bit scanline count
minus one, unlike the 13-bit width and pitch registers. Both indexed
I/O and MMIO use the same mask. Execution also applies the mask to
previously loaded register state. Other Cirrus chip profiles retain
their existing height masks pending separate hardware verification.
A solid-fill operation rejected by the existing geometry checks returns
the engine to idle, as do other rejected BitBLT operations. No new
command queue, pause scheduling or video-to-system transfer support is
introduced.

Hardware reference: CL-GD5446 Technical Reference Manual, November 1996,
sections 5.2-5.5 and 5.10.

Cirrus GD5446 display timing
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For an opt-in comparison of the GD5446 display clock and retrace
behavior, replace the existing primary VGA selection with::

    -vga none -device cirrus-vga-generic,precise-timing=on

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

The generic default is IRQ10 on a PIIX machine and IRQ9 otherwise.
QEMU warns if a PIIX ACPI power-management function also uses IRQ9. IRQ2 is the AT interrupt
cascade and is not a separate selectable NIC interrupt. Select a free
IRQ and match the I/O base and IRQ in the guest's network adapter
properties. For example, IRQ3 is usable only if COM2 and any other
IRQ3 users are absent. IRQ5 may be occupied by a sound card, and IRQ10
and IRQ11 may be used by PCI interrupt steering.

The optional ``novell-ne2000`` profile models the documented jumper
choices of Eagle Technology assembly 810-149-00X. Its I/O bases are
0x300, 0x320, 0x340 and 0x360; its IRQs are 3 (default), 4, 5 and 9.
It exposes a 16 KiB packet memory window at 0x4000-0x7fff and byte/word
data-port transfers, without the shared RTL8029 identification responses.
The generic ISA and PCI profiles retain their existing behavior.

For example, using an otherwise unused IRQ3 and I/O base 0x300::

    -netdev user,id=net0 -device novell-ne2000,netdev=net0,irq=3

Replace the existing NIC attachment; do not add a second NIC using the
same resources. Select matching resources in the guest. The profile does
not automatically change the Windows driver name. Media/boot-ROM jumpers,
electrical bus aliasing, collision timing and complete DP8390 register
behavior are not modeled. Use matching profiles when restoring state.

References: Eagle Technology NE2000 assembly 810-149-00X jumper table
(https://stason.org/TULARC/pc/network-cards/E/EAGLE-TECHNOLOGY-Ethernet-NE2000-ASSY-810-149-00X.html)
and QNX 4.25 Net.ether1000 documentation
(https://staff.qnx.com/developers/docs/qnx_4.25_docs/qnx4/utils/n/netether1000.html).

The I/O overlap check detects devices mapped before the NIC is realized.
It is not a general resource allocator and does not prevent a later
device or reprogrammed PCI BAR from using the same range.

PIIX motherboard controller selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Intel's 82371FB/82371SB PCI ISA IDE Xcelerator datasheet (May 1996),
sections 3.7 and 3.8, specifies integrated 82C54 timer and cascaded
82C59 interrupt controller functions. These are chipset functions, not
separate discrete expansion cards.

The PIIX-family PC machines support an opt-in controller selection::

    -machine pc,chipset-controllers=on

This selects the existing ``i8254`` software timer profile and two
``i8259a`` software PIC profiles instead of ``isa-pit`` and
``isa-i8259``, and two integrated ``piix-82c37`` DMA profiles instead
of ``i8257``. It retains the motherboard's existing IRQ cascade,
ELCR, HPET routing, PC speaker link, and I/O addresses. The ``pit=off``
and ``pic=off`` options still suppress their respective controllers.
The option is not a claim of complete 82C54/82C59 silicon emulation;
the PIC profiles currently share the same behavior. It is incompatible
with Xen and enabled in-kernel PIC/PIT emulation.

The default is off to retain existing machine-version and migration
configurations. Use a cold boot when changing the selection, and keep
it consistent across saved-state or migration endpoints. Do not add
duplicate standalone timers, DMA controllers or interrupt controllers.
CPU, RAM, RTC, storage, display and NIC selections are unchanged. The option
does not select a physical motherboard model or change Windows driver
names by itself.

PIIX DMA controller registers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Intel 82371FB/82371SB documentation (May 1996), sections 2.5.1.1
and 2.5.1.4-2.5.1.6, and the 82371AB PIIX4 documentation, describe
two integrated 82C37-compatible DMA groups. DMA1 serves channels 0-3,
DMA2 channels 4-7, with channel 4 reserved for the cascade.
With ``chipset-controllers=on`` the PIIX-specific pair exposes the
all-channel mask at 0x0f and 0xde with only four implemented bits.
Master clear sets those four bits. The write-only request register
does not expose the old mask alias (reads return zero in this model).
The group-disable command inhibits service, including DMA1 when DMA2
is disabled or channel 4 is masked. Enabling a group or unmasking the
cascade rechecks pending requests.

The common ISA DMA transfer API, I/O locations and migration fields
are retained. This is a partial 82C37 register and scheduling model,
not a discrete 8257 or complete 8237A simulation. Terminal-count
masking, autoinitialization, separate software/hardware request latches,
address wrapping, decrement transfers, and electrical arbitration
are not corrected by this change. Existing machine defaults are
unchanged; use the same controller selection at both migration
endpoints. Windows may still identify the standard DMA class with
a generic driver name.

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
not proof of an EMU8000. The existing ``sb16-generic`` profile remains the
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
revision-specific capability limits. Spindle speeds below are historical
reference data, not reported in the later word 217:

* ``seagate-st31640a``: ST31640A, 5376 RPM, original 3175200 sectors.
* ``seagate-st32140a``: ST32140A, 5376 RPM, original 4127760 sectors.
* ``ibm-dtta-351010``: IBM-DTTA-351010, 5400 RPM, original 19807200 sectors.

For example, with an existing disk image and an available IDE unit::

    -drive if=none,id=hdd0,file=/path/to/disk.img,format=raw \
        -device seagate-st32140a,bus=ide.0,unit=0,drive=hdd0

Replace the original attachment rather than attaching the image twice.
The image format must match the actual image. Capacity and geometry
continue to follow the backend and existing geometry options; the profiles
never resize an image. Model, serial and firmware revision can still be overridden using the
existing properties.

The Medalists use an ATA-2 compatibility subset, with words 69-255
cleared as reserved or vendor-specific and no UDMA. The Deskstar uses
ATA/ATAPI-4 major word 0x001e and minor word 0x0017 (IBM figure 81),
with UDMA modes 0-2. Both reject LBA48 and TRIM commands and invalid
transfer modes. Initial images must be smaller than 2^28 sectors;
resized images are limited to the representable LBA28 sector count.
These are not complete vendor implementations: seek timing, original
firmware, security, queued DMA, and vendor commands remain absent or
incomplete. The generic engine's multiple-sector limit is retained.
Cold boot when upgrading these profiles; do not mix saved states from
before and after the capability change.

References: Seagate Medalist 1640 and 2140 Product Manual, January 1996,
sections 1.1 and 3.2 (https://www.seagate.com/support/disc/manuals/ata/36314-21.pdf);
IBM DTTA-3xxxxx OEM specifications, sections 1 and 3.2
(https://www.manualowl.com/m/IBM/DTTA-351010/Manual/335209).
