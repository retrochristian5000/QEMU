i440fx PC (``pc-i440fx``, ``pc``)
=================================

PC machine profiles
~~~~~~~~~~~~~~~~~~~

The fork provides three unversioned i440FX/PIIX machine profiles:

* ``pc`` (canonical type ``pc-hardware``): the default PC, preferring the
  named motherboard controller implementations where userspace emulation
  is available. Automatic COM ports use the NS16550A profile, and the
  PS/2 mouse uses the IntelliMouse wheel protocol profile. The synthetic
  VMware backdoor and absolute mouse are disabled by default. The
  default PCI video card is ``gd5446-pci`` when Cirrus support is built.
* ``laptop-pc``: portable PC profile sharing the named desktop hardware
  selection, with a two-socket Intel 82092AA PCMCIA bridge when available,
  laptop SMBIOS enclosure identity and optional floppy/HPET defaults.
* ``generic-pc`` (canonical type ``pc-generic``): the compatible controller
  configuration, using the previous default device selections.

All three profiles share the same motherboard initialization, PCI and ISA
topology, firmware defaults, and configurable CPU, memory and expansion
devices. None represents a specific retail motherboard. The generic machine
still requires the i440FX/PIIX host and southbridge topology. The named
UART, mouse and VGA card are representative choices, not components
claimed to be integrated into every PIIX board. The default NIC on
``pc`` is AMD Am79C970A PCnet-PCI II (``am79c970a-pci``) when built,
otherwise the existing E1000 default is retained. The automatic floppy
controller is ``i82078``, using the existing Intel 82078 command engine,
when ISA FDC support is available. The named userspace I/O APIC is
``i82093aa`` (version 11h, 24 inputs), selected by
``chipset-controllers=on``. Kernel I/O APIC acceleration retains its
existing implementation. Generic and versioned machines retain their
previous defaults unless explicitly overridden.

Optional devices can be configured independently. Use
``-machine pc,help`` (or ``-M pc,help``) to list supported properties.

The existing boolean properties retain their QOM/QMP types and accept
``on`` or ``off`` as before. The corresponding policy properties add
``auto`` without breaking callers that read boolean values:

* ``chipset-controllers-mode=on|off|auto``: select named controllers,
  generic controllers, or the profile preference with accelerator fallback.
* ``fdc-mode=on|off|auto``: permit automatic floppy controller creation,
  disable it, or follow the profile and explicitly supplied legacy drives.
* ``pcmcia-mode=on|off|auto``: require the bridge, omit it, or follow the
  profile, build support and ``-nodefaults``.
* ``hpet-mode=on|off|auto``: enable, disable, or follow the profile and
  build support.
* ``pit-strict-programming=on|off|auto``: override the userspace PIT
  programming behavior, or leave its device properties unchanged.
  Explicit on/off overrides the corresponding ``-global`` device setting;
  on requires an enabled userspace PIT.

Do not specify both the legacy boolean and its policy property in the
same machine configuration; use one spelling per feature. Auto does
not mean every feature is enabled. Host battery telemetry stays
explicitly opt-in and is not controlled by an automatic policy.

For example::

    -machine pc,chipset-controllers-mode=auto,hpet-mode=off,pit-strict-programming=on
    -machine pc,fdc-mode=off,pcmcia-mode=on

The legacy spellings remain valid::

    -machine pc,fdc=off -nic none
    -machine pc,fdc=on -nic user,model=am79c970a-pci
    -machine pc,fdc=off -device isa-fdc

The ``fdc`` switch controls automatic controller creation, not explicit
``-device`` selection. Legacy ``-fda`` or ``-drive if=floppy`` requires
the automatic controller; use ``if=none`` with an explicitly attached
floppy device otherwise. ``-nic none`` suppresses default networking.
Other existing machine options (such as ``usb=off``, ``i8042=off``,
``hpet=off``) remain available. I/O APIC removal is not supported:
firmware interrupt tables and routing require separate validation.

The 82078 profile does not implement all electrical or tape-drive
features of Intel's January 1994 82078 data sheet. The 82093AA profile
uses the shared I/O APIC engine and selects the register version from
Intel's May 1996 data sheet (290566-001, section 3.2.2); it does not
claim full X-bus electrical emulation.

The CL-GD5446 uses the historical chipset compatibility implementation,
with the bundled Cirrus VGA BIOS and 4 MiB default VRAM. Neither revision
A nor revision B is implied. If the target build omits Cirrus support,
``pc`` retains its standard VGA default when available. The generic and
versioned machines retain standard VGA. Explicit display choices override
the automatic card::

    -machine pc -vga std
    -machine pc -vga cirrus
    -machine generic-pc -vga gd5446-pci
    -machine pc -vga none -device gd5446b-pci

