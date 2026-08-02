Explicit macOS SDK builds
=========================

The recommended macOS entry point is::

  bash scripts/macos-builder.sh

The wrapper selects the active Apple developer directory and macOS SDK before
calling ``builder.sh``.  It makes the SDK and deployment policy explicit in
all QEMU host compile and link flags instead of relying only on inherited
environment behavior.

Selected build policy
---------------------

``scripts/macos-builder.sh``:

* resolves ``DEVELOPER_DIR`` through ``xcode-select`` unless it was supplied;
* resolves ``SDKROOT`` and the SDK version through ``xcrun``;
* defaults ``MACOSX_DEPLOYMENT_TARGET`` to the running macOS major and minor
  version;
* rejects a deployment target newer than the selected SDK;
* rejects an Arm deployment target older than macOS 11.0;
* adds the selected SDK with ``-isysroot`` to C, C++, Objective-C, and linker
  flags;
* adds the same ``-mmacosx-version-min`` value to those four flag groups; and
* delegates architecture, Rosetta, Homebrew, compiler, LTO, firmware, and
  QEMU configuration checks to the WHP build stages.

This keeps configure probes, Meson host objects, Cocoa code, and final links on
one SDK and minimum-version policy.  The Meson OpenBIOS adapter removes the
QEMU host flags when its firmware edge runs, so the macOS SDK does not leak
into firmware compilation.

Deployment overrides
--------------------

Set a lower deployment target explicitly when producing a binary for another
supported macOS release::

  MACOSX_DEPLOYMENT_TARGET=14.0 \
  bash scripts/macos-builder.sh

Select a particular installed SDK through ``DEVELOPER_DIR`` or ``SDKROOT``::

  DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  bash scripts/macos-builder.sh

  SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
  bash scripts/macos-builder.sh

The wrapper rejects ``-isysroot``, ``--sysroot``, or
``-mmacosx-version-min`` already embedded in ``CFLAGS``, ``CXXFLAGS``,
``OBJCFLAGS``, ``CPPFLAGS``, or ``LDFLAGS``.  Use ``SDKROOT`` and
``MACOSX_DEPLOYMENT_TARGET`` as the single source of truth instead.  Advanced
configurations that intentionally manage all flags themselves may call
``builder.sh`` directly.

Architecture examples
---------------------

Native Apple Silicon::

  arch -arm64 bash scripts/macos-builder.sh

An intentional Intel build under Rosetta::

  arch -x86_64 env MACOS_ALLOW_ROSETTA=1 \
  bash scripts/macos-builder.sh

The existing Homebrew-prefix and compiler-identity guards still apply to both
modes.
