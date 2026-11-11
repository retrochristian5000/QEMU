RCA CED media descriptors and player transport
===============================================

This is an initial reusable RCA SelectaVision Capacitance Electronic Disc
(CED) **transport core**, not a working analog video decoder or a complete
Zenith VP2000 emulator.  A CED is a grooved, capacitively read analog disc;
it is neither LaserDisc nor CD-ROM and has no ISO-9660 filesystem.

Source provenance
-----------------

* RCA, *SelectaVision SFT100 Service Data*, pp. 3-5: loading, stylus,
  pause and search, DAXI, channel 3/4 RF output.  SFT100 behaviors should
  not automatically be treated as Zenith VP2000-specific specifications.
  https://www.manualslib.com/manual/3552449/Rca-Selectavision-Videodisc-Sft-100.html
* RCA, *RCA Engineer*, Nov-Dec 1981, buried-subcarrier/DAXI technical
  discussion: https://www.worldradiohistory.com/ARCHIVE-RCA/RCA-Engineer/1981-11-12.pdf
* CED Magic, engineering references and disc catalog:
  https://www.cedmagic.com/

Emulated today
--------------

``hw/block/ced.c`` and ``include/hw/block/ced.h`` implement:

* Media validation for NTSC, audio-profile and DAXI-*knowledge* metadata.
* A fixed 24-byte **WHP-CED1** synthetic *descriptor*, not an authentic
  RCA disc image, encoded or decoded solely to make deterministic tests.
* Caddy loading and retention, physical side selection on re-insertion,
  stopping and ejection, playing and pausing with stylus/video/audio gates.
* An RCA SFT100 transport profile with *approximate* 480-field startup
  (about eight seconds), 16x forward/reverse visual-search position advance,
  silent rapid seek, and end-of-side clamping.  Rapid seek completion is
  currently abstract, without mechanical travel-duration modeling.
* CH3/CH4 switch state (not actual RF transmission).

The US format has **eight television fields per disc revolution** and a
nominal spindle speed of **450 RPM**.  Television timing is kept as the
exact rational ``60000/1001`` fields/sec.  Never force that precise field
clock into the nominal 450 RPM figure.  The disc-native chroma signal is
approximately 1.53 MHz; NTSC television output uses approximately
3.58 MHz.  The code deliberately does **not** equate those signals.

WHP-CED1 test descriptor layout (version 1)
--------------------------------------------

All byte offsets are zero-based; 32-bit integers are little-endian.

========== =============================================================
Offset     Meaning
========== =============================================================
0..7       ASCII ``WHP-CED1`` magic
8          Descriptor version (1)
9          Video system (1 = North American NTSC CED)
10         Audio (0 unknown, 1 mono, 2 stereo, 3 independent channels)
11         Number of sides (1 or 2)
12         DAXI status (0 unexamined, 1 presence verified; no payload)
13..15     Reserved, must be zero
16..19     Number of logical fields on side 1 (nonzero)
20..23     Number of logical fields on side 2 (zero if absent)
========== =============================================================

This descriptor intentionally carries **no** movie video, audio, waveform,
DAXI packets, UPC, title, or packaging artwork.  It is used to test a drive
without redistributing copyrighted film content or inventing an official
CED digital-ripping standard.

Not yet emulated
----------------

* Electrical capacitance pickup, FM video/audio demodulation, 1.53 MHz
  buried chroma comb filtering, DAXI bitstream and player microprocessor.
* Physical motor acceleration, seek travel time, servo feedback, defects,
  stylus wear or groove physics.
* Analog NTSC composite encoding, antenna pass-through, and VHF RF carrier
  synthesis; these require a later output stage coupled to the existing
  ``analog-video`` descriptions.
* Guest-visible front-panel integration, machine-specific control/firmware,
  actual CED captured media playback and migration/snapshot support.

RCA SFT100 standalone appliance wrapper
---------------------------------------

The registered QOM device ``rca-sft100`` models RCA's OFF/LOAD-UNLOAD/PLAY
lever, direction-based search controls, caddy, TV output source selection
and rational virtual-clock playback. It is **not** command-line creatable:
there is no AV playback path, television attachment or machine-specific
front-end. See ``ced-sft100.rst`` for interfaces and explicit limits.
Migration and snapshots are blocked until player state has a VMState
schema. The legacy CED transport helpers remain reusable independently.

The core is deliberately independent of a CPU architecture.  A CED disc is
not a machine target and should not create a ``qemu-system-ced`` binary.
RCA SFT100 and Zenith VP2000 device-specific electrical differences remain
an open documentation question.  Disney's RCA CED releases are historically
useful compatibility references, not bundled test footage.