Use a cold boot and allow the guest to redetect its graphics adapter
when changing the primary VGA device. Existing snapshots require their
original machine and graphics configuration.

The IntelliMouse profile preserves standard PS/2 operation and wheel
negotiation, but does not negotiate the five-button Explorer protocol.
To override the mouse or re-enable VMware integration, use e.g.::

    -machine pc -global i8042.mouse-model=generic
    -machine pc -global i8042.mouse-model=microsoft-ps2
    -machine pc,vmport=on

Use ``vmport=on`` only when the configured build supports VMware integration.

The ``pc`` alias previously selected ``pc-i440fx-11.1``. Existing saved
states or migration configurations should use their original explicit
versioned machine type and matching device options. All versioned i440FX
machine defaults remain unchanged. Treat the three unversioned profiles
as evolving configurations, not cross-version migration ABIs.

Laptop PC profile (``laptop-pc``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The portable profile reports SMBIOS Type 3 chassis type 09h (Laptop,
DSP0134 section 7.4.1). The existing desktop and compatibility SMBIOS
defaults are unchanged. It uses the same named PC chipset, COM, VGA and
NIC choices as ``pc``; the CL-GD5446 is a display substitute, not an
LCD panel or a mobile graphics chipset.

With default devices enabled and the Intel 82092AA built, the machine
creates its two empty 16-bit PC Card sockets. It does not automatically
insert a modem or network card. Use ``pcmcia=off`` to suppress the bridge,
or ``pcmcia=on`` to require it, including with ``-nodefaults``. A build
without the bridge omits it by default and rejects explicit activation.
The desktop profile also accepts explicit ``pcmcia=on``. To install a
different socket configuration, disable automatic creation first::

    -machine laptop-pc,pcmcia=off -device i82092aa,id=pcic,sockets=1

The floppy controller and HPET are off by default on the laptop.
Explicit ``fdc=on`` restores the Intel 82078 controller; automatic
mode also enables it when a legacy floppy drive is explicitly supplied.
``hpet=on`` restores the timer if built. The host battery remains opt-in and is never a prerequisite for running the
laptop profile on a desktop host::

    -machine laptop-pc,fdc=on -fda disk.img
    -machine laptop-pc,host-battery=on

There is no emulated embedded controller, LCD panel, lid switch, charging
hardware or ACPI control-method battery added by this profile. The host
battery bridge is still a static APM POST snapshot, not live passthrough.

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

The ``isa-serial`` device remains a generic 16550A-compatible UART.
Automatic COM ports on ``pc`` use ``ns16550a``; ``generic-pc`` and the
versioned machines keep ``isa-serial``. Serial backends, COM indexing,
I/O addresses, IRQ defaults, and explicit device selection are unchanged.
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
assignments. The optional ``acpi-legacy-irq=on`` property advertises an
edge-triggered, active-high, exclusive IRQ in ACPI (IRQNoFlags), matching
traditional PC PIC routing. The default retains the existing shared,
level-triggered, active-low descriptor for newer Windows guests. Use a
unique IRQ for each legacy-mode UART; this property only changes ACPI
reporting, not interrupt wiring or PIC programming. Use matching UART
profiles and resource properties for migration;
do not switch profiles when restoring saved state.

ISA modem compatibility profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing Hayes-compatible modem engine also supports integrated
ISA device profiles with an owned 16550A-compatible UART:

* ``hayes-accura-2400``
* ``rockwell-voice-14400``
* ``att-paradyne-dataport-3711``
* ``att-paradyne-3740`` (external modem with an owned ISA UART;
  the previous device spelling ``att-paradyne-dataport-3740`` is a compatibility alias)

For example, to install a modem on COM2 and leave COM1 available::

    -serial none -device hayes-accura-2400,index=1

The device owns its character backend; do not provide a separate
``chardev`` or a second UART at the same I/O range. The normal COM
index, base and IRQ validation applies. The guest sees a serial
controller (PNP0501), and modem identification is provided by the
existing AT-command engine. No original modem ROM, exact internal
card design, ISA PnP identifier, analog telephone DSP, fax signal
processing or real telephone connection is claimed.

For a Windows 9x COM2 detection test with the DataPort Express 3740::

    -serial none -device att-paradyne-3740,index=1,acpi-legacy-irq=on

Do not assign another device to IRQ 3 for this test. The legacy IRQ
option does not supply a modem serial Plug and Play identification packet.
The AT identification remains synthetic; an authentic modem INF match
requires separate verification. The UART reset drops DTR and RTS on
both the owned and externally attached modem paths.

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
respectively. The ``-device help`` descriptions identify the manufacturer,
chipset and bus. Adjustable properties and implementation limitations
are documented separately rather than encoded in device labels.
The ``-vga cirrus`` selector remains generic; ``-vga gd5446-pci``
selects the named PCI compatibility profile and is the default on
``pc`` when available. The chipset-specific device names are:

* ``gd5422``: CL-GD5422 ISA.
* ``gd5426``: CL-GD5426 ISA.
* ``gd5428``: CL-GD5428 ISA, sharing the generic ISA implementation.
* ``gd5430-pci`` and ``gd5430-vlb``: explicit bus variants.
* ``gd5446-pci``: historical CL-GD5446 PCI compatibility profile.
* ``gd5446a-pci``: CL-GD5446 Revision A, 16 MiB PCI aperture,
  with optional VGA relocation and GPIO disabled (CF3=1).
* ``gd5446b-pci``: CL-GD5446 Revision B, 32 MiB PCI aperture and
  4 KiB VGA/BitBLT register BAR, with optional GPIO disabled.

Both revisions share the DAC, display core and SeaVGABIOS. Their alternate
host BitBLT source paths differ: Revision A uses BC000h-BFFFFh for color
expansion; Revision B uses the second 16 MiB PCI aperture. The aperture
sizes describe PCI address space, not installed VRAM. See the November
1996 CL-GD5446 Technical Reference Manual, sections 5.10, 7.4-7.8
and Appendix A2. Revision B maps three 4 MiB framebuffer views
at BAR0 offsets 0, 4 and 8 MiB (native, word-swapped and DWORD-swapped)
and three corresponding host BitBLT source views at 16, 20 and 24 MiB.
All framebuffer views refer to the same 4 MiB physical memory; they do
not increase installed VRAM. The swapped host-source views accept aligned
DWORD writes and honor the source-select and pause controls. The 12 MiB
YUV planar-assist view remains unimplemented; 28-32 MiB is unused.
Revision A and the historical compatibility profile retain their previous
aperture behavior. Other strap configurations and silicon-specific PCI
revision ID values are not yet modeled. Revision B uses QEMU's virtual board subsystem IDs (with the upper
subsystem byte zero for the GPIO-disabled configuration) rather than
claiming a specific physical board. SR17[3] enables PCI2C subsystem ID
writes for motherboard firmware; clearing it locks the register again.
Reset restores the virtual board ID. BAR0 is non-prefetchable as specified
in TRM 7.4, BAR1 provides relocated VGA and BitBLT registers, and the
interrupt pin is zero because no interrupt is implemented.

