Standalone SIP SDK foundation
=============================

Liblinphone is an optional host dependency for a future telephone
service. QEMU's emulator is GPLv2; current Liblinphone SDK releases
are AGPLv3 or commercially licensed. Do not link the SDK into the
emulator, load it as an emulator plugin, or copy its code into QEMU.
The standalone sdk-check.c source is MIT-licensed. Distribution of
the linked helper must comply with the SDK's actual license and
dependency licenses; process separation alone is not a legal
determination about future integration.

Build
-----

Install a supported Liblinphone 5.3 or later development SDK from a
trusted host package or the upstream SDK distribution. The initial
integration uses the ``linphone.pc`` pkg-config metadata (available
in Debian's liblinphone-dev package). SDKs that provide only CMake
metadata are not yet supported by this build option. No dependencies
are fetched automatically. Set PKG_CONFIG_PATH to the installed
SDK's pkg-config directory if necessary, matching the host ABI.

From the QEMU source tree, use the existing configure workflow::

    ./configure --enable-liblinphone
    ninja -C build qemu-sip-sdk-check
    ./build/tools/sip/qemu-sip-sdk-check --version
    meson test -C build --suite sip

Adjust the build directory to match your configuration. The helper
is not installed by default. The option defaults to disabled and
explicit enablement requires successful C header and link checks.
The SDK must match the host architecture, not the guest CPU.

Scope
-----

The current helper only checks the linked SDK's version. It creates
no SIP core, credentials, sockets, accounts, calls, microphone access
or audio streams. The DataPort 3740 remains disconnected in its
integrated ISA profile; existing chardev TCP behavior is unchanged.

Future work should implement an independent service process with
a documented, versioned local IPC interface. Keep SIP credentials in
host-owned configuration, use explicit host authorization and allowed
destinations, validate TLS certificates, and never let guest dial
strings select arbitrary network endpoints. Keep call progress and
carrier detection independent; SIP answer is not modem training.
G.711 PCM transport and modem DSP must be implemented and verified
separately before claiming telephone or V.34 connectivity.

References:

* https://www.linphone.org/en/liblinphone-voip-sdk/
* https://www.linphone.org/en/faq/
* https://download.linphone.org/releases/docs/liblinphone/5.3/c/
