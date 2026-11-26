AHCI and RAID controller boundaries
===================================

AHCI describes the software interface to a SATA host controller.
RAID describes the organization of multiple storage devices into logical
volumes. A physical chipset can offer both AHCI-compatible registers
and a RAID personality; neither feature implies the other.

ICH9
----

The ``ich9-ahci`` device models Intel ICH9 desktop six-port AHCI mode
(PCI ID 8086:2922, class 0106, programming interface 01).
The generic AHCI engine in ``hw/ide/ahci.c`` implements host registers,
port state, FIS processing, command slots and DMA. The PCI wrapper in
``hw/ide/ich.c`` provides the ICH9-specific identity and BARs.

Intel ICH9 desktop RAID mode uses device ID 2822, and mobile RAID mode
uses 282a. These personalities, Intel Matrix Storage metadata and
RAID option-ROM behavior are not implemented by ``ich9-ahci``.
Changing only the PCI class or device ID is not an implementation
of RAID. The Q35 AHCI PCI specification test checks the actual
ICH9 AHCI identity rather than accepting another storage class.

Reference: Intel I/O Controller Hub 9 (ICH9) Family Specification
Update, ICH9 Device and Revision ID Table, page 12.

Other storage controllers
------------------------

Device help distinguishes generic controller interfaces from identified
hardware and paravirtualized controllers. For example, ``isa-ide`` and
``isa-fdc`` describe generic ISA interfaces rather than a particular
manufacturer's chip. ``cmd646-ide``, ``sii3112``, ``am53c974`` and
``lsi53c895a`` identify particular controller models; ``pvscsi``
identifies VMware's paravirtualized interface. The established device
type names remain unchanged. The labels identify hardware or interfaces,
not adjustable resources, firmware requirements or implementation
limitations.

The ``sii3112`` controller retains its historical RAID-class PCI
identity (1095:3112) for compatibility. It implements Silicon Image
SATA task-file registers and bus-master DMA, not AHCI or an array engine.

The MegaRAID SAS model in ``hw/scsi/megasas.c`` implements the MFI
controller interface. Its emulated configuration reports one array
and one logical drive per attached SCSI device. It does not implement
general multi-disk striping, mirroring, parity or reconstruction.

Block backends, image formats and host storage redundancy are separate
from the guest-visible controller. An AHCI disk can be backed by
redundant host storage without becoming a guest RAID controller.
Keep controller identity, command transport and logical-volume policy
distinct, and do not change existing PCI IDs or migration state merely
to reorganize the implementation.