For PCI-controlled legacy VGA resource decoding, select
``gd5446b-pci,pci-legacy-decode=on``. The historical decode default is
unchanged pending firmware boot validation. These changes address parts
of PC 97 Hardware Design Guide chapter 15 (requirements 43-46); they do
not constitute PC97 certification. Loading subsystem IDs from a physical
board ROM, DAC shadowing and display power management are not implemented
by this profile.

Revision B provides a DDC2B monitor through SR8[6,1:0], with pin
readback on SR8[7,2] as described in TRM section 8.3 and Appendix B8.
The virtual analog VGA monitor at I2C address 0x50 uses the shared
QEMU EDID generator (800x600 preferred at 60 Hz, maximum advertised
resolution 1280x1024). Its single 128-byte EDID block is read by the
Cirrus SeaVGABIOS at initialization; VBE 4F15h reports DDC2B and
returns that validated block. EEPROM mode remains disconnected.
No host monitor data is read. DDC1, E-DDC extension blocks, physical
bus timing and hotplug refresh of the firmware's cached EDID are
not implemented. Earlier Cirrus profiles keep their prior SR8
behavior. The new monitor and bitbang migration state require
cross-version migration testing before compatibility can be claimed.

Revision B honors GR31[5] to suspend an in-progress system-to-screen
BitBLT. While suspended, primary framebuffer writes bypass the host
source FIFO and the status register reports the operation as suspended
rather than busy. Clearing the pause bit resumes the existing transfer
without discarding buffered source bytes. The alternate PCI source
aperture does not consume source data while suspended. Revision B keeps
host source writes together through each DWORD bus transaction: byte-packed
color expansion carries remaining bytes into subsequent rows, but discards
unused bytes after the last row rather than writing them to the framebuffer.
Native, banked and swapped source paths use the same bounded byte feeder.
Incomplete destination pixels in host color expansion are rejected until
partial-pixel rendering is supported. The 8 KiB source line buffer is
unchanged. See TRM 5.10, 9.4.5 and
9.4.4.3. This supports concurrent framebuffer and accelerator access
used by Windows display drivers. Buffered BitBLT commands, the GR2F
source DWORD offset and hardware page-switch synchronization remain
incomplete; DirectDraw support depends on the guest driver and is not
implied by the device name.

