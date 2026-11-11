i440fx PC (``pc-i440fx``, ``pc``)
=================================

Peripherals
~~~~~~~~~~~

.. include:: ../target-i386-desc.rst.inc

Host laptop battery snapshot for legacy SeaBIOS APM
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On supported laptop hosts, the WHP QEMU fork can opt in to reading the
**host's internal battery** at VM startup and forward an eight-byte APM 1.2
snapshot to the matching WHP SeaBIOS firmware::

    qemu-system-i386 -machine pc,host-battery=on

This option is disabled by default. On macOS, QEMU uses IOKit's power-source
API and ignores external UPSs. On Linux, it reads the host's
``/sys/class/power_supply`` interface. It reports the observed AC line,
charge percentage, charging status, and remaining discharge time (when
available), without giving the guest access to host battery control.

The interface requires exactly one readable internal host battery. If none
is found, multiple internal batteries are present, or the host platform does
not support the reader, ``host-battery=on`` fails explicitly instead of
fabricating an emulated battery. Without the option, no host power source
is exported. This is intentionally independent of the Dell-style POST UI
and works with the existing SeaBIOS APM 1.2 overlay protocol.

**Runtime limitation:** the current SeaBIOS firmware caches this record
once during POST. The guest does not receive ongoing updates, lid events,
hot-swap notifications, or charge changes after boot. Host state is sampled
when QEMU creates the firmware configuration, not continuously. The
``opt/org.seabios/whp-laptop-apm`` fw_cfg entry holds the protocol version
and battery fields documented in ``roms/seabios/docs/Runtime_config.md``.
Use a separate future runtime/ACPI device protocol for live monitoring;
do not confuse this static bridge with battery hardware passthrough or
host sleep/suspend passthrough.

For deterministic test scenarios, leave ``host-battery`` off and provide
a deliberately constructed firmware record using ``-fw_cfg``. Do not specify
the record manually at the same time as ``host-battery=on`` because both
paths would attempt to publish the same fw_cfg filename.
