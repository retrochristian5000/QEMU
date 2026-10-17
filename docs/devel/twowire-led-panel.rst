2Wire 2701HG-B visible LED output
=================================

This component is an incremental front-panel output for the historical AT&T
2Wire 2701HG-B research target. Evidence associates Ares with the
TriMedia TM32/TM3260 processor family, but exact silicon markings,
physical GPIO numbers, polarity and MMIO remain unverified. See ``docs/devel/twowire-ares-identity.rst`` for its IDCODE evidence.
There is no complete 2701HG-B machine definition yet: this system-bus device is available for
later board wiring and produces a separate QEMU graphical console when
instantiated.

Five legends are visible, in order: POWER, ETHERNET, WIRELESS, DSL,
INTERNET. Their light-emission states come from existing TYPE_LED child
devices, with independently observable read-only QOM properties.

Eight named "emission" inputs provide logical colour output only.
They are documented in include/hw/display/twowire-led-panel.h. Board
code can connect to these through qdev_get_gpio_in_named(dev, "emission",
channel). The panel never guesses the physical GPIO mapping, invents a
guest-visible MMIO register, or generates its own blink clock.

POWER has green, orange and red presentation channels. ETHERNET,
WIRELESS and DSL have green channels. INTERNET has green and red
channels. A conflicting simultaneous command is resolved only by
presentation priority (red, orange, green), never by changing hardware
state. The logical channels do not prove physical LED die count.

POST, flash upgrade, Ethernet/Wi-Fi traffic, DSL training, and PPP
authentication will eventually drive those inputs through verified board
devices and firmware. The front panel does not independently simulate
a working network or an invented sequence of LED changes.

Period sources (model-specific variations still require checking):
https://manuzoid.com/manuals/GwMNK-2Wire%202701hg-b%20User%20manual
https://manuzoid.com/manuals/xkG0b-2Wire%202701hg-b%20Owner%27s%20manual

Voltage-domain evidence and the boundary between physical LED drive and
logical QEMU output are tracked in
``docs/devel/twowire-voltage-domains.rst``. Do not connect the 5.1 V
adapter directly to an LED GPIO merely because it shares this model.

Static integration test:
python3 scripts/tests/test-twowire-led-panel.py