The Revision B video window accepts CR31-CR3F, CR58-CR5A and CR5D-CR5E
with documented register masks. Rectangular playback supports RGB555,
RGB565, packed UYVY (including the alternate planar-assist byte
layout), and AccuPak YUV 4:1:1, with 8- or 15/16-bpp primary graphics. Window positions and
widths use the primary graphics pixel size; source addresses and pitch
are independent. Manual buffer selection uses CR5E[5:4]. Unscaled
horizontal playback and vertical line replication are implemented.
The host compositor clips the window to the display and checks each
source row against physical VRAM before reading it.

AccuPak playback is selected by CR3E[3:1] = 1. Each little-endian
32-bit packet represents four pixels (four five-bit Y samples and
shared six-bit U and V samples). The decoder zero-extends sample
precision by left shifting, reconstructs chroma with linear quarter
steps, and uses the existing limited-range YUV-to-RGB conversion.
The final partial packet requires a complete DWORD fetch. Chroma
interpolation at the source edge repeats the final sample without
reading row padding. Interpolation rounding and chroma phase have
not been verified against physical silicon. AccuPak capture and
YUV-to-AccuPak compression remain unimplemented. See TRM figure 9-6
and sections 9.3.2.4 and 9.5.10.

V-Port capture controls are separate from the video-window compositor.
Revision B accepts CR50-CR54, CR56-CR57 and CR5C with documented
writable masks; CR55 remains reserved. CR58-CR5A and CR5E retain
their shared capture/playback roles. GR17 accepts programmable output,
feature-connector direction and interrupt control bits, but its
V-Port interrupt status stays clear. Capture-only writes, including
CR58[6:5], do not invalidate the playback surface.

The emulated V-Port is disconnected: writing CR51[3] arms the
capture control but cannot produce input clocks, VREF transitions,
VRAM writes, automatic buffer switches or capture interrupts.
No host camera, synthetic video stream or additional PCI device is
implied. CR3F capture status remains inactive. Capture input,
decimation, luminance-only capture and compression are not implemented.
See TRM sections 6.14-6.25, 8.26 and 9.6. The existing PCI no-interrupt
board configuration is unchanged.

Window enable and buffer selection take effect at the next host display
refresh rather than an exact guest VSYNC/window-start edge. Disabling
or moving the window restores the underlying graphics at the next
refresh. Color-key/chroma-key occlusion, horizontal and vertical
interpolation, LUT video, brightness adjustment, capture,
automatic buffer switching and the video write aperture are not yet
implemented. Unsupported formats and configurations do not composite
a window. See TRM chapter 6 and sections 9.3.2 and 9.5.

The CL-GD5422 does not have a hardware BitBLT engine, as documented in
Table 2-1 of the January 1994 CL-GD542X Technical Reference Manual.
The GD5426 introduces BitBLT and the GD5428 enhances it. On profiles
that implement the engine, the existing ``blitter=off`` property can
disable emulated acceleration without introducing another device type.

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
CR27 identification 0xa0, PCI bus straps, a default of 2 MiB VRAM and a
16 MiB prefetchable BAR0. Both GD5430 bus variants accept
``vgamem_mb=1`` or ``vgamem_mb=2``. The February 1995 Alpine data book
also documents 512 KiB configurations, which require sub-MiB allocation
support not yet provided by the common VGA engine. The hardware ceiling
is 2 MiB; the larger 4 MiB configurations belong to the GD5434/GD5436.
The configured memory size determines the reset scratch-register value
and address mask; the PCI BAR and VLB window sizes are independent of
installed VRAM. It models the primary framebuffer aperture only,
with relocatable VGA I/O disabled, and does not expose the GD5446
dedicated MMIO BAR or high BitBLT aperture. The GD5430 PCI and VLB
variants both omit GR12-GR15, GR33 solid-fill and GR31 auto-start.
Other chipset-specific accelerator features and clocks are incomplete.

For a legacy PC guest, replace the existing primary VGA configuration
with::

    -vga none -device gd5430-pci

