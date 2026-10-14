RCA SelectaVision SFT100 front-panel emulation
===============================================

The real SFT100's **main controller is a Mostek MK3870**, implementing
the **Fairchild F8 instruction-set architecture** with 2 KB of mask ROM.
The Zenith VP2000 is documented as an SFT100-based clone; its actual
chip markings and ROM revision still require direct verification.
See ``ced-mk3870.rst`` for primary/secondary evidence, the unresolved
RCA stock-number discrepancy, and CPU integration requirements.
No ``target/f8`` backend or ROM execution is implemented yet.

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

Decoded mono audio output (2026-10-14)
------------------------------------

The original SFT100 delivers monaural sound extracted from a **716 kHz
audio FM carrier** on the capacitance disc. RCA service literature shows
a band-pass filter, FM demodulator and audio routing toward the VHF RF
modulator. The later 905 kHz stereo carrier is **not** an SFT100 stereo
output capability. Independent engineering reference:
https://www.stason.org/TULARC/pc/videodisc-selectavision/1-3-What-are-the-technical-specifications-of-the-RCA-VideoDi.html
RCA SFT100 service reference:
https://www.manualslib.com/manual/4050471/Sams-Rca-Sft100w.html

The QOM SFT100 now exposes an ``audiodev`` property and opens a QEMU
output voice with **48 kHz, signed 16-bit, mono, host-endian PCM**.
This is a *host interface convention*, **not** the rate or encoding
recorded in the disc groove. The decoder (not implemented) must
supply already demodulated, mono, resampled PCM using
``rca_sft100_submit_pcm()`` in the emulation thread.

``ced-sft100-audio.c`` provides a fixed 4096-frame FIFO with bounded
partial writes and no dynamic allocations. Playback is enabled only
while the SFT100 is in active normal PLAY. Pause, search, rapid access,
power-off, and end-of-side mute playback and discard stale decoded
samples. Audio voice setup failures abort device realization, clean
up the migration blocker, and do not leave a running timer.

The original SFT100's **RF television output** is not yet emulated;
QEMU host sound is a diagnostic output route and must not be
mistaken for an RCA rear-panel analog audio jack. Real sample data
can be heard only after a decoder/media source submits PCM; no
Disney recording, test song, or FM signal is synthesized.

Test with ``meson test test-ced-sft100-audio`` in the configured
QEMU build. The isolated test also has a QOM/audio callback mock
covering partial backend writes, muting, and realize cleanup.

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
