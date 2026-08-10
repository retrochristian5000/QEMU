Analogue video signal modelling
===============================

Analogue television and monitor emulation needs to preserve distinctions that
are often hidden by framebuffer-oriented software.  In particular, NTSC, PAL
and SECAM must not be used as aliases for framebuffer sizes or for a particular
number of scan lines.

ITU-R BT.470 separates conventional analogue television into baseband composite
video characteristics (BT.1700) and radiated RF characteristics (BT.1701).
QEMU should preserve the same architectural boundary.  A physical monitor,
video decoder and RF tuner are different devices even when a consumer TV set
contains all three in one cabinet.

Signal layers
-------------

Model the path as separate layers::

    picture source / video adapter
              |
              v
       scan timing + sync
              |
              +---- luminance
              |
              +---- colour encoding (NTSC/PAL/SECAM)
              |
              v
       composite/baseband signal
              |
              +------------------------> monitor/video input
              |
              v
       RF modulator / broadcast system
              |
              v
       channel allocation / carrier frequency
              |
              v
             air/cable
              |
              v
       tuner -> IF/demodulator -> baseband decoder

A direct composite-video monitor starts near the middle of this diagram.  A TV
receiver includes the RF stages.  A PC TV-tuner card usually adds a capture
engine after the decoder.  Those configurations may share signal descriptors
without being the same emulated device.

Scanning is not colour coding
-----------------------------

``AnalogVideoScanSystem`` describes timing independently from
``AnalogVideoColorSystem``.  The initial timing set contains the two dominant
interlaced conventional-TV scan families:

* ``ANALOG_VIDEO_SCAN_525_59_94``: 525 total lines, 60000/1001 fields/s,
  two interlaced fields per frame;
* ``ANALOG_VIDEO_SCAN_625_50``: 625 total lines, 50 fields/s, two interlaced
  fields per frame.

Colour is represented independently as monochrome, NTSC, PAL or SECAM.

This is intentional.  Code must not test ``PAL`` and infer 625/50, or test
``NTSC`` and infer 525/59.94.  PAL-M is an important architectural control:
it combines PAL colour coding with the 525/59.94 scan family.  Other regional
or playback variants likewise make a single combined ``ntsc_or_pal`` enum too
weak for reusable hardware emulation.

The predefined ``analog_video_pal_m_525_59_94`` descriptor exists partly as a
regression guard against reintroducing that false equivalence.

Line and field timing
---------------------

The timing structure stores field rate as a rational rather than a floating
point approximation.  ``analog_video_get_line_rate()`` derives the horizontal
line rate from total lines and field timing.  This keeps 60000/1001 exact in
emulated timing calculations.

Do not replace field rate with framebuffer refresh rate.  In a 2:1 interlaced
system, a field and a complete frame are not the same event.  Future scanout or
capture paths which model interlace need field parity and field timing; a
progressive framebuffer containing two woven fields is only one possible host
presentation of that signal.

The current QEMU ``DisplaySurface`` path does not itself carry analogue field
parity.  The analogue-video descriptors therefore describe the hardware signal
without pretending that the existing Pixman presentation path already models
beam scanning or deinterlacing.

Receiver lock versus colour lock
--------------------------------

A monitor can synchronize to a signal even when it cannot decode its colour
system.  Monochrome receivers are the obvious case, but multi-standard and
partially compatible colour receivers make the distinction useful more
broadly.

``AnalogVideoReceiverCaps`` consequently has independent scan and colour masks.
``analog_video_receiver_lock()`` returns one of three states:

* ``ANALOG_VIDEO_LOCK_NONE`` -- the receiver cannot lock to the scan timing;
* ``ANALOG_VIDEO_LOCK_LUMA`` -- sync/luminance are usable but colour is not
  decoded (or the source is monochrome);
* ``ANALOG_VIDEO_LOCK_COLOR`` -- both scan timing and colour encoding are
  supported.

A historical monitor model should use this type of signal acceptance test
instead of maintaining a list of framebuffer dimensions.  Electrical
bandwidth, sync tolerance, line-frequency tolerance and model-specific decoder
quirks can be added around this baseline when documented for a real device.

Framebuffer dimensions are not TV standards
--------------------------------------------

