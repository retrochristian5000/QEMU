Hayes-compatible serial modem
=============================

QEMU provides a local Hayes-compatible modem character backend for serial
ports.  It is intended for operating-system modem detection, driver testing,
legacy dialer setup, and serial-control-line validation.

Attach the modem to a serial port with::

  -chardev modem,id=modem0 -serial chardev:modem0

The optional ``model`` property selects the emulated modem model::

  -chardev modem,id=modem0,model=hayes-accura-2400 \
    -serial chardev:modem0

Supported models are:

``hayes-accura-2400``
  The default data/fax profile.  It intentionally does not advertise voice
  service.

``rockwell-voice-14400``
  A Rockwell-compatible 14.4 Kbit/s voice/fax/data profile intended for
  Windows 9x voice-modem probing and telephony software.

``att-paradyne-dataport-3711``
  AT&T/Paradyne DataPort Express 3711 command profile. The historical 3711
  was an ISA 14.4 Kbit/s data/fax modem; QEMU models only its serial command
  interface, not the ISA board or a physical telephone line.

``att-paradyne-3740``
  Paradyne DataPort Express 3740 command profile. The historical 3740 was
  an external modem with a serial connection, 28.8 Kbit/s data and
  14.4 Kbit/s fax (Class 1 and Class 2).
  The previous model spelling ``att-paradyne-dataport-3740`` remains accepted.

An unsupported model name stops chardev creation with an error.

The default backend identifies as a Hayes Accura 2400-class modem and
implements the command sequences commonly used by DOS, Windows 9x Unimodem,
and dial-up clients.  Supported behavior includes:

* ``AT``, ``A/``, ``ATZ``, and ``AT&F``
* ``ATE``, ``ATQ``, ``ATV``, ``ATW``, and ``ATX`` result controls
* ``ATI0`` through ``ATI10`` and ``AT%V`` identification
* ``ATD``, ``ATA``, ``ATH``, ``ATO``, and the ``+++`` escape sequence
* ``AT&C``, ``AT&D``, ``AT%C``, ``AT&Q``, and ``AT&T``
* S-register reads and writes, including ``S0``, ``S7``, ``S30``, and ``S95``
* ``+FCLASS`` queries used during modem probing
* CTS, DSR, DCD, DTR, RTS, and modem-status interrupt behavior through the
  serial chardev ioctl interface

For example, the Windows 9x initialization string::

  AT&FE0V0W1&C1&D2S95=47

is accepted as a single combined command.

AT&T/Paradyne DataPort Express command profiles
------------------------------------------------

The DataPort Express profiles reuse the existing Hayes command/serial layer.
They provide separate maximum *emulated* DCE speeds (14,400 and 28,800 bit/s),
model-specific identification strings clearly marked as QEMU emulation, and
profile-scoped Paradyne configuration commands:

* ``\N0`` through ``\N7`` on both models: record the requested
  connection/reliability mode. On the 3740, ``\N7`` is accepted for
  compatibility with the archived DataPort Express V.34 driver.
* ``\Q0`` through ``\Q4``: record the configured flow-control mode
* ``%B<rate>``: select an attested discrete line-speed setting no higher than
  the selected model's maximum; invalid values return ``ERROR``
* ``AT&V``: inspect the current ``\N``, ``\Q``, and DCE speed settings
* ``ATZ`` and ``AT&F``: restore the model's initial settings

For example, to exercise a Windows 9x-style DataPort setup, attach::

  -chardev modem,id=modem0,model=att-paradyne-dataport-3711 \
    -serial chardev:modem0

Then send the following from the guest serial terminal::

  ATE1V1&F\N7\Q3%C1S7=60
  AT&V
  AT%B12000
  AT&V

The 3740 accepts ``%B28800``; the 3711 rejects that rate. Both accept
``\N7`` and reject ``\N8``. The generic Hayes and Rockwell profiles do
not acquire these Paradyne-specific commands.

Windows modem detection is separate from command initialization. An archived
``MDMATT.INF`` lists the DataPort Express V.34 (28.8) as ``UNIMODEM3C89963B``
and requests ``\N7`` during initialization. This is evidence for accepting
that command, not proof of original 3740 firmware responses or a successful
Windows 98 automatic match. The 3740 command reference repeats ``\N6``
for two reliability modes; the exact firmware semantics remain unverified.
No original hardware ID or serial PnP packet is invented.

