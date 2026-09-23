WHP build orchestration
=======================

The WHP entry point is a run of QEMU's build system, not an independent build
system. ``build.sh`` normalizes the shell and platform environment, then
``builder.sh`` owns both module loading and the small build lifecycle:

#. validate the maintained wrapper scripts when runtime preflight is requested;
#. prepare the WHP build profile and host tools;
#. prepare source-backed inputs and firmware configuration;
#. configure QEMU when the recorded build identity changes;
#. ask GNU Make, Meson, and Ninja to build the requested targets; and
#. verify and record the artifacts produced by that run.

The focused ``scripts/whp-build/*.bash`` modules define individual stages but
do not maintain another ordered stage list. ``builder.sh`` sources those
modules directly beside the sequence that executes them, so module membership
and execution order have one production owner. Wrapper integrity checks live
in ``scripts/whp-build/preflight.bash`` and final artifact checks live in
``scripts/whp-build/post-build.bash``.

Shell contract
--------------

``build.sh`` and ``scripts/macos-builder.sh`` are small POSIX ``sh`` launchers.
They locate GNU Bash 3.2 or newer, clear shell startup inputs such as
``BASH_ENV``, ``ENV``, ``POSIXLY_CORRECT``, ``SHELLOPTS``, and ``BASHOPTS``,
and then enter the Bash orchestration layer with ``--noprofile --norc``.

``WHP_BUILD_BASH`` is the single public shell selector. The selected Bash path
is also used as ``CONFIG_SHELL`` for nested configure recursion. There is no
separate QEMU or PowerPC-toolchain shell selector. ``BOOTSTRAP_BASH=auto``
uses the pinned WHP Bash fork by default on macOS, where the system Bash is
historically old, while other hosts keep a usable host Bash first and fall
back to the pinned fork when needed. An explicit ``WHP_BUILD_BASH`` always
wins.

The implementation scripts use Bash arrays, ``[[ ... ]]``, ``pipefail``, and
other Bash syntax. Do not run ``builder.sh`` or the ``scripts/whp-build/*.bash``
implementation files through ``sh``, ``dash``, or ``zsh``. Use the public
launcher instead::

  ./build.sh

A lightweight shell check is available without starting a build::

  WHP_SHELL_PROBE_ONLY=1 ./build.sh

Set ``WHP_RUN_SHELLCHECK=1`` to add ShellCheck during preflight when it is
installed.

Source refresh
--------------

Normal local ``./build.sh`` runs refresh the checkout before Python,
toolchain, or QEMU configuration discovery.  ``WHP_SOURCE_UPDATE=auto`` is
the default.  It fast-forwards only the current QEMU branch from its configured
upstream and then synchronizes and initializes the exact recursive submodule
revisions recorded by that QEMU commit.

The refresh deliberately uses ``git pull --ff-only`` and never resets,
cleans, rebases, or follows arbitrary submodule branch tips.  QEMU's gitlinks
remain authoritative because firmware and toolchain bootstrap guards depend on
those exact revisions for reproducible builds.

If the QEMU commit changes, the launcher re-executes the newly pulled
``build.sh`` before continuing.  This prevents an older launcher from driving
newer orchestration helpers in the same build.

Automatic refresh is skipped for CI, ``menuconfig``, and build/shell/portable
probe invocations so those operations stay side-effect free.  Set
``WHP_SOURCE_UPDATE=0`` to disable refresh completely.  Set
``WHP_SOURCE_UPDATE=1`` to require it; unsafe states such as tracked source
changes, a detached QEMU checkout, no configured upstream, or tracked
submodule changes then fail instead of silently building older sources.
In ``auto`` mode the same conditions produce a warning and preserve the
current checkout.

Build-graph ownership
---------------------

QEMU's existing configure, Meson, and Ninja layers own dependency tracking and
artifacts. The WHP preparation stage may generate inputs consumed while QEMU
is configured, but it must not compile an artifact before entering the build
graph.

OpenBIOS follows this rule on every host. The preparation stage writes
``BUILD_DIR/.whp-openbios-meson.env`` and ``pc-bios/meson.build`` declares the
``whp-openbios-ppc`` target. The firmware, cross-toolchain bootstrap, and their
incremental stamps are therefore reached through one Meson/Ninja edge.
Setting ``BUILD_OPENBIOS=0`` removes the generated graph input and selects the
checked-in firmware blob instead.

Configuration menu
------------------

Run ``./build.sh menuconfig`` to edit the persistent ``.whpconfig`` build
profile. The menu is the single portable interface for host features,
firmware, machines, build behavior, hardware filters, and build outputs.
Explicit environment variables remain one-run overrides of the saved values.

Each menu item carries its own repository default; optional diagnostics,
installation, and some build outputs are deliberately opt-in. The build-output
section includes ``qemu-img`` and the supported ``qemu-system-*`` selectors.
Disabling ``qemu-img`` passes ``--disable-tools`` to QEMU; enabling it passes
``--enable-tools``. The system-emulator selections derive QEMU's internal
target list, so the menu does not expose a conflicting raw target-list field.
Disabling every system emulator passes ``--disable-system`` for a tools-only
build.

The ``QEMU hardware`` section is device-first. Each currently exposed audio
model appears once, with independent ``i386`` and ``ppc`` choices underneath:
Sound Blaster 16, AdLib, Gravis UltraSound, Crystal CS4231A, PC speaker,
Ensoniq ES1370, Intel AC'97, Crystal CS4630, and Intel HD Audio. Each target
choice is three-state: ``auto``, ``y``, or ``n``. ``auto`` leaves QEMU's
Kconfig decision and dependency handling unchanged for that architecture.

Explicit ``y`` or ``n`` values are written as only the requested ``CONFIG_*``
overrides in the matching architecture preset, such as
``configs/devices/i386-softmmu/whp-user.mak`` or
``configs/devices/ppc-softmmu/whp-user.mak``. QEMU then receives the supported
``--with-devices-i386=whp-user`` or ``--with-devices-ppc=whp-user`` configure
hook for the affected target. An i386 choice never changes the PowerPC preset,
and a PowerPC choice never changes the i386 preset.

Meson records each selected architecture-scoped preset as a source input, so
an ignored generated ``whp-user.mak`` remains present while that custom device
profile is active. It is removed only after a successful configuration has
switched the architecture back to QEMU's tracked ``default.mak`` preset. This
also lets the wrapper reconstruct a missing ignored preset before reusing an
otherwise unchanged Meson/Ninja configuration.

The portable Python fallback does not currently materialize target-specific
device presets. It therefore fails closed when any explicit ``QEMU hardware``
filter is requested instead of silently ignoring it. Leaving hardware choices
on ``auto`` continues to use QEMU's tracked Kconfig defaults and dependencies.

Incremental policy
------------------

Incremental builds are the default. ``WHP_INCREMENTAL_BUILD=1`` preserves the
QEMU Ninja tree, reuses a valid OpenBIOS configuration, and reuses a valid
PowerPC toolchain cache. QEMU configuration is rerun only when its recorded
identity changes.

For a deliberately fresh firmware/toolchain pass use::

  WHP_INCREMENTAL_BUILD=0 ./build.sh

The narrower ``OPENBIOS_FORCE_RECONFIGURE`` and
``POWERPC_TOOLCHAIN_FORCE_REBUILD`` controls remain diagnostic overrides for
one component; they are not separate build modes.

Targets
-------

With no positional arguments, the run builds ``BUILD_TARGETS``, whose default
is ``all``::

  ./build.sh

Positional arguments select Make targets for that run and take precedence over
``BUILD_TARGETS``::

  ./build.sh qemu-system-ppc

  ./build.sh whp-openbios-ppc

Installation follows the ``Install after build`` menu Boolean and is opt-in in
a new profile. Set ``INSTALL_AFTER_BUILD=1`` when installation is wanted; compile-only
runs keep ``INSTALL_AFTER_BUILD=0``. The generic ``INSTALL`` name is reserved
for build systems that use it to name the installation command.

Artifact identity
-----------------

After a PowerPC emulator build, the wrapper executes the newly produced
``BUILD_DIR/qemu-system-ppc`` rather than an installed or PATH-selected QEMU.
It checks that the base ``mac99`` machine and the historical
``powermac3_1`` profile are registered. A failed registration therefore makes
the build fail instead of producing a misleading success message.

Each successful run writes ``BUILD_DIR/.whp-build-artifacts``. The manifest
records the source revision, requested targets, target list, exact emulator
path, emulator version and checksum, and the OpenBIOS output when present. Use
that path when launching or reporting a test so source state is not confused
with an older installed executable.

Configure defaults
------------------

The WHP profile does not replace QEMU's supported configure, Kconfig, or Meson
defaults with a private feature matrix. The wrapper adds only the host policy,
firmware integration, and explicit target/device choices requested by the WHP
build profile. Device choices left on ``auto`` remain owned by QEMU's Kconfig
defaults and dependencies.
