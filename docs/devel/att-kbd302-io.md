# AT&T 302 keyboard I/O development

The PC 6300/M24 motherboard decodes 0x60 as keyboard data and 0x64
as command/status. Other ports in 0x60–0x67 are board-specific;
do not claim them in the keyboard profile. The keyboard controller
has an IRQ1 connection.

Use `-machine none -nodefaults -device att-kbd302,io=on` for
isolated register tests. The optional interface refuses occupied ports.
The default profile still connects a controller without mapping ports.
The PC machine's i8042 is independent of -nodefaults.

The existing original UPI-41 shared-buffer handshake is retained.
The host input path uses the provisional Model 302 scan table and
passes queued bytes to the empty controller buffer without loss of
pending bytes. Reads of status do not consume data. The named irq1
GPIO indicates available output, but a motherboard must connect it
to its interrupt controller. Commands are latched, not executed:
the firmware ROM, clock/data wire timing, reset, full board resources,
and Windows 9x compatibility remain unimplemented. Migration is blocked
while experimental I/O is enabled because its state is not serialized.

Reference: Olivetti M24/M21 Theory of Operation, November 1984,
pp. 2-44, 2-53 to 2-55.
https://bitsavers.org/pdf/olivetti/m21_m24/Olivetti_M21_M24_Theory_of_Operation_Nov84.pdf
