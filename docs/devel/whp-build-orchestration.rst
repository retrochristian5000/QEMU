WHP build orchestration
=======================

The WHP entry point is a run of QEMU's build system, not an independent build
system.  ``build.sh`` normalizes the shell and platform environment, then
``builder.sh`` executes four explicit stages:

#. prepare the WHP build profile and host tools;
#. prepare source-backed inputs and build-graph configuration;
#. configure QEMU when the recorded build identity changes; and
#. ask GNU Make, Meson, and Ninja to build the requested targets.

``builder.sh`` intentionally contains only that sequence.  The stage
implementation lives in ``scripts/whp-build/stages.bash`` so policy and
validation can evolve without turning the run script back into the owner of
build artifacts.

Build-graph ownership
---------------------

QEMU's existing configure, Meson, and Ninja layers own dependency tracking and
artifacts.  The WHP preparation stage may generate inputs consumed while QEMU
is configured, but it must not compile an artifact before entering the build
graph.

OpenBIOS follows this rule on every host.  The preparation stage writes
``BUILD_DIR/.whp-openbios-meson.env`` and ``pc-bios/meson.build`` declares the
``whp-openbios-ppc`` target.  The firmware, cross-toolchain bootstrap, and
their incremental stamps are therefore reached through one Meson/Ninja edge.
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
