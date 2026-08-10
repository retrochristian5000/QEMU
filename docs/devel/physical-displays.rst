Physical display presentation
=============================

Historical display hardware needs a different presentation model from QEMU's
generic graphical console.  The guest video mode, the physical display face,
and the host GUI window are separate things and must not be conflated.

Three layers
------------

The guest video adapter owns the input raster and timings.  A physical monitor
owns a screen face with stable geometry.  The host frontend owns a resizable
window used to present that monitor.

A guest mode change therefore must not resize a historical monitor.  For
example, 720x400 VGA text and 640x480 graphics can both occupy the same 4:3 CRT
face.  The horizontal and vertical scale factors from raster to glass may be
different because historical video modes did not require square pixels.

``qemu_console_set_fixed_display_face()`` gives a graphical console a stable
presentation surface.  Guest ``DisplaySurface`` updates are resampled into that
surface.  Display frontends continue to see the same surface dimensions across
guest mode switches, so guest-driven window resizing stops without adding
monitor-specific policy to Cocoa, GTK, SDL, VNC, or other frontends.

The user remains free to resize the host window.  Normal frontend scaling then
maps the already-normalized physical display face into that window.  This is a
host presentation choice and is not guest-visible state.

Generic consoles
----------------

Do not assign a fixed display face to a generic QEMU console.  Existing generic
behaviour remains unchanged: a frontend can continue to track guest surface
size in the way it historically has.

Historical monitor models should establish their physical display face before
display listeners are initialized.  The dimensions describe presentation
geometry; they are not a list of guest modes the monitor accepts.  Timing and
mode validation belongs in the monitor/device model separately.

Analogue signal acceptance
--------------------------

Analogue television standards make the separation above especially important.
A framebuffer size is not sufficient to describe an incoming signal, and a
colour system is not a synonym for scan timing.

``hw/display/analog-video.h`` provides independent scan and colour descriptors.
A physical analogue monitor should first decide whether it can synchronize to
the incoming scan family, then whether it can decode the colour encoding.
``analog_video_receiver_lock()`` expresses the baseline outcomes as no sync,
luminance-only lock, or colour lock.

This distinction lets a monochrome display lock to a colour composite signal,
and it prevents code from assuming that PAL always means 625/50 or that NTSC
always defines the raster geometry.  See :doc:`analog-video` for the shared
signal model and the RF/tuner boundary.

Interlaced analogue input also carries temporal field structure.  The fixed
face scaler is not a deinterlacer and must not be treated as one.  A future
analogue monitor path can use field parity/timing to reproduce scan behaviour
while keeping phosphor persistence in presentation-only state.

Current scanout boundary
------------------------

The first implementation normalizes software ``SCANOUT_SURFACE`` output.  It
is deliberately correctness-first and currently resamples the full face when
the guest surface changes.

Direct OpenGL texture and DMA-BUF scanout bypass this software presentation
surface and are not transformed yet.  Historical monitor models which require
the fixed-face path should therefore use software-surface scanout until a
corresponding physical-display transform exists for direct scanout.

Future physical effects
-----------------------

A fixed face is only geometry.  CRT phosphor colour, persistence, scan response,
overscan, analogue bandwidth, controls, power state, and front-panel indicators
belong to the physical display model or its presentation layer.  They must not
be approximated by changing the guest video adapter merely to make the host
window look historical.
