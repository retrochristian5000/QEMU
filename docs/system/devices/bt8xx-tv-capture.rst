Brooktree/Conexant Bt8xx analogue TV capture family
===================================================

The Brooktree Bt848/Bt878 generation is a useful first family for analogue TV
capture emulation because period boards expose a clean separation between the
common PCI video-capture silicon and board-specific tuner, audio and auxiliary
parts.

Do not model a Bt8xx board as one magic ``TV tuner`` device.  The RF tuner,
baseband video decoder/capture engine, audio decoder, input muxes, EEPROM and
other companion devices can be separate pieces of hardware even when sold on
one PCI card.

Family map
----------

Linux's long-lived ``bttv`` driver groups the following closely related capture
parts::

    Brooktree/Conexant Bt8xx video capture
    |
    +-- Bt848
    +-- Bt848A
    +-- Bt849
    +-- Bt878
    `-- Bt879

The exact silicon differences need to be taken from the relevant data sheets
before QEMU exposes variant-specific registers or PCI identities.  A common
capture/decoder core with explicit chip profiles is preferable to copying one
controller implementation for every member.

Board composition
-----------------

A typical analogue-TV board can be represented as::

    antenna / cable
          |
          v
       RF tuner -------- I2C/programming
          |
          v
    IF / demodulator
          |
          +---------------------- audio path
          |
          v
    composite / S-Video
          |
          v
       Bt8xx video decoder
          |
          v
      crop / scale / capture
          |
          v
        PCI DMA -> guest memory

Additional board devices can include EEPROMs, GPIO-controlled muxes, stereo or
NICAM audio decoders, teletext/VBI hardware, radio-tuner support and remote
control circuitry.

The Linux ``bttv`` documentation makes the same hardware distinction: video is
largely common to the Bt848/849/878/879 family, while boards differ by tuner,
sound decoder, EEPROM and other companion components.  QEMU board models should
preserve that composition rather than moving board-specific behaviour into the
Bt8xx core.

Relationship to analogue-video signals
---------------------------------------

The Bt8xx video side should consume the shared analogue-video description from
``hw/display/analog-video.h`` rather than receiving a framebuffer labelled
``NTSC`` or ``PAL``.

The useful boundary is:

* RF tuner/channel model selects and demodulates the broadcast signal;
* the resulting baseband signal carries scan timing and a composite-colour
  encoding profile;
* the Bt8xx decoder decides whether it can lock/decode that signal;
* the capture engine then samples, crops and scales it into a guest-visible
  raster; and
* the PCI DMA engine writes that raster and ancillary data to guest memory.

This allows the same composite/S-Video input path to work without any RF tuner,
and lets multiple tuner modules feed the same capture silicon.

Regional standards are board profiles
--------------------------------------

Period Bt8xx boards were sold in many regional configurations.  The bttv card
inventory records, among others, NTSC-M, PAL-B/G, PAL-I, PAL-D/K, PAL-N,
PAL-B/H, PAL-M and SECAM variants.

Those names describe more than one layer.  For QEMU:

* 525/59.94 versus 625/50 belongs to scan timing;
* NTSC/PAL/SECAM baseband variants belong to the composite decoder profile;
* B/G, D/K, I, L, M, N and similar broadcast-system distinctions belong to the
  RF/audio/channel layer where applicable; and
* a particular card model selects the tuner/decoder combination actually
  installed on that board.

Do not make ``-device bt878,standard=pal`` stand in for all of this.  A board or
source object should identify the real signal and hardware configuration.

Tuner modules
-------------

The RF tuner is not part of the Bt8xx core.  Linux documentation for historical
boards records Philips and TEMIC tuner modules and examples built from Philips
TDA573x mixer/oscillator parts with TSA55xx I2C synthesizers.  Different board
revisions with the same Bt8xx capture chip can therefore require different RF
models.

A reusable tuner abstraction should eventually expose at least:

* tuned RF frequency;
* regional/channel-plan interpretation outside the generic tuner core;
* RF lock / no-lock state;
* supported broadcast-system bandwidth/modulation properties;
* recovered video baseband signal; and
* recovered audio/IF output where the real module provides it.

Do not initially synthesize every historical channel plan in the Bt8xx device.
Channel numbering belongs above frequency tuning and can be added as reusable
regional data once an actual machine/card needs it.

Audio is independent
--------------------

Bt8xx board audio is particularly important evidence against a monolithic
model.  Linux documents boards using external MSP34xx, TDA98xx and related
sound-processing parts, with board-specific GPIO routing and muxes.

The video-capture model should therefore not infer stereo/NICAM/FM/AM audio from
its colour standard.  A board composes the appropriate sound hardware and routes
its output to the guest-visible audio path.

Initial implementation roadmap
------------------------------

A conservative first implementation is:

#. Keep ``AnalogVideoSignal`` as the shared baseband input description.
#. Add a Bt848/Bt878 family PCI core with explicit chip profiles, register state,
   interrupt handling and DMA plumbing before modelling a specific retail card.
#. Implement composite and S-Video input selection and decoder lock against the
   supported analogue-video profiles.
#. Implement capture geometry and DMA as a separate stage from analogue timing;
   sampled frame dimensions are output configuration, not the TV standard.
#. Add one documented capture-only board profile first.  This tests the decoder
   and DMA without RF or audio dependencies.
#. Add one well-documented tuner board by composing a real RF tuner module,
   EEPROM/GPIO wiring and any required audio decoder around the same Bt8xx core.
#. Add Bt848A/Bt849/Bt878/Bt879 differences only when their data sheets or
   operating-system drivers establish the guest-visible distinction.
#. Add VBI/teletext and board-specific audio after ordinary video capture is
   stable.

A capture-only board is intentionally earlier than a tuner board: it lets QEMU
validate composite/S-Video decoding and DMA without pretending that RF tuning,
regional channel plans and television sound are already solved.

QEMU status
-----------

The WHP fork currently has no Bt848/Bt878 device model.  The new analogue-video
signal layer provides the first shared prerequisite but does not itself emulate
colour decoding, RF tuning or capture DMA.

The family should be implemented under a reusable media/display boundary rather
than directly in a GUI frontend.  Host Cocoa/GTK/SDL presentation is not part of
the guest-visible TV capture device.

Reference controls
------------------

Useful implementation controls include:

* Linux kernel ``bttv`` documentation and the corresponding driver source for
  the Bt848/Bt848A/Bt849/Bt878/Bt879 family and historical board composition;
* Brooktree/Conexant data sheets for the exact capture-chip member being
  implemented;
* tuner-module and companion-audio data sheets for the selected retail board;
* ITU-R BT.1700 for composite analogue video characteristics; and
* ITU-R BT.1701 for radiated analogue television characteristics.

Driver compatibility is useful evidence for family structure, but it does not
replace the chip data sheet when deciding register resets, timing, DMA details
or undocumented variant behavior.
