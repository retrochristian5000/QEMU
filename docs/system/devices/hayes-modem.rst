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

The DataPort Express profiles reuse the common AT command and serial
transport layer. Hayes compatibility describes command syntax, not
manufacturer identity. Model-specific ATI and AT%V responses are held in
the separate modem model table, rather than in the shared parser. The
3740 retains ERROR for unidentified ATI responses; it never substitutes
another manufacturer's identification. The documented DataPort %C0 and
%C1 compression settings are accepted; other values return ERROR.
They provide separate maximum *emulated* DCE speeds (14,400 and 28,800 bit/s),
model-specific identification strings clearly marked as QEMU emulation, and
profile-scoped Paradyne configuration commands:

* ``\N0`` through ``\N7`` on both models: select the requested
  asynchronous connection/reliability policy; bare ``\N`` selects 0.
  On the 3740, ``\N7`` is accepted for compatibility with the archived
  DataPort Express V.34 driver.
* ``&M0`` and ``&Q0`` select direct asynchronous mode; ``&Q5`` selects
  asynchronous error-control mode and ``&Q6`` selects buffered asynchronous
  mode. The external 3740 also accepts ``&M1`` through ``&M3`` and the
  equivalent ``&Q1`` through ``&Q3`` as synchronous configuration.
* ``\C0`` through ``\C2``: record the auto-reliable buffering
  policy (default 0); mode 2 requests a switch to buffering upon receipt
  of the configured fallback character
* ``%A0`` through ``%A127``: record the ASCII fallback character
  (default 19; 0 disables character-based fallback)
* ``\Q0`` through ``\Q4``: record the configured flow-control mode
* ``&K0`` (or bare &K), ``&K3`` and ``&K4`` select disabled,
  hardware and software flow control using the same state as
  ``\Q0``, ``\Q3`` and ``\Q1`` respectively. &K4 also selects
  local XON/XOFF handling; these settings are stored in user profiles.
* ``\K0`` through ``\K5``: record the requested DTE BREAK policy
  (factory default 5, bare command selects 0); reported by AT&V and
  included in stored profiles
* ``%B<rate>``: select an attested discrete line-speed setting no higher than
  the selected model's maximum; invalid values return ``ERROR``
* ``AT&V``: inspect the current ``\N``, ``\Q``, and DCE speed settings
* ``AT&W0`` and ``AT&W1``: save the active data configuration to one
  of two emulated user profiles; bare &W saves profile 0
* ``AT&Y0`` and ``AT&Y1``: select the profile recalled by hardware reset;
  bare &Y selects profile 0
* ``ATZ0`` (or ``ATZ``) and ``ATZ1``: disconnect and recall the specified
  user profile
* ``AT&F``: restore active factory settings without changing stored
  profiles or the power-up selection

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

AOL 4.0's reported initial commands (AT twice, ATH, AT, ATEQV1)
are covered by regression tests, with its separately observed &K3
probe. The basic commands follow ITU-T V.25ter (August 1995):
https://www.itu.int/rec/T-REC-V.25ter-199508-S/en.
Both Express hardware tables show &K3 in a flow-control example.
The related DataPort PCX User's Guide (October 1995, B-15) and
Rockwell reference manual 1048 describe &K0, &K3 and &K4 semantics.
The alias mapping is reference-based, not an original ROM comparison.
The PCX also documents &K5 and &K6, but Express support and the
corresponding transport behavior are unverified; these values return
ERROR in this implementation. Bare K is not a synonym for either
&K or \K. The existing 3740 receive-side RTS gate and software
flow-control logic are reused; transmit-side CTS throttling is not
implemented. No change is made to the separate \D CTS policy.
AOL's complete scan and detection algorithm remain unknown.

The operating-mode mappings follow the related DataPort PCX User's
Guide (October 1995, B-16/B-17) and Rockwell RC288ACx reference
manual 1048 (3.2.2). The original 3740 firmware mappings are unverified.
The Express hardware table identifies ``\N0`` as normal, ``\N1`` as direct,
and 2 through 6 as error-control policies; 7 remains accepted.
For consistent state, ``\N0`` selects &Q6, ``\N1`` selects &Q0, and
``\N2`` through ``\N7`` select &Q5. &Q5 retains an existing reliable
policy or restores the current emulation default (6). Synchronous
selection retains the last asynchronous policy as inactive. The
most recent valid operating-mode command wins; bare &M and &Q mean
0. Backslash-Q is independent DTE flow control. &Q4 (Rockwell AutoSync)
is not supported by the related PCX table and is rejected. The 3711
does not expose synchronous DTE clocking in this emulation.

