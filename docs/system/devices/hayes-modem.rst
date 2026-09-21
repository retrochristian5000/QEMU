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
