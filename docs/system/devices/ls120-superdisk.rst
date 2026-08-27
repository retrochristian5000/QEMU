LS-120 SuperDisk / ATAPI removable disk
========================================

Status
------

The WHP QEMU fork does not currently emulate an LS-120 SuperDisk drive.
This document records the implementation boundary and the verified protocol
requirements so that LS-120 support is not flattened into either the floppy
controller model or the existing ATAPI CD-ROM model.

The first implementation target is one IDE/ATAPI LS-120-style removable disk.
LS-240, USB SuperDisk, SCSI SuperDisk and Iomega Zip devices are separate
follow-on targets and must not be implied by the first device.

Hardware boundary
-----------------

An IDE LS-120 is an ATAPI removable block device.  It is not an FDC-attached
floppy drive and it is not a CD-ROM with a different sector size.

The Compaq/Phoenix *ATAPI Removable Media Device BIOS Specification* defines an
ARMD as an ATAPI drive that reads, writes and boots removable media.  The BIOS
interface was designed to present such devices through INT 13h as floppy-like
boot devices while the hardware itself remains on the ATA/ATAPI interface.

For QEMU this requires three layers to remain distinct::

    IDE/ATA host controller
            |
            +-- ATAPI packet transport
                    |
                    +-- CD/DVD MMC personality       (existing ide-cd)
                    |
                    `-- removable block personality  (LS-120 target)

The LS-120 device therefore should reuse the IDE bus and generic ATAPI packet
transport where their semantics match, but should have its own packet-command
personality.

Protocol identity
-----------------

The removable-disk personality should expose a direct-access peripheral rather
than a CD-ROM peripheral.

Useful controls are SFF-8070i, *ATAPI Packet Commands for Block Devices*, and
the USB-IF UFI command specification, whose command set is explicitly based on
SFF-8070i and SCSI-2.  The resulting minimum identity is:

* 12-byte packet commands;
* removable media;
* direct-access peripheral type (``0x00``), not CD-ROM (``0x05``);
* 512-byte logical blocks;
* read/write block semantics;
* media-present, media-change and write-protect state; and
* flexible-disk geometry reported independently from the block backend size.

Do not reuse a CD-ROM INQUIRY response or a 2048-byte READ CAPACITY response.

Initial packet-command set
--------------------------

The first useful implementation should support the commands needed for
identification, media management and ordinary read/write operation:

* TEST UNIT READY (``0x00``);
* REQUEST SENSE (``0x03``);
* INQUIRY (``0x12``);
* START STOP UNIT (``0x1b``);
* PREVENT/ALLOW MEDIUM REMOVAL (``0x1e``);
* READ FORMAT CAPACITIES (``0x23``);
* READ CAPACITY (``0x25``);
* READ(10) (``0x28``);
* SEEK(10) (``0x2b``), if guests require it;
* WRITE(10) (``0x2a``); and
* MODE SENSE(10) (``0x5a``).

READ(12) and WRITE(12) are useful second-step additions.  FORMAT UNIT, VERIFY,
MODE SELECT and WRITE AND VERIFY should be added from documented behavior or a
real guest requirement rather than stubbed as successful commands.

A command that is not implemented must report an appropriate packet-command
error.  It must not silently succeed merely to make one guest continue.

Mode pages
----------

Two mode pages are especially important to the removable-block contract:

``0x05`` Flexible Disk page
    Reports geometry and media characteristics used by operating systems and
    by ARMD-aware firmware.  Historical Linux ``ide-floppy`` code also treats
    this page as the source of the current medium geometry.

``0x1b`` Removable Block Access Capabilities page
    Describes removable-block behavior.  Its system-floppy-type indication is
    relevant to devices intended to behave as floppy replacements.

Geometry must be a property of the inserted medium/profile, not a universal
translation applied to every image.

Media profiles
--------------

A native LS-120 medium uses 512-byte logical blocks and has a nominal 120 MiB
capacity (245760 logical sectors).  Period technical material reports a
960-cylinder, 8-head, 32-sector logical geometry for the native medium, while
the physical disk uses zoned recording and therefore does not have a constant
physical sectors-per-track value.

The 960/8/32 value is useful as a candidate native-mode profile, but it should
remain a verification item until checked against a primary LS-120 drive manual,
a captured Flexible Disk mode page, or equivalent first-party evidence.

LS-120 drives can also read conventional floppy media.  Supporting a 1.44 MiB
image must therefore eventually select a floppy-compatible medium profile
rather than stretching the native 120 MiB geometry over the smaller image.

Implementation boundary in QEMU
-------------------------------

The current IDE implementation has three ``IDEDriveKind`` values: hard disk,
CD-ROM and CF-ATA.  The ATAPI packet path is consequently gated as a CD-only
operation and ``ide_atapi_identify()`` identifies the device as a removable
CD-ROM.

LS-120 should get a distinct drive kind, for example an ATAPI removable-disk
kind.  The name should describe the protocol class rather than bake one vendor
model into generic IDE core code.

The expected split is:

#. Add a distinct ATAPI removable-disk drive kind and a user-visible
   ``ide-superdisk`` device.
#. Share the existing removable-media backend callbacks for insertion,
   ejection and media locking, after renaming/generalizing CD-specific helpers
   where necessary.
#. Permit an empty backend: an empty removable drive is valid hardware state.
#. Keep hard-disk geometry/SMART initialization out of the removable ATAPI
   personality unless the specification requires a specific field.
#. Generalize IDENTIFY PACKET DEVICE so its peripheral device type comes from
   the drive personality instead of being hard-coded to CD-ROM.
#. Split ATAPI command dispatch into common packet commands plus personality
   commands.  CD/DVD-only MMC operations must not appear on the SuperDisk.
#. Implement 512-byte PIO packet reads and writes against the block backend.
#. Advertise DMA only after the ATAPI removable-disk DMA path is implemented
   and tested; do not inherit CD DMA capability accidentally.

The existing CD read path is not a suitable block-transfer helper for LS-120:
it assumes 2048/2352-byte optical sectors and converts ATAPI logical blocks to
512-byte backend sectors with a two-bit shift.  A removable-disk path should
operate directly in 512-byte logical blocks.

Write path
----------

WRITE(10) is fundamental, not optional decoration.  A read-only LS-120 model
would contradict the ARMD definition and would fail normal removable-disk use.

The implementation should:

* reject writes when the backend/medium is write protected;
* bounds-check LBA and transfer length;
* use QEMU block accounting and asynchronous I/O conventions;
* preserve packet sense information on failed I/O; and
* complete PIO data-out transfers without reusing CD-ROM data-in assumptions.

Firmware / ARMD handoff
-----------------------

The WHP X86 firmware currently detects ATAPI packet devices but initializes all
of them with a CD-ROM block size and rejects ATAPI write operations.  It only
registers packet-device type ``0x05`` as a CD boot device.

QEMU-side emulation alone is therefore insufficient for a bootable LS-120.
The matching firmware work should:

#. recognize a removable direct-access ATAPI packet device as ARMD;
#. use packet INQUIRY/READ CAPACITY and Flexible Disk mode data rather than
   assuming 2048-byte CD-ROM sectors;
#. permit packet READ and WRITE operations with the device's 512-byte block
   size;
#. obtain the current medium geometry from the removable-disk command set; and
#. register the device through the appropriate floppy-style INT 13h ARMD path,
   rather than El Torito CD-ROM handling or ordinary fixed-hard-disk handling.

The ARMD BIOS specification permits configuration as floppy drive ``00h`` or
``01h``.  Exact SeaBIOS drive-number policy should be implemented from the
specification and tested with an actual boot image rather than inferred from
current hard-disk registration code.

Test contract
-------------

The QEMU qtest should start with observable guest behavior rather than internal
structure.  A minimal useful test matrix is:

* ``ide-superdisk`` can exist with no medium inserted;
* IDENTIFY PACKET DEVICE reports a removable packet direct-access device;
* INQUIRY reports peripheral type ``0x00`` and RMB set;
* no-medium TEST UNIT READY / REQUEST SENSE reports medium-not-present;
* READ FORMAT CAPACITIES and READ CAPACITY report the inserted image correctly;
* READ(10) returns 512-byte sectors from a raw backend;
* WRITE(10) changes the expected backend sector;
* a read-only backend reports write protection rather than modifying data;
* MODE SENSE(10) page ``0x05`` reports the selected media geometry;
* eject/load and PREVENT/ALLOW semantics are observable; and
* existing ``ide-cd`` qtests remain unchanged.

Firmware tests should separately verify that an LS-120 image is assigned the
expected INT 13h identity and can be read and written through BIOS services.
A bootable DOS/Windows-era image is a later integration test, not a substitute
for the packet-level tests above.

Non-goals for the first implementation
--------------------------------------

Do not add these by implication:

* LS-240 media or drive extensions;
* USB or SCSI SuperDisk transports;
* Iomega Zip behavior;
* a new floppy-controller format;
* fake CD-ROM commands for compatibility; or
* silent success stubs for unsupported formatting commands.

Reference controls
------------------

Implementation and validation should cross-check at least:

* Compaq/Phoenix, *ATAPI Removable Media Device BIOS Specification*;
* SFF-8070i, *ATAPI Packet Commands for Block Devices*;
* USB-IF, *USB Mass Storage Class UFI Command Specification* (a later command
  set explicitly based on SFF-8070i/SCSI-2 and useful as a control);
* historical Linux ``ide-floppy`` handling for SFF-8070i-compatible devices;
  and
* first-party LS-120 drive or system documentation for media geometry and
  timing details before those values are hard-coded.