AT&V reports the requested operating mode; profile save and reset
include it. Synchronous DTE clocking, DTR dialing, talk/data switching,
S27 bit mapping and physical direct-mode timing are not implemented.
A data dial in a requested synchronous mode returns NO CARRIER rather
than establishing a misleading TCP byte connection. A synchronous
mode cannot be selected during an active or pending connection.
The existing asynchronous TCP substitute and non-DataPort profiles
are unchanged.

At 300 bit/s, ATB0%B300 requests V.21 and ATB1%B300 requests Bell
103. B0/B1 follow the related Rockwell RC288ACx reference manual 1048
(section 3.2.1); B1 is the US reference default, not a verified 3740
firmware default. The B setting is saved with the other profile fields.
AT&V reports the requested 300 bit/s modulation, not an established
physical link. Other B-command effects and S27 mapping are unverified.

The separate modem-v21 module implements phase-continuous 300 bit/s
binary FSK generation at 9600 PCM samples/s, and tone classification
of already symbol-aligned windows. Channel 1 uses 980/1180 Hz
(mark/space), and channel 2 uses 1650/1850 Hz. Reference: ITU-T V.21
(1988), https://www.itu.int/rec/T-REC-V.21-198811-I and RFC 4734.
It is not connected to the TCP byte transport, audio hardware or SIP.
Carrier acquisition, timing recovery, call establishment, physical
line levels and asynchronous framing remain unimplemented. Bell 103
waveforms and T.30 fax framing are separate future work.

MNP Class 5 uses compression over an MNP link, not LAPM error
correction. The DataPort hardware table defines \\N2 as MNP only,
\\N3 as MNP with normal-mode fallback, and %C0/%C1 as compression
disabled/enabled. These differ from generic Rockwell command mappings.
AT&V describes MNP5 eligibility for these explicit MNP modes; no
negotiated compression is claimed. Modes 6/7 remain unresolved.

The separate modem-mnp5 module implements the 257 rank codewords
(including the flush token), with exact-length validation and no
unbounded allocation. Tests check published codeword examples, all
ranks, incomplete codewords and malformed input. References:
https://www.ece.unb.ca/tervo/ece4253/mnp5.shtml and
https://d-modem.github.io/D-Modem/mnp/mnp5/.
Adaptive ranking, run-length coding, streaming bit packing, link
negotiation and retransmission are not implemented by this module.
No raw TCP payload is compressed or changed.

Both DataPort Express hardware tables identify \A0 through \A3 as
maximum LAP-M information sizes of 64, 128, 192 and 256 characters,
with \A3 as the factory default:
https://arvutimuuseum.ee/th99/t/P-R/53811.htm and
https://arvutimuuseum.ee/th99/t/P-R/53813.htm.
Rockwell reference manual 1048 section 3.3.2 instead describes its
\A command as an MNP block-size control, defaulting to 128. Do not
import that default or MNP semantics into the Express profiles
without model-specific evidence. The Express setting is reported by
AT&V and stored with user profiles. It is a requested maximum, not
a negotiated LAPM information-field length or a TCP buffer limit.
The omitted-argument form is not documented in the Express tables;
the existing requirement for an explicit number is retained.
Regression coverage exercises all four values, invalid values,
compression independence and profile restoration.

The auto-reliable settings are included in AT&V and saved profiles.
They are manufacturer-specific controls related to error correction,
not AT commands defined by ITU-T V.42. The historical reference is
ITU-T V.42 (March 1993), https://www.itu.int/rec/T-REC-V.42-199303-S/en.
No detection exchange, LAPM framing, retransmission, MNP fallback,
V.42bis compression or negotiation-time buffering is implemented by
these settings. The fallback character does not intercept ordinary
online payload. The EC indicator remains unsupported; TCP reliability
does not establish V.42 negotiation. The hardware tables disagree on
the exact modes 6 and 7; their existing numeric acceptance is retained.

