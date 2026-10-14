RCA SelectaVision SFT100 front-panel emulation
===============================================

The QOM type ``rca-sft100`` is a non-user-creatable standalone appliance
model backed by the existing CED transport.  It does **not** add fictional
ISA, PCI, IDE, CD-ROM or memory-mapped interfaces to a physical 1981 RCA
player.  A real physical CED disc records analogue capacitance variations;
``WHP-CED1`` remains a 24-byte *test descriptor only*, not a disc capture.

Evidence: RCA SFT100 owner's manual, pages 4, 5, 11 and 14
(https://www.manualslib.com/manual/4315910/Rca-Selectavision-Sft100.html)
and RCA's service documentation.  RCA documents an OFF / LOAD-UNLOAD /
PLAY function lever, hold-type FWD and REV visual-search and rapid-access
buttons, a pause toggle, VHF antenna in/out and switchable channels 3/4.

Implemented in ``hw/block/ced-sft100-control.c``:

* Lever states and guarded caddy insertion/ejection; the disc is retained
  while switching to OFF and must be removed and reinserted to flip sides.
* PLAY startup approximation and stylus/motor/audio/video states.
* Momentary forward/reverse 16x visual search, pause toggle, abstract
  rapid-access positioning, end-of-side behavior, and CH3/CH4 selection.
* Rational 60000/1001 fields/sec accumulation using integer operations;
  no timestamp multiplication overflow or floating-point clock drift.
* Logical pass-through versus player RF source selection; no synthesized
  carrier.  Audio/video status flags are not actual signals.

``hw/block/ced-sft100.c`` adds the QOM device and virtual-clock timer, with
read-only state properties and a C-only front-panel interface in
``include/hw/block/ced-sft100.h``.  It is intentionally not advertised as
``-device rca-sft100``: there is no television attachment/AV renderer or
external control surface yet.  The device blocks migration/snapshots until
its VMState and virtual media restore semantics are implemented, avoiding
silent state loss.  Tests cover the controller separately from its QOM
wrapper.  The SFT100 wrapper is not yet connected to a QEMU machine.

Explicit limitations
--------------------

* No RCA microcontroller ROM, electrical pin map, electronics-level servo,
  turntable spin-up simulation, damaged-groove handling or DAXI decoding.
* Rapid access takes a resolved field target: duration and direction of
  real button holds remain unmodeled.  The 16x reverse/forward model and
  eight-second startup are operating approximations, not firmware cycles.
* No waveforms, buried chroma, FM demodulation, NTSC encoder, RF TV
  modulator or Disney media content.  No custom ``qemu-system-ced`` target.
* No Zenith VP2000 model-specific claims; these require separate Zenith
  wiring/service-documentation evidence.
* Run ``meson test test-ced test-ced-sft100`` in a complete QEMU build;
  local isolated tests are not a substitute for that integration check.