The GD5430 PCI profile uses the bundled SeaVGABIOS Cirrus ROM
(``vgabios-cirrus.bin``). With the normal PCI ROM BAR enabled, QEMU's
existing default-ROM loader adjusts the PCI device ID from 00b8 to
00a0 and updates the checksum in the loaded image. The ROM file
and SeaBIOS sources remain unchanged. A user-supplied compatible ROM
can still be selected with ``romfile=PATH``; an empty ``romfile=``
disables the ROM. Explicit ROM files are not patched by the default
ROM loader. The legacy ``rombar=0`` firmware path bypasses this
PCI header patching and has not been validated for GD5430.

The header adaptation alone does not establish boot or guest-driver
compatibility; GD5430 mode setup still requires runtime validation.
Keep the same device type and VRAM configuration when saving/restoring
a VM. Use a cold boot to change chipsets. The GD5446 precise timing
property is not available on GD5430.

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

The PIIX-family PC machines support an explicit controller selection::

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

The default is on for ``pc`` when userspace PIC/PIT emulation is
available, and off for ``generic-pc`` and the versioned i440FX machines.
When Xen or an enabled in-kernel PIC/PIT is in use, the implicit
hardware-profile default falls back to the compatible controller set;
explicitly requesting ``chipset-controllers=on`` still reports an error.
Either profile accepts an explicit override. Use a cold boot when
changing the selection, and keep it consistent across saved-state or
migration endpoints. Do not add duplicate standalone timers, DMA
controllers or interrupt controllers.
CPU, RAM, RTC, storage, display and NIC selections are unchanged. The option
does not select a physical motherboard model or change Windows driver
names by itself.

PC speaker and system control port
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The motherboard speaker (``isa-pcspk``) retains its PIT channel 2
connection and port 61h. Bit 4 approximates normal ISA refresh
cycles by toggling every 15 microseconds of virtual time, independently
of the number of reads. This is not cycle-accurate ISA refresh arbitration
or a model of reprogrammed PIT channel 1. In PIT modes 2 and 3,
low GATE holds OUT high; raising GATE restarts the period. Port 61h
bit 5 reports the PIT output.

The mode-3 audio path uses unsigned PCM centered at 128, with
fractional phase maintained across partial writes. Unsupported modes
and out-of-band divisors supply silence. The existing 32 kHz rate
and 1792-byte buffer are unchanged. Reset mutes the voice; loading
speaker state reconstructs the audio voice activity from the PIT gate
and speaker-enable bit. The old refresh byte remains in the migration
stream for layout compatibility, but is no longer used for readback.
Cross-version migration and actual audio output require runtime testing.
NMI source controls/status, direct one-bit audio and other PIT audio
modes remain unimplemented. See Intel 82371FB/82371SB (May 1996),
sections 2.5.5.1 and 3.4.2.

AMD PCnet Ethernet controllers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The existing ``pcnet`` PCI NIC remains the compatibility profile.
``am79c970a-pci`` selects the AMD Am79C970A PCnet-PCI II profile
(AMD publication 19436, revision E, June 2000). Both expose PCI
1022:2000 and CSR88/89 chip part number 2621h, a 32-byte I/O
BAR and a 32-byte memory BAR. The explicit model retains the
existing option ROM and network backend support, but implements
the documented CSR100 reset value 0600h, STOP/SPND write guards
for CSR46/47/100 and BCR22, and ignores CSR47 bits 3:0.
Its descriptor poll counter advances in approximately 30 ns clock
periods instead of multiplying elapsed nanoseconds, and rebases
the timestamp at each update. PCI cache-line size and configuration
offsets 40h-FFh are reserved.

The CSR100 timeout is currently register storage only; PCI bus
arbitration and timeout error signaling are not cycle accurate.
BCR22 aliases in PCI configuration space remain to be synchronized.
The explicit model interprets the migrated timer timestamp differently
from the compatibility profile: use the same device model at both
migration endpoints. Do not substitute an ISA NIC merely because
Windows uses a shared PCI/ISA driver name. Am79C960, Am79C961,
Am79C961A and Am79C970 require separate hardware implementations.

PCI and ISA host topology
~~~~~~~~~~~~~~~~~~~~~~~~~

The i440FX machines already instantiate the Intel 82441FX PCI and memory
controller (8086:1237, ``i440FX``) through the host-facing
``i440FX-pcihost`` object. The default ISA bridge is Intel 82371SB PIIX3
(8086:7000, ``PIIX3``); it owns the ISA bus and its integrated devices.
The ``PCI`` and ``ISA`` bus types describe reusable interconnect
infrastructure, not additional guest-visible generic bridges. In particular,
``isabus-bridge`` is not instantiated on this PCI-based machine.
The host-facing QOM path, PCI bus and ISA bus names remain unchanged.