The legacy Unimodem detection procedure (Microsoft patent US5815682A)
probes with ``ATE0Q0V1``, then derives a CRC-based device identifier
from normalized replies to ``ATI0`` through ``ATI10`` and ``AT%V``.
The archived INF's identifier is a target for comparison, not a string
to return in an AT reply. The current responses, including the
model-specific 3740 ``AT%V`` reply, are synthetic. Original firmware
responses and the exact Windows 98 FE INF match still need verification.

To inspect only the 3740 identification, serial parameters and modem
control-line changes, enable the following opt-in trace events::

    -trace 'dataport_3740_*'

The trace records virtual-clock nanoseconds. Identification query numbers
0 through 10 mean ATI0 through ATI10; -1 denotes AT%V. Control values
use the CHR_TIOCM bit definitions in include/chardev/char-serial.h.
No dial strings or carrier data are traced by these events. The trace
shows when a reply is queued, not when the guest has consumed it.

Reference: https://patents.google.com/patent/US5815682A

DataPort family comparison
~~~~~~~~~~~~~~~~~~~~~~~~~~

The external 3740 and ISA 3741 are 28.8 kbit/s models; the 3741
configuration reference explicitly points to the 3740 command summary.
The ISA 3711 is a 14.4 kbit/s Express model. The PCX 3705/3706 manual
is useful for identification command semantics (e.g. ATI3 reports
firmware, model and interface), but does not establish Express firmware
strings. The archived MDMATT.INF distinguishes the Express internal,
external and V.34 entries by identifiers ADA0F3F6, 401EA6EE and
3C89963B respectively, despite their identical initialization strings.
Those labels alone do not prove a one-to-one mapping to board models.

Both implemented Express models support ``\\D0`` (force CTS high) and
``\\D1`` (CTS follows DTR, default), and ``\\A0`` through ``\\A3``
(request 64, 128, 192 or 256 byte LAP-M frames, default 256). Only the
3740 accepts ``%M0`` (both V.34 and V.FC), ``%M1`` (V.34), and ``%M2``
(V.FC). These modulation and frame settings are configuration state,
not implemented data-pump behavior. ``AT&V`` reports them and ``AT&F``
restores defaults. ``AT%V`` identifies each emulated Express model
without claiming a genuine firmware revision. The 3741 is evidence for
shared commands, not an additional emulated device in this change.

* 3741: https://www.stason.org/TULARC/pc/modems-telephone-ISDN/P-R/PARADYNE-CORPORATION-Modem-DATAPORT-EXPRESS-3741.html
* PCX manual: https://manualmachine.com/att/dataportpcxmodem/19730026-user-manual/

DataPort 3740 modulation configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The 3740 reference distinguishes ``%B`` from ``%BL``: the latter
selects a legacy modulation/rate combination (2400 through 14400
bit/s in 2400 bit/s steps), rather than the V.34-capable rate path.
The requested rate and legacy selector are retained independently
of the ``%M`` preference. ``S76`` (V.32bis auto-retrain) and
``S78`` (automatic modulation) accept only 0 (enabled) and 1
(disabled), defaulting to 0.

``AT&V`` reports these requested settings and a diagnostic
``VFC CONFIGURED RATE`` field. Eligibility means only that the
configured rate is a Rockwell V.FC rate (14400 through 28800
bit/s in 2400 bit/s steps), the legacy selector is not active,
and the preference does not exclude V.FC. It is not evidence of
a negotiated modulation, and does not constrain possible fallback
or TCP throughput. The 3740 source describes %M at 28.8 kbit/s;
behavior at lower rates is not independently established.
No carrier is generated from these settings alone, and no artificial
delay is added to AT commands. Factory reset restores the original
rate and selection. Other modem profiles do not gain %BL support.

References:

* 3740 command table: https://arvutimuuseum.ee/th99/t/P-R/53813.htm
* Rockwell AT Command Reference Manual 1048 (1996), V.FC rate table:
  https://manualzz.com/doc/29221493/rockwell-rc288acx--rc144acx-modem-reference-manual

DataPort 3740 fax discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~

