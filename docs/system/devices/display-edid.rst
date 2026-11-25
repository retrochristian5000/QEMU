Display input identification
============================

EDID describes the display sink, not the GPU, its PCI interface, or the
host UI backend. VGA, HDMI and DisplayPort can share an EDID generator
without sharing their electrical or link protocols.

For compatibility, existing virtual displays continue to advertise the
previous digital DisplayPort monitor profile. The fork supports two
explicit opt-in sink identities:

* PCI VGA and secondary VGA: ``analog-edid=on`` selects an analog RGB
  monitor with separate synchronization (EDID 1.4).
* SiI9022: ``hdmi-edid=on`` selects the HDMI Type A input identifier in
  the attached DDC monitor's base EDID block.

For example, on a machine supporting the standard PCI VGA adapter::

    qemu-system-i386 -vga none -device VGA,analog-edid=on

On boards containing the SiI9022, the property may be selected with
``-global sii9022.hdmi-edid=on``.

The SiI9022 remains a limited register/DDC model. Its new identity
does not implement TMDS, HDMI audio, HDMI vendor-specific CTA data
blocks, CEC, dynamic hotplug or DVI/HDMI mode switching. The VGA
profile likewise does not simulate analog waveforms. Shared timing
descriptors are unchanged and do not establish physical link limits.

Use identical display properties on source and destination when
migrating a machine. The new properties are fixed at construction
and no migration state format has changed.
