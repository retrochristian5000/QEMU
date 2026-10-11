OPTi 486WB chipset (26 April 1991)
==================================

The original OPTi data book explicitly identifies three chips, not one:
82C491 (system/DRAM/cache/AT bus controller), 82C392 (data buffer,
parity, clock and reset), and 82C206 (AT integrated peripherals).

The opti-486wb machine owns an ISA bus through the opti-486wb-chipset
QOM device.  The current implementation supports the documented
82C491 register index/data ports 22h/24h, with register indices
20h-2Bh, reset defaults and index expiry after each data-port access.

The current stage does NOT implement ROM shadow switching, cache
timings, refresh arbitration, physical 82C392 electronics or exact
82C206 silicon.  Existing AT PIC/DMA/PIT/RTC devices are reused.
It is a chipset reference profile, not an assertion about any
specific retail motherboard ROM or expansion-card configuration.

The ISA-only profile uses an i486 CPU with 1-64 MiB RAM (4 MiB default).
Existing isapc and Dell EISA profiles retain their behavior.
QTest: opti-486wb-test.

Primary source: OPTi, 82C491/82C392 Data Book, v1.1, 1991.
https://bitsavers.trailing-edge.com/components/opti/dataSheets/82C491_82C392_OPTi-486WB_PC_AT_Chipset_199104.pdf
