LED and front-panel indicator modelling
======================================

QEMU's ``TYPE_LED`` models a physical LED endpoint.  Machine and device
models should use it to preserve the electrical behaviour of historical
hardware rather than synthesizing a convenient UI animation.

Electrical state is authoritative
---------------------------------

An LED does not own the policy which makes it blink.  The emulated circuit
which drives the LED is the source of truth:

* a power LED follows the emulated power or enable signal;
* a link or activity LED follows the emulated PHY or controller signal;
* a firmware-controlled LED follows the register or GPIO written by firmware;
* a hardware blink or PWM engine must generate the same transitions or duty
  cycle as the emulated hardware.

Do not add a generic timer to the LED merely because the real product blinked.
Doing so loses the distinction between firmware behaviour, controller
behaviour and the physical indicator.

Polarity and reset level
------------------------

The visible state is derived from the electrical input and its polarity.
``gpio-active-high`` describes whether a high input makes the LED emit.
``gpio-reset-level`` describes the electrical level present at reset.

New historical machine models should set the reset level from evidence about
the real circuit, including pull-ups, pull-downs and reset drivers.  The
``led_create_simple_with_reset()`` helper makes this explicit.  The older
``led_create_simple()`` helper retains QEMU's previous effective reset level
for compatibility.

For example, an active-low status LED with a pull-up at reset should be
created active-low with a high reset level, so it begins dark.  An active-high
LED held low by reset logic should use a low reset level.

Intensity and time
------------------

``intensity-percent`` is instantaneous emitted intensity.  Simple digital
indicators normally use 0 or 100 percent.  Intermediate values should only be
used when the emulated hardware really provides an analogue or PWM-derived
intensity.

The LED core does not model human persistence of vision.  It reports exact
emulated transitions through its change-notifier API.  A graphical frontend
may integrate those transitions over its presentation interval so short
activity flashes or high-frequency PWM remain visible, but that averaged
value is presentation state and must not feed back into guest-visible device
state or migration.

Colour and compound indicators
------------------------------

The LED colour describes the light emitted by the physical die.  A bicolour
or multicolour package with independently driven dies should therefore be
modelled as one ``LEDState`` per die.  A frontend may present those dies behind
a shared lens and visually combine simultaneous emission.

Do not represent unrelated technologies such as incandescent lamps, neon
lamps or LCD segments as LEDs solely to reuse a UI element.  They can share a
future front-panel presentation layer while keeping distinct device physics.

Observation and migration
-------------------------

LED objects expose read-only QOM observation properties for
``intensity-percent``, ``emitting`` and ``gpio-level``.  These are intended for
frontends, tests and debugging tools.

Instantaneous emitted intensity and the electrical GPIO level are migrated.
Host-side observers and any frontend persistence or animation state are not.
This keeps migration tied to emulated hardware state rather than to how a
particular host happened to render the front panel.