The named ``pc`` and ``laptop-pc`` profiles now enable the existing
``strict-timing-config`` property and the new
``strict-reserved-config`` property of the native 82441FX function.
The former restores the documented DBC, DRAMT and CLT register reset
values and writable masks; the latter clears reserved configuration
bytes and ignores writes to them, including on reset and state load.
See Intel 440FX PCIset datasheet 290549-001 (May 1996), Table 1 and
sections 3.2.13, 3.2.17 and 3.2.22. These controls are register-level
accuracy improvements, not cycle-accurate memory or PCI bus timing.

The generic and versioned profiles keep the previous register behavior.
For a controlled comparison, override either property independently::

    -machine pc -global i440FX.strict-timing-config=off
    -machine pc -global i440FX.strict-reserved-config=off

The FX masks do not apply to the experimental 440BX or IGD passthrough
host functions. The legacy coreboot RAM-size handoff at offset 57h,
PAM mapping, PCI addresses, PIIX3 routing and DMA wiring remain unchanged.
SMRAM lock/reset and data-versus-code access behavior, complete DRAM
configuration, actual DBX transactions and PCI arbitration still require
separate work. PIIX3 with ACPI enabled also uses a compatibility PIIX4
PM function rather than a fully faithful original PIIX3 package.

PIIX3 PCI-to-ISA bridge configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Intel 82371SB function 0 (8086:7000) uses the type-0
multifunction header, class 060100h, and has no PCI BARs, subsystem
IDs, expansion ROM or interrupt line. The Command register's I/O,
memory and bus-master bits are hardwired to one. The Special Cycle
Enable and SERR Enable bits are writable; the remaining bits are
reserved or unimplemented. Status reports medium DEVSEL timing and
implements the documented write-one-to-clear error bit mask.
Special-cycle broadcasting and delayed-transaction error signaling
are not implemented by these register changes.

See Intel 82371FB/82371SB datasheet (May 1996), Table 2 and
sections 2.2.3-2.2.7. PIIX4 and other PCI functions retain their
existing header behavior. Older PIIX3 migration streams with
generic header values are normalized on load; cross-version
migration requires validation.

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

ACPI root bridge identities
---------------------------

PCI, PCIe and CXL root bridges share the PNP0A03 hardware or compatible
ID in the x86 ACPI namespace. Their persistent ``_UID`` values must be
distinct. The primary PCI root retains its machine-version-specific UID;
expander bridges retain their bus-number-based UIDs. QEMU rejects an
ACPI-enabled configuration that would publish a duplicate root UID,
rather than silently renumbering a bridge. For example, machine types
5.1 and older use primary UID 1; choose an unused expander ``bus_nr``
other than 1. Existing valid configurations and ACPI-disabled guests
are unchanged. This does not alter the identities of ISA devices.

See ACPI Specification 6.4, section 6.1.12 (_UID):
https://uefi.org/htmlspecs/ACPI_Spec_6_4_html/06_Device_Configuration/Device_Configuration.html

Legacy serial compatible identifiers
------------------------------------

On current PC machine types, a FIFO-capable ISA UART publishes
``_HID = EisaId("PNP0501")`` and ``_CID = EisaId("PNP0500")`` on the
same ACPI device. The fallback identifies the standard COM programming
interface; it does not create a second serial port. Non-FIFO UARTs
already use PNP0500 as their HID and do not repeat it as a CID. The
existing COM index UID, resources, and migration state are unchanged.
PC compatibility machine types 11.0 and earlier retain the previous AML
by default. The device property ``acpi-legacy-cid`` allows an explicit
override (for example, ``-global isa-serial.acpi-legacy-cid=on``).

ACPI 1.0 section 6.1.2 defines compressed EISA compatible identifiers;
the PC 98 System Design Guide recommends PNP0500 for standard COM ports
and PNPB003 for SB16-compatible sound devices. Do not advertise the
latter on an invented ACPI audio node for an independently enumerated
ISA PnP card. Preserve PCI and PCIe root bridge compatible IDs and do not
introduce aliases that claim unsupported hardware functionality.

References:

* https://uefi.org/sites/default/files/resources/ACPI_1.pdf
* https://techshelps.github.io/MSDN/PC98/HTML/03bas98_3.htm

Diagnosing legacy guest clock drift
-----------------------------------

