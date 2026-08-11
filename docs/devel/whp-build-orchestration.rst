WHP build orchestration
=======================

The WHP entry point is a run of QEMU's build system, not an independent build
system. ``build.sh`` normalizes the shell and platform environment, then
``builder.sh`` executes a small lifecycle:

#. validate the wrapper scripts before loading platform-specific paths;
#. prepare the WHP build profile and host tools;
#. prepare source-backed inputs and build-graph configuration;
#. configure QEMU when the recorded build identity changes;
#. ask GNU Make, Meson, and Ninja to build the requested targets; and
#. verify and record the artifacts produced by that exact run.

``builder.sh`` intentionally contains only that sequence.
``scripts/whp-build/stages.bash`` is the stable loader for four focused
modules: ``prepare-build.bash``, ``prepare-sources.bash``, ``configure.bash``,
and ``build-targets.bash``. Wrapper integrity checks live in
``scripts/whp-build/preflight.bash`` and final artifact checks live in
``scripts/whp-build/post-build.bash``. This keeps the public runner readable
without hiding verification in an unrelated build stage.

Wrapper integrity
-----------------

Every run performs ``sh -n`` or ``bash -n`` checks on the maintained build
entry points and helper scripts, including platform-specific scripts that the
current host would not otherwise execute. Set ``WHP_RUN_SHELLCHECK=1`` to add a
ShellCheck pass when ShellCheck is installed::

  WHP_RUN_SHELLCHECK=1 ./build.sh qemu-system-ppc

The preflight is intentionally limited to wrapper integrity. QEMU's own build
graph remains responsible for compiling source files and deciding which
artifacts are out of date.

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

Targets
-------

With no positional arguments, the run builds ``BUILD_TARGETS``, whose default
is ``all``::

  ./build.sh

Positional arguments select Make targets for that run and take precedence over
``BUILD_TARGETS``::

  ./build.sh qemu-system-ppc

  ./build.sh whp-openbios-ppc

Installation remains an explicit post-build request through ``INSTALL=1``.
It does not become an implicit side effect of an ordinary build.

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

The WHP profile does not use ``--without-default-features``,
``--without-default-devices``, a private device configuration, or overrides
for QEMU's random-number, tracing, debugging, plugin, and TCG-interpreter
defaults. QEMU's configure, Kconfig, and Meson layers remain responsible for
detecting optional host dependencies and selecting their supported defaults.
The wrapper adds only the features that define the WHP host integration and
the requested QEMU target.