The BREAK policy is documented for both the 3711 and 3740 hardware
tables. The six values describe discard, priority or ordered BREAK
handling and whether to enter command mode. Only the configuration
is implemented; serial BREAK delivery, buffer-discard effects and
BREAK-triggered command-mode transitions are not yet emulated.
No synthetic bytes are sent to the TCP peer. The separate &K command
controls flow rather than BREAK; \B (transmit BREAK) remains unsupported.

Both user profiles initially contain factory defaults. Stored settings
include the emulated writable S-registers, data reliability, compression,
flow control, DCE rate and modulation, and result and control-line
policies. Connection state, pending payload, DTE wiring and fax/voice
session settings are not stored. AT&V reports the power-up selection
along with the active configuration. Invalid profile numbers return
ERROR. The profiles are instance-local memory: they survive ATZ,
AT&F and the owned UART hardware reset, but not QEMU process exit.
No host NVRAM file is created. The exact 3740 NVRAM field layout
and power-cycle persistence are not implemented.

Reference: the 3740 hardware table uses &W with S76, S78 and %M;
Rockwell reference manual 1048 sections 3.2.1 and 3.2.2 documents
two user profiles and reset selection. The related DataPort PCX
user guide (October 1995, B-18/B-19) confirms &W and &Y.
This is reference-based behavior, not a verified original ROM dump.

Macintosh initialization is also supported at the command level. Apple's
MacPPP documentation gives the following string for the related 14.4 kbit/s
DataPort, which both Express profiles accept::

  AT\N7%C1&C1&D0\Q3

This selects reliability mode 7, enables the compression setting,
makes DCD follow the connection, ignores DTR changes for connection
control, and selects hardware flow control. Regression coverage checks
the configured settings and continued reception over the TCP substitute
after DTR falls while RTS remains asserted. The CTS policy selected by
``\D`` remains independent of ``&D``. This is not a recovered 3740 CCL
script or proof of electrical RS-422, compression or reliability
negotiation.

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
to return in an AT reply. For the 3740, ATI0 reports the reference
Rockwell product code 28800, corroborated by HylaFAX's rc288dpi-1
configuration. ATI3 is a descriptive emulation identity including
the documented V.34 and V.FC modulation families, not a firmware dump.
AT%V retains its explicitly synthetic model-specific response.

ATI1, ATI2 and ATI4 through ATI7 return ERROR until the OEM checksum,
OEM identifier, country, data-pump and DAA information can
be established. ATI8 and higher also return ERROR rather than invented
identification text; the Rockwell reference command range is I0-I7.
These errors describe the limitations of this emulation, not verified
original 3740 responses. In particular, ATI2 does not assert a valid
ROM checksum where no ROM is emulated. Result codes honor Q/V settings.
The related HylaFAX att-dpexpress-2 configuration documents a
customized ATI1 format for a 3715, so its firmware values are not
transferred to the 3740. Other modem profiles retain their existing
responses. Original firmware responses and the Windows 98 FE INF
match still need verification.

References:

* Rockwell reference manual 1048, revision 3, section 3.2.1:
  https://manualzz.com/doc/29221493/rockwell-rc288acx--rc144acx-modem-reference-manual
* HylaFAX rc288dpi-1:
  https://sources.debian.org/src/hylafax/1%3A4.1.1-3.1/config/rc288dpi-1
* HylaFAX att-dpexpress-2:
  https://fossies.org/linux/misc/hylafax-6.0.7.tar.gz/hylafax-6.0.7/config/att-dpexpress-2

To inspect only the 3740 identification, serial parameters and modem
control-line changes, enable the following opt-in trace events::

    -trace 'dataport_3740_*'

The trace records virtual-clock nanoseconds. Identification query numbers
0 through 10 mean ATI0 through ATI10; -1 denotes AT%V. Control values
use the CHR_TIOCM bit definitions in include/chardev/char-serial.h.
No dial strings or carrier data are traced by these events. The trace
shows when a reply is queued, not when the guest has consumed it.