The 3740 hardware reference establishes a 14400 bit/s maximum fax rate
independent of its 28800 bit/s data rate, with V.17, V.29 and V.27ter
fax modulation. The 3740 exposes data (0), fax Class 1 (1) and fax
Class 2 (2) through ``+FCLASS``. Class 2.0 and voice are not supported.
Class 1 modulation test queries (``+FTM=?``, ``+FRM=?``, ``+FTH=?``
and ``+FRH=?``) use the documented Rockwell 14400 bit/s code list.
Class 2 provides manufacturer/model/revision queries and ``+FDCC``
read, write and test forms; the latter uses the Rockwell reference's
example parameter ranges and defaults, with rate code 5 denoting
14400 bit/s. These are provisional command-layer values, not a
verified original 3740 firmware transcript or negotiated T.30 session.
The fax settings do not change the data rate. Factory reset restores
data class and fax configuration defaults.

The configuration/discovery layer does not transmit fax data. Class 1
send/receive commands and Class 2 transfer commands return ERROR.
With no line, dialing reports the existing no-dial-tone/no-carrier
result; even with a TCP endpoint, fax-mode dialing returns NO CARRIER
rather than entering a raw data stream. No other modem profile's fax
capability report is expanded by this change.

References: 3740 hardware table and Rockwell command manual 1048,
sections 5.2, 6.2 and 6.5 (links above). Windows' original Unimodem
fingerprint is still unverified.

**Scope:** Settings for flow control and reliability are retained and
reported, but actual hardware RTS/CTS throttling, V.42/MNP negotiation,
compression, analogue signaling, fax frames, real manufacturer ROM responses,
and historical bus-level hardware are **not** implemented by this patch.
The existing TCP carrier simulation remains the only data path. ``ATI``
identification is emulated, not a byte-for-byte firmware fingerprint.
Do not equate the selected DCE setting with actual network throughput.

Reference evidence for these profile boundaries:

* DataPort Express 3711: https://stason.org/TULARC/pc/modems-telephone-ISDN/P-R/PARADYNE-CORPORATION-Modem-DATAPORT-EXPRESS-3711.html
* DataPort Express 3740: https://stason.org/TULARC/pc/modems-telephone-ISDN/P-R/PARADYNE-CORPORATION-Modem-DATAPORT-EXPRESS-3740.html
* Archived DataPort Express V.34 initialization: https://files.mpoli.fi/unpacked/software/win16/net/www/dlfull21.exe/_iew31_2.cab/mdmatt.inf

Voice control-plane compatibility
---------------------------------

The ``rockwell-voice-14400`` profile additionally advertises service class 8.
It accepts both ``+FCLASS=8`` and the Rockwell-style ``#CLS=8`` alias.  Voice
configuration currently covers ``+VIP``, ``+VLS``, ``+VSM``, ``+VGR``, and
``+VGT`` together with their query forms.  The initial voice format is kept
intentionally small: 8-bit linear samples at 8000 Hz.

This support is a control-plane compatibility layer.  ``+VTX``, ``+VRX``, and
``+VTR`` return ``ERROR`` because voice sample playback, recording, and duplex
transport have not yet been connected to QEMU audio.  Advertising those states
before a sample path exists would let guest software enter a mode the backend
cannot fulfill.

TCP data transport
------------------

The modem can use a TCP connection as its emulated telephone-line data path.
Configure a destination with both ``host`` and ``port``::

  -chardev modem,id=modem0,model=hayes-accura-2400,host=127.0.0.1,port=2323 \
    -serial chardev:modem0

With a TCP destination configured, ``ATD`` starts a non-blocking TCP
connection.  The guest receives ``CONNECT`` only after the connection is
established and ``NO CARRIER`` if the connection fails or the remote endpoint
closes it.  While online, serial payload bytes are forwarded bidirectionally
between the guest UART and the TCP stream.  ``+++`` returns to command mode and
``ATH`` closes the TCP connection.

The dialed Hayes number is intentionally kept separate from the TCP endpoint.
This lets DOS, Windows and other legacy dialers continue to issue ordinary
telephone-number strings while QEMU maps that emulated line to a host TCP
service.  A phonebook/number-to-endpoint mapping can therefore be added later
without replacing the transport ABI.

If ``host`` and ``port`` are omitted, ``ATD`` and ``ATA`` retain the
existing local-carrier behavior used by modem-detection tests.  Incoming TCP
ringing/``ATA`` service is not implemented yet; this first transport layer is
outbound dialing only.  Voice sample transport also remains separate.
