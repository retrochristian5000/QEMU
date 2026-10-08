Creative Music System / Game Blaster (CT1300)
=============================================

The historical Creative Music System (C/MS) and Radio Shack Game Blaster are
the same class of *8-bit ISA programmable sound-generator card*, **not**
synonyms for Sound Blaster 16.  They contain two Philips SAA1099 sound chips
(Creative's CMS-301 stickers), each with six tone/noise voices and per-output
amplitude controls.  The model is named ``gameblaster`` and does not
emulate a Yamaha OPL, 8-bit Sound Blaster DSP, ISA DMA, or a PIC IRQ.

Example::

  qemu-system-i386 -M pc -audiodev none,id=snd0 \
    -device gameblaster,audiodev=snd0,iobase=0x220

Select a real host audio backend to hear the PSG output.

Guest ISA port map, relative to ``iobase`` (default 0x220):

======= ==============================================================
Offset  Function
======= ==============================================================
+0      SAA1099 chip A data (write only)
+1      SAA1099 chip A register selection (write only)
+2      SAA1099 chip B data (write only)
+3      SAA1099 chip B register selection (write only)
+4      Common identification read value 0x7f (limited emulation)
+6/+7   CT1302 identification latch write
+A/+B   CT1302 identification latch readback
Other   No implemented function (reads return 0xff)
======= ==============================================================

The card occupies a full 16-byte ISA window.  Historically documented
jumper-selectable bases are 0x210, 0x220, 0x230, 0x240, 0x250 and 0x260.
No IRQ or DMA line is allocated by this device.  Do not attach both this
card and another Sound Blaster-family card at the same I/O base; the
physical ISA address ranges would overlap.

The first-stage audio implementation covers independent chip register
selection, frequency/octave settings, 12 tone voices, left/right volume,
noise and an approximated eight-shape envelope engine, software PCM rendering,
hardware reset and save/restore of chip state.

**Known limitations:** full SAA1099 analogue output characteristics,
envelope edge timing, the CT1302's shifting identification sequence (used
by some CMSDRV.COM versions), and period-correct analog mixing are **not
yet verified against the original hardware**.  A fixed 0x7f response at
+4 is insufficient for all software.  Treat this as an early functional
chip/ISA model rather than complete Game Blaster compatibility.

Sound Blaster 1.0 historically combines OPL2 and digital sound hardware
with populated CMS chips.  Sound Blaster 1.5 and 2.0 have optional CMS
hardware with differing upgrade requirements; SB Pro/16 are distinct.
Do not expose CT1302 identification behavior on the Sound Blaster 1.x
DSP ports.  Sharing the two-SAA1099 sound core with a future SB 1.0
board implementation is a separate task and requires exact I/O composition.

Evidence: Philips SAA1099 register definitions; Creative CT1300 reverse
engineering (https://github.com/schlae/game-blaster); game-specific
observations in the CMS hardware survey at
https://nerdlypleasures.blogspot.com/2012/10/all-you-ever-wanted-to-know-about.html.