The Cocoa Modem Indicators window also includes an optional, read-only
AT command transcript. Enable Capture AT commands and replies to record
completed guest AT commands, the escape sequence and modem-generated
reply lines, including numerical result codes. This is a command-level
view, not a byte-exact serial trace: echo, incomplete commands and online
payload are excluded. Command text can contain dialed telephone numbers.
The transcript is limited to 16 KiB per supported 3740 backend; older
complete lines are discarded. Capture starts off, and Clear, disabling
capture or closing the window discards the collected text. No host log
file is written. The capture does not modify the guest's AT result-code
verbosity. Reply lines are captured when generated, not when the guest
consumes them.

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

DataPort XON/XOFF pass-through
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Both Express models document ``\X0`` (default, local processing only)
and ``\X1`` (local processing plus forwarding). With ``\Q1``
selected in online data mode, DTE XOFF (0x13) pauses delivery of
received payload to the guest, and XON (0x11) resumes it.
With ``\X1`` the same byte also enters the TCP transmit queue.
The existing receive buffer is retained and TCP backpressure applies
when it fills. No characters are intercepted under hardware flow
control (``\Q3``) or in command mode. Changing the setting does not
alter the ordinary Hayes X result-code control. ``AT&V`` reports the
pass-through setting, and factory or hardware reset restores ``\X0``.
Hangup and leaving online data mode clear the paused state.

This implements guest-to-modem software pacing and optional forwarding
over the TCP substitute, not full bidirectional XON/XOFF generation,
remote modem negotiation or analogue flow control. The reference's
example uses \X7, but its command table documents only 0 and 1;
other values return ERROR. Other modem profiles remain unchanged.

DataPort 3740 serial connector and receive pacing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The hardware table identifies CN3 as RS-232/422, CN1 as line out,
CN2 as line in, CN4 as DC power, and SW1 as the power switch.
The related DataPort Express installation guide (3715-A2-GB13-00)
describes a 25-pin modem serial plug for PC cables, a Macintosh
hardware-handshake cable, and separate PHONE and LINE jacks.
The exact 3740 RS-422 pin assignment and synchronous clock wiring
remain unverified. Do not equate the computer serial interface
with a telephone line, or the UART DTE speed with the DCE rate.

For the 3740, the default ``\\Q3`` mode now honors the DTE RTS
signal for line-to-guest payload. Deasserting RTS holds received
payload in a separate 64 KiB FIFO; asserting RTS resumes delivery
without a timer. The original AT reply FIFO is retained and
remains independent, including CONNECT and command-mode replies.
TCP backpressure applies when the payload FIFO fills. Escaping
to command mode holds pending line data until returning online;
hangup discards remaining line payload. Other profiles retain
their previous behavior. ``\\Q1`` software pacing still works,
and the documented ``\\D0``/ ``\\D1`` CTS behavior is unchanged.
This is receive-side logical handshaking, not a complete RTS/CTS
transmit-side implementation or an electrical RS-422 transceiver.

References:

* 3740: https://arvutimuuseum.ee/th99/t/P-R/53813.htm
* DataPort Express quick installation guide:
  https://manuzoid.com/manuals/eN66a-Paradyne%20DataPort%20Quick%20start%20guide

External modem indicators
~~~~~~~~~~~~~~~~~~~~~~~~~

In Cocoa (Core Graphics or Metal), View > Modem Indicators opens a
separate optional window for the external 3740 front panel. It shows
one labeled row per backend, including the automatically created
backend of the ISA UART convenience device. Closing this window
does not stop the guest. Internal drive indicators are unchanged.

The nine red labels follow the hardware reference: TST, HS, EC, CD,
OH, RD, SD, TR and MR. MR indicates a powered emulated modem, TR
follows DTR, and CD/OH represent simulated carrier/line engagement
(not a physical telephone line or forced DCD under &C0).
RD and SD observe delivered serial bytes and accepted guest bytes,
including AT traffic. Cocoa retains a flash for 180 ms using host
time; activity counters do not introduce emulated delays.
TST, HS and EC are shown as unavailable until their operating
states are implemented. No claim about electrical GPIO wiring or
negotiated data-pump rates is made.

The observer copies state under BQL and holds no backend pointers.
Polling occurs only while the inspector is open. No guest display,
migration state or VM configuration is changed.

**Scope:** Settings for flow control and reliability are retained and
reported, but transmit-side CTS throttling, V.42/MNP negotiation,
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
