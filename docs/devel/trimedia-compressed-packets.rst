TriMedia compressed packet layout and QEMU TCG boundary
=======================================================

Recovered compression rules
---------------------------

TriMedia's VLIW instruction has up to five issue slots. Each slot
uses a two-bit descriptor from the **preceding** packet: 00 is a
26-bit operation, 01 a 34-bit operation, 10 a 42-bit operation,
and 11 an empty slot. A decision-tree entry starts with
format 0x02aa, specifying five 42-bit operations. The first two
bytes of the *current* packet provide the following format.

Each occupied slot has 24 core operation bits and two high bits
in a format-group byte. The 34-bit and 42-bit encodings carry
1 or 2 extension bytes in the packet's final extension region.
A fourth occupied operation introduces a second format-group
byte. Packet size ranges from 2 through 28 bytes. The issue
slot is not necessarily the ordinal position of its stored
operation (empty slots are compressed away).

Implementation and verification
-------------------------------

* ``target/trimedia/packet.[ch]`` implements bounded layout
  calculation and raw operation-bit reconstruction, given the
  *explicit* preceding format word; it does not decode semantics.
* ``scripts/tests/test-trimedia-packet.py`` builds the C
  helper in isolation and checks the seven packets in a public
  82-byte sample along with all 1024 descriptor combinations
  and truncated buffers.
* In the public sample, initial format 0x02aa describes a
  28-byte packet beginning 7c 47. It supplies next format
  0x477c, describing a following 9-byte packet.
* The helper is built into ``trimedia_ss`` through Meson,
  but is **not yet invoked for guest execution**.

The decoder/TCG integration remains deliberately closed:
``trimedia_decode_packet()`` returns false. Arbitrary guest
PC/translation block re-entry cannot assume that the incoming
format is 0x02aa; branch targets, exceptions, byte ordering,
and packet semantic decoding still need verification.
No executable firmware, guest cycles, or PLL timing is implied.

Period and independent comparative sources
------------------------------------------

* https://patents.google.com/patent/US5787302
* https://media.digikey.com/pdf/data%20sheets/nxp%20pdfs/pnx1300%20series.pdf
* https://blog.quarkslab.com/reverse-engineering-a-philips-trimedia-cpu-based-ip-camera-part-3.html
* https://github.com/poxyran/tm32disassembler
