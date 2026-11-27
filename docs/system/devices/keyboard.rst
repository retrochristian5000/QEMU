.. _keyboard:

Sparc32 keyboard
----------------
SUN Type 4, 5 and 5c keyboards have dip switches to choose the language layout
of the keyboard. Solaris makes an ioctl to query the value of the dipswitches
and uses that value to select keyboard layout. Also the SUN bios like the one
in the file ss5.bin uses this value to support at least some keyboard layouts.
However, the OpenBIOS provided with qemu is hardcoded to always use an
US keyboard layout.

With the escc.chnA-sunkbd-layout driver property it is possible to select
keyboard layout. Example:

-global escc.chnA-sunkbd-layout=de

Depending on type of keyboard, the keyboard can have 6 or 5 dip-switches to
select keyboard layout, giving up to 64 different layouts. Not all
combinations are supported by Solaris and even less by Sun OpenBoot BIOS.

The dip switch settings can be given as hexadecimal number, decimal number
or in some cases as a language string. Examples:

-global escc.chnA-sunkbd-layout=0x2b

-global escc.chnA-sunkbd-layout=43

-global escc.chnA-sunkbd-layout=sv

The above 3 examples all select a swedish keyboard layout. Table 3-15 at
https://docs.oracle.com/cd/E19683-01/806-6642/new-43/index.html explains which
keytable file is used for different dip switch settings. The information
in that table can be summarized in this table:

.. list-table:: Language selection values for escc.chnA-sunkbd-layout
   :widths: 10 10 10
   :header-rows: 1

   * - Hexadecimal value
     - Decimal value
     - Language code
   * - 0x21
     - 33
     - en-us
   * - 0x23
     - 35
     - fr
   * - 0x24
     - 36
     - da
   * - 0x25
     - 37
     - de
   * - 0x26
     - 38
     - it
   * - 0x27
     - 39
     - nl
   * - 0x28
     - 40
     - no
   * - 0x29
     - 41
     - pt
   * - 0x2a
     - 42
     - es
   * - 0x2b
     - 43
     - sv
   * - 0x2c
     - 44
     - fr-ch
   * - 0x2d
     - 45
     - de-ch
   * - 0x2e
     - 46
     - en-gb
   * - 0x2f
     - 47
     - ko
   * - 0x30
     - 48
     - tw
   * - 0x31
     - 49
     - ja
   * - 0x32
     - 50
     - fr-ca
   * - 0x33
     - 51
     - hu
   * - 0x34
     - 52
     - pl
   * - 0x35
     - 53
     - cz
   * - 0x36
     - 54
     - ru
   * - 0x37
     - 55
     - lv
   * - 0x38
     - 56
     - tr
   * - 0x39
     - 57
     - gr
   * - 0x3a
     - 58
     - ar
   * - 0x3b
     - 59
     - lt
   * - 0x3c
     - 60
     - nl-be
   * - 0x3c
     - 60
     - be

Not all dip switch values have a corresponding language code and both "be" and
"nl-be" correspond to the same dip switch value. By default, if no value is
given to escc.chnA-sunkbd-layout 0x21 (en-us) will be used.


PC PS/2 mouse profiles
---------------------

The PC motherboard's i8042 auxiliary port accepts a fixed configuration
property ``mouse-model``. It selects the protocol capabilities of the
existing child rather than creating a second mouse or IRQ. For example::

    -global i8042.mouse-model=microsoft-ps2

* ``generic`` (default): preserves PNP0F13 and existing QEMU wheel/Explorer
  negotiation and migration behavior.
* ``microsoft-ps2``: experimental three-byte Microsoft PS/2 protocol
  profile, with ACPI HID PNP0F03 and CID PNP0F13 on the same MOU device.
  Wheel and Explorer negotiation do not change the device ID from zero.
* ``intellimouse``: starts with device ID zero, negotiates ID 3 using
  sample rates 200, 100, 80, and does not negotiate ID 4. Uses signed
  four-bit wheel movement sign-extended to one byte. Retains the port
  HID PNP0F13 because a specific IntelliMouse ACPI ID is not established.

Both explicit profiles validate sample-rate and resolution parameters and
report default settings on machine reset. Status requests include button
state. They preserve the motherboard I/O addresses and IRQ assignments.
Use identical profile settings at both ends of a migration; the profile
is configuration, not a new field in the existing VMState format.
These are protocol profiles, not cycle-accurate mouse firmware. Physical
sample-rate pacing, resolution conversion, scaling of movement and resend
history still require work. A Logitech PS/2++ identity is not implemented.
The Microsoft-specific HID is opt-in because changing it in an installed
guest may cause a new enumeration; the actual Windows 98 INF match and
Device Manager label need guest verification. With ACPI disabled only
protocol behavior changes. No SeaBIOS node is added.

References:

* https://sources.debian.org/src/pcmcia-cs/3.2.5-10/debug-tools/pnp.ids/
* https://www.scs.stanford.edu/23wi-cs212/pintos/specs/kbd/scancodes-12.html
* https://www.betaarchive.com/wiki/index.php?title=Microsoft_KB_Archive%2F132867
