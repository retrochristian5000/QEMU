WHP build orchestration
=======================

The WHP entry point is a run of QEMU's build system, not an independent build
system. ``build.sh`` normalizes the shell and platform environment, then
``builder.sh`` executes a small lifecycle:

#. validate the maintained wrapper scripts;
#. prepare the WHP build profile and host tools;
#. prepare source-backed inputs and firmware configuration;
#. configure QEMU when the recorded build identity changes;
#. ask GNU Make, Meson, and Ninja to build the requested targets; and
#. verify and record the artifacts produced by that run.

``builder.sh`` intentionally contains only that sequence.
``scripts/whp-build/stages.bash`` loads the focused preparation,
source-input, configuration, and build-target modules. Wrapper integrity checks
live in ``scripts/whp-build/preflight.bash`` and final artifact checks live in
``scripts/whp-build/post-build.bash``.

Shell contract
--------------

``build.sh`` and ``scripts/macos-builder.sh`` are small POSIX ``sh`` launchers.
They locate GNU Bash 3.2 or newer, clear shell startup inputs such as
``BASH_ENV``, ``ENV``, ``POSIXLY_CORRECT``, ``SHELLOPTS``, and ``BASHOPTS``,
and then enter the Bash orchestration layer with ``--noprofile --norc``.

``WHP_BUILD_BASH`` is the single public shell selector. The selected Bash path
is also used as ``CONFIG_SHELL`` for nested configure recursion. There is no
separate QEMU or PowerPC-toolchain shell selector.

The implementation scripts use Bash arrays, ``[[ ... ]]``, ``pipefail``, and
other Bash syntax. Do not run ``builder.sh`` or the ``scripts/whp-build/*.bash``
implementation files through ``sh``, ``dash``, or ``zsh``. Use the public
launcher instead::

  ./build.sh

A lightweight shell check is available without starting a build::

  WHP_SHELL_PROBE_ONLY=1 ./build.sh

Set ``WHP_RUN_SHELLCHECK=1`` to add ShellCheck during preflight when it is
installed.

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
firmware, machines, build behavior, and build outputs. Explicit environment
variables remain one-run overrides of the saved values.

Every Boolean menu item is enabled in a new profile. The build-output section
includes ``qemu-img`` and ``qemu-system-i386``. Disabling ``qemu-img`` passes
``--disable-tools`` to QEMU; enabling it passes ``--enable-tools``. Enabling
``qemu-system-i386`` adds ``i386-softmmu`` to the saved target list, while
disabling it removes that target. An explicitly supplied
``QEMU_TARGET_LIST`` environment value remains authoritative.

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

Installation follows the ``Install after build`` menu Boolean, which is
enabled in a new profile. Set ``INSTALL=0`` for a compile-only run.

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
firmware integration, and requested target choices required by the WHP build.