Host and guest software often represents standard-definition video as sampled
rasters such as 720 by 480 or 720 by 576.  Those dimensions are useful digital
representations, but they are not definitions of NTSC or PAL and they do not
contain the analogue blanking interval, sync waveform or colour subcarrier.

Likewise, 480 and 576 active-picture rows must not replace the 525- and
625-line scan structures in signal timing.  A capture device may deliberately
discard blanking and expose only an active sampled rectangle to guest memory;
the tuner/decoder still received a timed analogue signal before that capture
step.

This distinction also explains why non-square pixel scaling remains valid in
the physical-display presentation layer.  A sampled raster can be mapped to a
4:3 physical face without claiming its storage dimensions are the dimensions
of the CRT raster.

Relationship to physical displays
---------------------------------

``qemu_console_set_fixed_display_face()`` solves physical face geometry and
host-window stability.  It does not identify or validate an electrical video
standard.

A complete historical display path therefore needs both concepts::

    source timing/colour descriptor
              |
              v
    physical display acceptance
              |
              v
    fixed physical display face
              |
              v
    host Cocoa/GTK/SDL/VNC window

The physical display can reject an unsupported scan family, show luminance
without colour, or decode the supported colour system before the result is
presented on its stable face.  Host GUI resize policy remains outside that
signal decision.

Overscan, blanking and active picture
-------------------------------------

Do not bake overscan into the generic timing descriptor.  Total scan structure,
nominal active picture, transmitter blanking and a particular receiver's
visible mask are separate layers.

A CRT may hide part of an otherwise valid active signal.  A capture chip may
sample a programmable rectangle.  A digital presentation surface may contain
only active pixels.  Keeping those concepts separate will let a monitor and a
TV capture device consume the same incoming signal without forcing them to
crop it identically.

TV tuner preparation
--------------------

A TV tuner model should not output a magic ``NTSC frame`` or ``PAL frame``.
For analogue television, useful hardware stages are:

#. RF/channel selection: tuned carrier frequency and regional channel plan.
#. RF broadcast-system handling: channel bandwidth, vision modulation, sound
   carrier arrangement and other system-specific RF parameters.
#. IF/demodulation: recover composite video and sound/baseband information.
#. Colour/video decoding: identify scan timing and decode NTSC/PAL/SECAM.
#. Capture: crop/sample/scale the decoded picture and DMA it into guest memory.

The new ``AnalogVideoSignal`` type belongs between the RF/demodulator and
monitor/decoder/capture portions of that pipeline.  RF system letters and
channel plans should be added as a separate RF descriptor rather than fields
that silently redefine ``AnalogVideoColorSystem``.

This boundary supports both integrated and modular hardware.  For example, a
future PCI TV-capture card may contain a tuner module, an IF/video decoder and
a DMA engine, while an external composite monitor consumes the same baseband
signal without any RF tuner at all.

Sound is a separate signal path
-------------------------------

Analogue television audio must not be inferred solely from NTSC/PAL/SECAM
colour selection.  Sound carrier spacing and modulation are properties of the
broadcast/RF system and regional implementation.  A future tuner core should
therefore expose video and audio results separately even when one silicon part
demodulates both.

Implementation rules
--------------------

When adding analogue-video hardware:

* keep scan timing, colour coding and RF broadcast system separate;
* use rational rates for hardware timing where the standard is fractional;
* preserve interlace as field timing instead of silently converting it to a
  progressive frame rate;
* let cards own their sampled/captured raster dimensions;
* let physical monitors own face geometry, overscan and visual response;
* do not make a GUI frontend responsible for NTSC/PAL decoding;
* do not synthesize RF/channel behaviour inside the generic baseband signal;
* add hybrid or regional variants only from documented hardware/standards
  evidence rather than deriving them from names.

Reference standards
-------------------

The primary standards boundary for conventional analogue television is:

* ITU-R BT.470, *Conventional analogue television systems*;
* ITU-R BT.1700, *Characteristics of composite video signals for conventional
  analogue television systems* (separate NTSC, PAL and SECAM signal sections);
* ITU-R BT.1701, *Characteristics of radiated signals of conventional analogue
  television systems*.

ITU material and period device data sheets should take precedence over modern
framebuffer shorthand when implementing guest-visible hardware behaviour.
