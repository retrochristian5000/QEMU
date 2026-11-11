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
  The first 42-bit operation reconstructs to ``0x11581604381``,
  whose fields independently decode as ``asli(7) r1 -> r34``;
  24-bit core bytes are combined least-significant-first.
* The helper is built into ``trimedia_ss`` through Meson,
  but is **not yet invoked for guest execution**.

The decoder/TCG integration remains deliberately closed:
``trimedia_decode_packet()`` returns false. Arbitrary guest
PC/translation block re-entry cannot assume that the incoming
format is 0x02aa; branch targets, exceptions, byte ordering,
and packet semantic decoding still need verification.
No executable firmware, guest cycles, or PLL timing is implied.

Host-side AddressSanitizer and fuzz regression
----------------------------------------------

This is **host-side QEMU reader instrumentation**, not ASan for a
TriMedia firmware executable. LLVM currently recognizes 32-bit
TriMedia ELF objects, but has no native TriMedia Clang codegen or
compiler-rt sanitizer runtime. Do not use a cross-target compiler
to build these host tests.

The test runner compiles the actual ``packet.c`` with a minimal
host ``qemu/osdep.h`` shim. It does not require a QEMU system
machine or guest firmware. To run ordinary static vectors::

   python3 scripts/tests/test-trimedia-packet.py

To instrument actual C reads with AddressSanitizer and
UndefinedBehaviorSanitizer on the *host*::

   CC=clang python3 scripts/tests/test-trimedia-packet.py --sanitize=address,undefined

To additionally run a deterministic-length Clang libFuzzer smoke test::

   CC=clang python3 scripts/tests/test-trimedia-packet.py --sanitize=address,undefined --fuzz-runs=20000

The runner intentionally excludes inherited ``CFLAGS``,
``CXXFLAGS``, ``CPPFLAGS`` and ``LDFLAGS`` from a normal QEMU
build. It supplies sanitizer flags to **both compile and link**
steps, with ``-O1 -g -fno-omit-frame-pointer`` for actionable reports.
If a sanitizer cannot be linked, the command fails; it cannot
silently rerun without instrumentation. Fuzzing requires a
Clang distribution with a usable libFuzzer runtime.

``trimedia-packet-bounds-test.c`` checks all 1024 slot layouts
at all reported byte lengths 0 through 28, allocating an
**exact-size buffer** for each case (29,696 calls); this exposes
reads past an allocation boundary to ASan. The layout tests
retain their published 82-byte source fixture and explicitly
reject NDEBUG configurations that would omit assertions.
``trimedia-packet-fuzz.c`` feeds arbitrary format and packet
bytes to the same reader and checks per-slot bounds/invariants.

Neither sanitizer finds semantic opcode mapping bugs automatically.
The translation stub still prevents guest firmware execution;
no claims about cycle accuracy, CPU frequency, or guest memory
protection follow from a clean host ASan report.

Period and independent comparative sources
------------------------------------------

* https://patents.google.com/patent/US5787302
* https://media.digikey.com/pdf/data%20sheets/nxp%20pdfs/pnx1300%20series.pdf
* https://blog.quarkslab.com/reverse-engineering-a-philips-trimedia-cpu-based-ip-camera-part-3.html
* https://github.com/poxyran/tm32disassembler
