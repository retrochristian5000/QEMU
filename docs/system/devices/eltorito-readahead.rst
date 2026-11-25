El Torito boot read-ahead
=========================

El Torito locates boot images using a boot record and boot catalog;
Rock Ridge extends ISO 9660 directory records with POSIX filesystem
metadata. The two are independent and can coexist on the same image.

On Darwin, buffered, read-only ISO opens with libisofs enabled can
use a direct El Torito advisory read-ahead path for a single bootable
x86 no-emulation entry. The path validates the boot record, catalog
checksum, entry and image bounds, and advises the initial load extent
without importing the ISO directory tree. Multiple entries, emulation
modes, EFI and unrecognized catalogs retain the existing libisofs
fallback, with Rock Ridge and Joliet imports disabled.

The initial load extent is not necessarily the complete boot image
file. The direct path intentionally does not advise the remainder of
that file; subsequent guest reads use the ordinary block backend.
This optimization neither changes guest boot decisions nor alters the
image, and is skipped for direct I/O. Actual startup performance
depends on the image and host cache state.

Reference: El Torito Bootable CD-ROM Format Specification 1.0,
figures 1 through 3.
