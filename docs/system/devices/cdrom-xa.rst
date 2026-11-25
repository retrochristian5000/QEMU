CD-ROM XA and Video CD
======================

Video CD is a White Book application format on CD-ROM XA. It is not
an independent drive transport. An optical disc may contain Mode 2
Form 1 filesystem data (2048-byte payloads), Mode 2 Form 2 multimedia
data (2324-byte payloads), and other track types.

The ordinary cooked optical image path in this fork exposes 2048-byte
logical blocks. ATAPI READ CD can synthesize legacy Mode 1 raw sectors
of 2352 bytes from these blocks. It cannot recover XA subheaders,
Form 2 payloads, audio tracks or original error-correction data from
a cooked image.

For nonempty READ CD data requests, explicit expected sector types
other than any type (0) or Mode 1 (2) are rejected. CD-DA (1) and
Mode 2 types (3, 4, 5) receive ILLEGAL REQUEST, ASC/ASCQ 64/00
(ILLEGAL MODE FOR THIS TRACK); reserved types (6, 7) receive invalid
field in CDB. The existing no-data request behavior is retained.
The synthetic Mode 1 encoder retains its legacy binary MSF header and
zero-filled EDC/ECC fields; it is not a physical disc encoder.

Full Video CD support requires an image backend that preserves per-track
and per-sector format metadata, XA subheaders, and original payloads,
plus MMC READ CD handling for the supported fields. MPEG decoding belongs
to the guest player or separately modeled decoder hardware, not the
generic CD-ROM transport. SCSI and ATAPI capabilities require separate
verification; this change does not implement SCSI READ CD.

References: MMC READ CD Expected Sector Type and T10 ASC/ASCQ assignments
(64h/00h); Philips/Sony White Book Video CD specification.

Read-only versus recordable media
---------------------------------

The emulated optical drives expose only the CD-ROM (0008h) and DVD-ROM
(0010h) MMC profiles. Reading cooked data from a finalized CD-R or CD-RW
does not implement the CD-R (0009h) or CD-RW (000Ah) recording profiles.
ATAPI and SCSI share the finalized, non-erasable disc-information
response and the read-only profile list. Neither reports recording
capabilities or a nonzero write speed on the capabilities mode page.
Existing read capability bits are retained for guest compatibility.

A recorder requires separate medium metadata, write parameters,
blanking, track reservation, session closure, and write-command
handling. A writable host image alone is not a CD-RW implementation.
The existing capacity-based CD/DVD selection remains unchanged.

Reference: MMC-4, profile definitions 5.4.8 through 5.4.10.
