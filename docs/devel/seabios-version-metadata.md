# Compact SeaBIOS version metadata

The pinned firmware generator embeds a fixed-width source identifier
(git- followed by 12 hexadecimal digits), an optional dirty marker for
tracked modifications, and the existing distributor suffix. Release
archives use their .version file; archives without metadata say unknown.

Build timestamps, hostnames and variable compiler descriptions are not
stored in the BIOS or VGA ROM. The full source revision and individual
compiler/binutils version lines are retained in build logs. BUILDINFO
remains a compatible string with the constant text "see build log".
The generator reports the combined UTF-8 byte length including NUL
terminators and preserves the generated header timestamp when unchanged.

This stabilizes version metadata, not the entire binary: compiler code
generation, configuration and linker placement can still change image
size. Compare unpadded BIOS sizes using the same toolchain and config.
The dirty marker is intentional; untracked files are not included.
