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

``att-paradyne-dataport-3740``
  Paradyne DataPort Express 3740 command profile. The historical 3740 was
  an external 28.8 Kbit/s data/fax modem with a serial connection.

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

* ``\N0`` through ``\N7`` on the 3711, ``\N0`` through ``\N6`` on the 3740:
  record the requested connection/reliability mode
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

The 3740 accepts ``%B28800`` but rejects ``\N7``. The 3711 accepts
``\N7`` but rejects ``%B28800``. The generic Hayes and Rockwell profiles
do not acquire these Paradyne-specific commands.

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
