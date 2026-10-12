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

PC Super VGA monitors and Windows 98
------------------------------------

Windows 98 distinguished the video *adapter* from the physical *monitor*.
Contemporary installation instructions for Rockwell Automation 6185 monitors
list Windows 98's ``Standard monitor types`` selections, including
``Plug and Play Monitor`` and ``Super VGA 800x600``, ``Super VGA 1024x768``,
or ``Super VGA 1280x1024`` profiles (depending on the monitor and manual).
These are evidence for selectable monitor compatibility descriptions; they
are **not** substitute graphics adapters or proof of a particular refresh
rate, colour depth, or Windows 98 video driver.

Historical sources: Rockwell Automation, *6185 Economy User Manual*,
publication 6185-UM003A-EN-P, "Setting the Monitor Type" /
"Setting Up Video Resolution", and publication 6185-5.1,
"Procedures for Accessing Monitor Type Manually".
Archived manual:
https://manualzilla.com/doc/6905490/6185-um003a-en-p--6185-economy-user-manual

The guest chooses modes through the actual adapter/driver.  A PC graphics
model (e.g. Cirrus GD5446 or QEMU Standard VGA) produces a framebuffer.
``ui/console.c`` then hands it to an optional physical monitor model,
which can validate supported *timings*, resample it onto a stable face,
and present the face through Cocoa/GTK/SDL/VNC.  The selected Windows
monitor label must not silently change the PCI identity, VGA registers,
graphics driver, host window dimensions, or pixel format.

An SVGA monitor capability model needs manufacturer/model provenance and,
where known, horizontal scan limits, vertical refresh limits, supported
sync/connection conventions, and any explicitly published mode timings.
Do not convert a resolution label into invented fixed pixel clocks or CRT
refresh rates.  For Plug and Play models, EDID and driver discovery are a
separate evidence path: QEMU Standard VGA can expose EDID in PCI BAR2,
but that does not establish that every Windows 98 driver reads it.

There is already a ``qemu_console_set_fixed_display_face()`` presentation
API, but as of this audit no emulated PC monitor calls it.  Consequently
the existence of this scaler must not be reported as operational Windows 98
SVGA monitor emulation.  Connect a real monitor model before enabling
this path for a guest.  Never force the fixed-face policy on all VGA
devices merely because Windows 98 offers a generic monitor selection.

Validation plan (not yet completed):

* On an x86 PC machine, establish the guest graphics driver and display
  adapter separately from the Windows 98 monitor selection.
* Exercise standard VGA text and 640x480 graphics, then monitor-profile
  candidates 800x600, 1024x768, and 1280x1024 only where the selected
  adapter/driver and monitor timings support those modes.
* Record guest colour depth, measured mode timing or driver-reported
  refresh, framebuffer size/stride, and any rejected combinations.
* Observe transitions on Cocoa and at least one other backend for
  full-frame redraw, clipping, aspect ratio, cursor coordinates, and
  stable physical-face size.  Do not infer successful guest mode changes
  solely from host window resize.
* Re-test the existing PowerPC OpenBIOS VGA BAR0/BAR2/EDID path separately:
  Windows 98 PC monitor selection cannot repair OpenFirmware PCI discovery.

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