The host monotonic clock, virtual clock, PIT output and PIC interrupt
acknowledgment are separate stages. On macOS the ordinary host clock
already uses CLOCK_MONOTONIC. Changing to raw Mach time without matching
pause, suspend and migration semantics is not a timer-delivery fix.

For a short diagnostic boot, append::

    -trace enable=pit_irq_deadline -trace enable=pic_interrupt

The PIT trace records its scheduled virtual nanosecond deadline and the
actual virtual time when the callback is dispatched, along with mode and
divisor. Repeated deadlines dispatched at almost the same actual time can
indicate scheduler delays; the PIC trace shows acknowledged vectors
(including BIOS IRQ0 at 08h, or the guest's remapped vector). Neither trace
changes timer rate or injects extra interrupts. Trace only briefly because
logging itself affects timing. Compare against the same guest's RTC time
and host elapsed time while the VM is running. The diagnostic requires a
trace backend that emits these events.

The named motherboard ``i8254`` in ``pc`` and ``laptop-pc`` enables
``strict-programming`` by default. After a new control word the counter
holds the initial OUT level (low in mode 0, high otherwise) and cancels
the previous IRQ deadline until the complete initial count is written.
This avoids reusing an obsolete divisor while the guest writes the
low and high bytes. The null-count status, gate handling, HPET legacy
IRQ handoff and restored timer deadline respect this waiting state.
Generic and versioned profiles retain their previous programming
behavior. For a controlled comparison, disable only this change::

    -machine pc -global i8254.strict-programming=off

The equivalent machine-level override is
``-machine pc,pit-strict-programming=off``.

The oscillator remains 1193182 Hz, with guest-programmed divisors and
absolute virtual-clock deadlines. The BIOS divisor 65536 produces about
18.2065 Hz, while divisor 1193 gives about 1000.15 Hz. These are not
guarantees of real-time host dispatch or guest IRQ acknowledgment.
Overdue edges can still be dispatched together, and the PIC may merge
unacknowledged requests. Do not alter the oscillator or inject synthetic
interrupts to compensate for host contention. For PIT-only diagnostics,
``-machine pc,hpet=off`` bypasses the HPET legacy routing path.
Intel 8254 datasheet, modes 0-3 and figures 15-18, documents the initial
OUT levels and periodic operation. The modeled count-load epoch is still
immediate, not a cycle-accurate oscillator phase; deferred reloads
without a new control word are not addressed here.

Modes 4 and 5 now produce an active-low strobe at the modeled terminal
count, instead of an inverted pulse. The existing immediate count-load
epoch is unchanged; deferred loads, gate pause and mode 5 trigger arming
still require separate work. This is a polarity repair, not a confirmed
fix for periodic Windows clock drift. See Intel 8254 datasheet figures
19 and 20 (https://www.scs.stanford.edu/20wi-cs140/pintos/specs/8254.pdf).

macOS background execution
--------------------------

Cocoa window focus controls input capture, not VM run state. The display
backend requests an NSProcessInfo user-initiated activity allowing idle
system sleep while the VM is running. This prevents App Nap from deferring
ongoing emulation solely because the application is inactive. A VM state
callback acquires or releases the token on resume or stop, and display
cleanup unregisters the callback and releases any outstanding token.
There is one activity per Cocoa process, not one per guest display.
No real-time scheduling priority, clock multiplier, timer injection or
sleep-prevention assertion is requested.

The default is ``-display cocoa,background-run=on``. For a comparison,
repeat the same test with ``background-run=off`` (do not change the guest
machine, RTC mode or CPU model). In Activity Monitor enable the App Nap
column, then switch to another application or hide all QEMU windows for
several minutes. Compare guest elapsed time and the PIT deadline trace
with host elapsed time; use QMP query-status to distinguish a stopped VM
from a running but delayed VM. An explicitly paused VM should release the
activity; after resume it should reacquire it. Actual system sleep and
host resource contention may still delay guest execution.

Reference: Apple Energy Efficiency Guide for Mac Apps, Prioritize Work
at the App Level:
https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/PrioritizeWorkAtTheAppLevel.html


SST parallel system ROM chips
-----------------------------

PCI PC machines can opt into one of three SST39SF parallel NOR devices::

    qemu-system-i386 -M pc,rom-chip=sst39sf020a -bios bios-256k.bin

The supported models are ``sst39sf010a`` (128 KiB), ``sst39sf020a``
(256 KiB), and ``sst39sf040`` (512 KiB). Each has an 8-bit data bus,
4 KiB erase sectors and its own JEDEC identification. The source is
Microchip data sheet DS20005022F, sections 3 and 4.

The image must fit the physical chip; shorter images are right-aligned
with erased (0xff) padding, preserving the reset vector. The chip is
mapped below 4 GiB and the top 128 KiB is aliased into the legacy BIOS
window, subject to chipset PAM controls. Programming and erasure are
volatile within the VM: the original BIOS file is never modified.
Typical program and erase intervals are modeled using virtual time.
Electrical behavior and flash wear are not modeled.

The default ``rom-chip=auto`` retains the existing raw BIOS or pflash
configuration. Explicit SST selection cannot be combined with pflash
or confidential guests and is not available on ISA-only PC machines.
A 128 KiB chip requires a BIOS image of at most 128 KiB.


PC IDE drive profiles
---------------------

On the hardware-oriented ``pc`` (also ``pc-hardware``) machine, automatic
IDE hard disk attachment through ``-hda``, ``-hdb`` or ``-drive if=ide``
uses ``ide-hd-model=auto``. This chooses an existing historical ATA profile
only for an exact native capacity match:

* Seagate ST31640A: 3,175,200 sectors (1,625,702,400 bytes).
* Seagate ST32140A: 4,127,760 sectors (2,113,413,120 bytes).
* IBM DTTA-351010: 19,807,200 sectors (10,141,286,400 bytes).

These values come from Seagate's Medalist 1640/2140 product manual
36314-21, section 1.1.1, and IBM's DTTA OEM specification S00K-0286-02,
figure 1. Other sizes retain the generic ATA device; no image is resized.
The profile can be explicitly selected, including for a custom image
size within the historical LBA28 addressing range::

    qemu-system-i386 -M pc,ide-hd-model=ibm-dtta-351010 -hda disk.img

Use ``ide-hd-model=ide-hd`` to retain the generic hard disk behavior.
The desktop PC legacy optical attachment now defaults to
``toshiba-xm-6202b``, a CD-only compatibility profile. Toshiba announced
the ATAPI drive on 12 November 1997, and the archived 1999 Disk/Trend
specification lists a 32x maximum data rate of 4.8 MB/s, a 256 KiB
cache and PIO mode 4. The profile reports those values, uses the observed
ATA model string ``TOSHIBA CD-ROM XM-6202B``, and supplies Toshiba INQUIRY
identity fields. DMA is conservatively not advertised or accepted:
Linux's libata has a model-specific NODMA quirk. The original firmware,
mechanical seek delays, speed throttling and physical cache are not
emulated; host I/O buffers and batching are unchanged.

References:

* https://www.global.toshiba/ww/news/corporate/1997/11/pr1201.html
* https://www.bitsavers.org/pdf/toshiba/cdrom/specs/Toshiba_1999_Specs.pdf
* Linux drivers/ata/libata-core.c, XM-6202B DMA quirk.

Select the generic optical drive for DVD media or DMA workloads::

    qemu-system-i386 -M pc,ide-cd-model=ide-cd -cdrom install.iso

As for the Oak profiles, cooked images are classified using the existing
CD/DVD size heuristic. To select an experimental Oak controller profile::

    qemu-system-i386 -M pc,ide-cd-model=oti-910 -cdrom install.iso

The alternate ``oti-011`` profile has early NEC CDR-260 identification
behavior. These are compatibility profiles, not complete vendor firmware
or mechanical timing emulations. An explicit ``-device`` still controls
its own model independently. The ``generic-pc``, ``laptop-pc``, Q35 and
versioned machine types retain their previous automatic drive behavior.


CPU-specific SeaBIOS builds
---------------------------

The matching X86-Firmware fork supports explicit compiler CPU profiles
without changing its calling conventions or ROM layout policy. With the
updated firmware source selected, build optional 256 KiB images using::

    make -C roms seabios-pentium
    make -C roms seabios-pentium-mmx

Each image uses a separate build directory and retains the same device
configuration as the regular 256 KiB BIOS. Select the P55C image explicitly::

    qemu-system-i386 -M pc -cpu pentium_mmx \\
        -bios pc-bios/bios-pentium-mmx-256k.bin -smp 1

The P54C image is named ``bios-pentium-256k.bin``. The firmware build
uses the corresponding ``-march`` and ``-mtune`` while disabling automatic
MMX/SSE generation to protect guest register state. The i386 baseline
remains unchanged. These optional images are not yet Meson default
outputs, bundled prebuilt blobs, or automatically selected by CPU model.
Use the regular BIOS if the selected compiler cannot build the CPU
profile. Compiler tuning does not model a CPU's cycle rate, implement
VME, or guarantee faster TCG execution. Validate ROM size and cold boot
before adopting a CPU-specific image as a machine default.
