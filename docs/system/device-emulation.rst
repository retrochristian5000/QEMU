.. _device-emulation:

Device Emulation
----------------

QEMU supports the emulation of a large number of devices from
peripherals such network cards and USB devices to integrated systems
on a chip (SoCs). Configuration of these is often a source of
confusion so it helps to have an understanding of some of the terms
used to describes devices within QEMU.

Common Terms
~~~~~~~~~~~~

Device Front End
================

A device front end is how a device is presented to the guest. The type
of device presented should match the hardware that the guest operating
system is expecting to see. All devices can be specified with the
``--device`` command line option. Running QEMU with the command line
options ``--device help`` will list all devices it is aware of. Using
the command line ``--device foo,help`` will list the additional
configuration options available for that device.

A front end is often paired with a back end, which describes how the
host's resources are used in the emulation.

Device Buses
============

Most devices will exist on a BUS of some sort. Depending on the
machine model you choose (``-M foo``) a number of buses will have been
automatically created. In most cases the BUS a device is attached to
can be inferred, for example PCI devices are generally automatically
allocated to the next free address of first PCI bus found. However in
complicated configurations you can explicitly specify what bus
(``bus=ID``) a device is attached to along with its address
(``addr=N``).

Some devices, for example a PCI SCSI host controller, will add an
additional buses to the system that other devices can be attached to.
A hypothetical chain of devices might look like:

  --device foo,bus=pci.0,addr=0,id=foo
  --device bar,bus=foo.0,addr=1,id=baz

which would be a bar device (with the ID of baz) which is attached to
the first foo bus (foo.0) at address 1. The foo device which provides
that bus is itself is attached to the first PCI bus (pci.0).


Device Back End
===============

The back end describes how the data from the emulated device will be
processed by QEMU. The configuration of the back end is usually
specific to the class of device being emulated. For example serial
devices will be backed by a ``--chardev`` which can redirect the data
to a file or socket or some other system. Storage devices are handled
by ``--blockdev`` which will specify how blocks are handled, for
example being stored in a qcow2 file or accessing a raw host disk
partition. Back ends can sometimes be stacked to implement features
like snapshots.

While the choice of back end is generally transparent to the guest,
there are cases where features will not be reported to the guest if
the back end is unable to support it.

Device Pass Through
===================

Device pass through is where the device is actually given access to
the underlying hardware. This can be as simple as exposing a single
USB device on the host system to the guest or dedicating a video card
in a PCI slot to the exclusive use of the guest.


Generic compatibility models
============================

A generic compatibility model implements a guest-facing interface without
claiming to reproduce a specific physical board. Use a distinct type
with a ``-generic`` or ``-compat`` suffix. Reserve chip and board names
for independently identified profiles; short hardware aliases should
identify physical devices rather than entire families.

The generic device types in this fork are:

* ``cirrus-vga-generic``: default generic Cirrus Logic VGA (PCI).
* ``cirrus-vga-generic-pci``: explicit PCI variant, sharing the
  CL-GD5446-compatible implementation of the default profile.
* ``cirrus-vga-generic-isa``: explicit ISA variant with the
  CL-GD5428-compatible identity.
* ``sb16-generic``: legacy ISA Sound Blaster 16-compatible DSP and mixer,
  not a specific Creative CT-series board or ISA PnP card.

The old ``-device cirrus-vga`` and ``-device isa-cirrus-vga`` names
are no longer registered. Update old generic command lines and
type-specific global properties to the new names. The short ``sb16``
name now selects an experimental Creative CT1740 PCM/MIDI profile, not the
generic model. For ``-audio``, use ``model=sb16-generic``. The legacy
``-vga cirrus`` option still selects the generic model. Guest register
identities, resource defaults, firmware path names and migration section
names are retained; cross-version migration has not been validated.

Cirrus Logic chipset types use the short chip name, with a bus suffix
where appropriate. The ``gd5428`` and ``gd5446-pci`` profiles retain their
historical generic implementations. The explicit ``gd5446a-pci`` and
``gd5446b-pci`` profiles distinguish the silicon revisions' PCI resource
layouts and alternate host BitBLT source paths while sharing the DAC. The GD5422, GD5426 and GD5430
profiles retain their existing behavior. These are registered device
types, not aliases. The previous names ``isa-cirrus-vga-generic``,
``isa-cirrus-gd5422``, ``isa-cirrus-gd5426``, ``isa-cirrus-gd5428``,
``cirrus-gd5430-pci``, ``cirrus-gd5430-vlb`` and
``cirrus-gd5446-pci`` are retired; update explicit device and global
property arguments. Cross-version migration after these renames
has not been validated. The ``sb16-pnp`` and
``awe32`` reserved profiles are not aliases for SB16.

Use the canonical names ``AC97``, ``ich9-ahci``, ``e1000`` and
``mc146818rtc`` instead of the removed aliases ``ac97``, ``ahci``,
``e1000-82540em`` and ``motorola-mc146818`` with ``-device``.
The legacy audio model selector ``-audio ...,model=ac97`` is unchanged.
VirtIO transport selectors retain architecture-dependent behavior;
they are not physical hardware profiles.


Emulated Devices
~~~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1

   devices/virtio/index.rst

   devices/ahci-raid.rst
   devices/bt8xx-tv-capture.rst
   devices/can.rst
   devices/canokey.rst
   devices/ccid.rst
   devices/cdrom-xa.rst
   devices/cxl.rst
   devices/display-edid.rst
   devices/eltorito-readahead.rst
   devices/emmc.rst
   devices/hayes-modem.rst
   devices/igb.rst
   devices/intel-82420-82430-bridges.rst
   devices/ivshmem-flat.rst
   devices/ivshmem.rst
   devices/keyboard.rst
   devices/ls120-superdisk.rst
   devices/net.rst
   devices/nvme.rst
   devices/pcmcia-pc-card.rst
   devices/scsi/index.rst
   devices/usb-u2f.rst
   devices/usb.rst
   devices/vfio-user.rst
