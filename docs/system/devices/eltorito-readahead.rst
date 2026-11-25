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

Filename extensions
-------------------

Joliet uses a supplementary Unicode volume descriptor and directory
hierarchy. Adaptec Romeo instead extends the primary directory hierarchy
with legacy long names, without a separate short-name tree. Disabling
Joliet alone cannot avoid importing Romeo's primary hierarchy.

The direct advisory probe scans at most 32 volume descriptors, starting
at sector 16, without interpreting filenames or character encodings.
A recognized terminator without a boot record needs only descriptor
read-ahead, not a directory import. Unknown descriptor types or versions,
truncated sequences and the scan limit retain the libisofs fallback.
This is not a Romeo detector or a filesystem reader. Boot records outside
the conventional sector 17 location may be discovered for host hints;
guest firmware boot support is unchanged.

References: Microsoft Joliet Recording Specification, May 22, 1995;
Apple Tech Info Library article 20752, December 18, 1996.
