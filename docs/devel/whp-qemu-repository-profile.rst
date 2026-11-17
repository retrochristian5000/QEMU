.. _whp-qemu-repository-profile:

WHP QEMU repository profile and repair evidence
===============================================

Scope and authority
-------------------

This document keeps QEMU-specific implementation details inside the QEMU
repository. Its source code, local developer documentation, tests and Git
history govern behavior. The WHP universal programming standard in Notion
is cross-repository guidance, not a competing QEMU specification.

Repository: `retrochristian5000/QEMU <https://github.com/retrochristian5000/QEMU>`_.
Published repairs described below were made on the existing ``master``
branch. Recheck the current ref and code before applying historical claims.

QEMU authorities
----------------

* ``docs/devel/style.rst``: QEMU C style, C11 baseline and checkpatch rules.
* :doc:`whp-build-orchestration`: ``build.sh`` and build-stage ownership.
* :ref:`whp-dependency-ledger`: source pins, managed dependencies, build
  graph, host-tool roots and non-rewinding submodule policy.
* :doc:`macos-build`: selected macOS developer tools, SDK, deployment
  target, host compiler and target ABI boundaries.
* ``scripts/whp-build/update-source.sh``: guarded source refresh.
* ``scripts/whp-config/config.py``: QEMU configuration schema and handoff.
* ``seeds/`` and ``scripts/whp-build/seed-bin/``: QEMU host-tool selection.

C language compatibility and targeted modernization
-------------------------------------------------

The universal C profile is guidance, not a command to adopt C23 everywhere.
QEMU's ``meson.build`` currently defaults to ``c_std=gnu11``; keep that
baseline unless a separate compatibility decision changes the supported
compiler matrix. The ``macio-c23.yml`` workflow checks selected PowerPC
MacIO sources under ``gnu23`` and does not establish whole-tree C23 support.
Modern C11 source may retain QEMU-approved GCC/Clang extensions; do not
silently substitute a target compiler for ``CC_FOR_BUILD`` or conflate the
host SDK, ABI, object format and C language edition.

Classify K&R definitions, missing prototypes, obsolete libraries, historical
compiler workarounds and older C keywords by their *actual* semantics. A
keyword introduced in C23 is not evidence that a legitimate guest-visible
field should be renamed globally. Changes to firmware formats, wire layouts,
guest APIs or calling conventions require their own compatibility tests.

One bounded remediation is ``hw/ppc/vof.c::prop_format``: Open Firmware
property trace output must not rely on ``strncpy`` termination or unchecked
string concatenation. The formatter now terminates within the supplied
diagnostic buffer and bounds binary-hex output; the firmware property payload
and its on-wire representation remain untouched. The focused host-side C11
regression ``scripts/tests/test-vof-property-format.py`` compiles that
function and probes zero/small buffers, text and binary inputs, and byte
canaries. It is not an end-to-end guest Open Firmware test. Validate the
affected subsystem and guest behavior separately before making wider
compatibility claims.

macOS platform and SDK provenance
---------------------------------

Native QEMU seed, LLVM and managed host-tool builds must use the selected
macOS developer directory and macOS SDK, not the iPhoneOS, iPhoneSimulator
or other Apple platform. This is distinct from selecting an AArch64 CPU:
``arm64`` alone does not establish the OS, runtime, ABI or sysroot.
``scripts/whp-build/macos-developer-tools.sh`` validates physical SDK
directories, required macOS headers and selected developer-root containment,
then rejects non-macOS ``Platforms/*.platform`` subtrees for both SDKs and
developer tools. Legitimate Xcode ``Platforms/MacOSX.platform/Developer``
paths and standalone Command Line Tools SDK paths remain permitted.

The native LLVM stage separately checks compiler target triples and effective
``TargetConditionals.h`` host-platform macros and passes explicit
``CMAKE_OSX_SYSROOT`` and deployment targets to its CMake subprojects.
These guards must not be repurposed to prohibit deliberate QEMU guest
cross-compilation; native build tools and guest objects have different target
contracts. The synthetic regression in
``scripts/tests/test-macos-developer-tools.bash`` exercises developer
SDK/tool origin, wrong-platform SDKs named ``MacOSX.sdk``, and legitimate
macOS platform paths. Fixture checks are not a native macOS build.

Host compiler and copy seed contracts
-------------------------------------

QEMU separates native **build-machine** compilers from compilers and tools
producing QEMU's **host artifacts**. A guest architecture (for example
``ppc-softmmu``) is a third role, not the meaning of ``CC``. Firmware and
cross-toolchain target compilers have their own contracts. The native
``seeds/cc.sh``, ``seeds/cxx.sh``, ``seeds/cpp.sh`` and ``seeds/ld.sh``
validate their respective tools; an executable name or successful version
probe alone is not an ABI guarantee.

Build-variable role and precedence
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``WHP_CC_SEED`` / ``WHP_CXX_SEED``
    Explicit seed-adapter compiler requests for native C and C++ tools.
    They take precedence over ``CC_FOR_BUILD`` / ``CXX_FOR_BUILD``
    during seed selection. Invalid nonempty choices fail closed.

``CC_FOR_BUILD`` / ``CXX_FOR_BUILD`` / ``OBJC_FOR_BUILD``
    Compiler executables for tools that **run on the build machine**.
    The public ``build.sh`` resolves native C/C++ seeds early. Standalone
    non-macOS preparation defaults to ``cc`` / ``c++`` and uses
    ``CC_FOR_BUILD`` for Objective-C when no explicit value was given.
    These defaults do not copy the configured QEMU artifact compilers.
    An explicit ``*_FOR_BUILD`` selection remains authoritative.

``WHP_CPP_SEED`` / ``CPP_FOR_BUILD``
    The former selects a native preprocessing driver; the latter is the
    callable ``seeds/cpp.sh`` bridge that guarantees preprocessing
    rather than compilation. ``build.sh`` rejects independent conflicting
    explicit selections. Neither name replaces QEMU's ``CPP``.

``WHP_AR_SEED`` / ``WHP_RANLIB_SEED`` / ``WHP_LD_SEED``
    Explicit native bootstrap-tool requests, ahead of their
    ``AR_FOR_BUILD`` / ``RANLIB_FOR_BUILD`` / ``LD_FOR_BUILD``
    counterparts. The latter carry resolved **build-machine** archiver,
    archive indexer and relocatable linker choices, respectively.
    ``LD_FOR_BUILD`` is not a request to change the final QEMU linker.

``CC`` / ``CXX`` / ``OBJC`` / ``CPP``
    Configured compilers and preprocessor for QEMU **host artifacts**.
    They may use managed native LLVM or an explicit host-cross toolchain.
    These variables are not bootstrap compiler fallbacks. A build-stage
    compiler cache may wrap ``CC`` and ``CXX`` without wrapping
    ``CC_FOR_BUILD`` and ``CXX_FOR_BUILD``.

``AR`` / ``RANLIB`` / ``NM`` / ``LD``
    Archive, indexing, symbol reading and linker selection for QEMU
    artifacts. Libtool can supply a validated alternative archive family;
    the selected native-object pipeline is tested together. Final
    executable links normally go through compiler drivers; on macOS an
    ``LD`` executable alone does not override the driver's linker.
    ``QEMU_HOST_LINKER`` and validated linker flags own that request.

``WHP_NATIVE_LLVM_ARCHIVE_PROVIDER``
    Controls only the **cache-miss native LLVM build-machine** archive pair:
    ``auto`` (default), ``native``, ``gnu``, or ``llvm``.
    Auto prefers an installed LLVM pair for a Clang compiler and GNU Binutils
    pair for GCC, but only when the entire native archive/indexer pipeline
    passes. It falls back to the existing native pair otherwise.
    Explicit seed paths and forced providers fail closed on conflicts or
    missing companion tools. This does not change QEMU's final artifact
    archive family or force managed LLVM to bootstrap itself.

``WHP_GNU_AR_SEED`` / ``seeds/GNUar.sh``
    An optional, case-sensitive selector for an **installed GNU Binutils
    archiver**. GNU identity is checked before reusing the native object,
    archive, index, link and execute probe in the general ``ar.sh`` seed.
    ``--print-candidate`` is identity-only; ``--print-seed`` and
    ``--check`` validate native capability. It does not overwrite
    ``WHP_AR_SEED``, ``AR_FOR_BUILD``, QEMU's ``AR``, or any ranlib
    selection. GNU ``--plugin`` support is not proof that a matching GCC
    LTO plugin has been installed and tested.

``WHP_LLVM_AR_SEED`` / ``NATIVE_LLVM_DIR``
    The former optionally selects an **installed** native LLVM archiver;
    the latter identifies the managed LLVM toolchain prefix. Neither is
    an alias for ``AR_FOR_BUILD``, ``AR`` or GNU linker-plugin support.

``MAKE_CMD`` / ``MAKE`` / ``WHP_MAKE_SEED``
    The public entry intentionally publishes the same validated GNU Make
    choice under these existing consumer interfaces. Do not generalize
    this specific handoff to compiler and linker variables.

``DEVELOPER_DIR`` / ``SDKROOT``
    On macOS, the selected Xcode/CLT root and its matching SDK. SDK
    validation is independent of compiler naming, host CPU, and ABI.

``CFLAGS`` / ``CXXFLAGS`` / ``CPPFLAGS`` / ``LDFLAGS``
    Flag interfaces, not tool selectors. Their effects depend on the
    consuming stage; QEMU-only LTO and host-CPU tuning must not leak
    into native bootstrap, guest firmware or cross-toolchain probes.
    Libtool's ``ARFLAGS`` / ``AR_FLAGS`` spellings are archive **flags**,
    not a second archiver selection.

One variable must not silently replace a different role. A user can
intentionally choose the same executable for both roles by setting the
respective variables explicitly; capability probes still decide whether
that pairing is usable. Keep ``WHP_*_SEED`` selectors and ordinary
``*_FOR_BUILD`` outputs distinct, rather than adding another alias layer.

``seeds/git.sh``, ``seeds/awk.sh``, ``seeds/grep.sh``, ``seeds/sed.sh``,
``seeds/cp.sh`` and ``seeds/install.sh`` provide other selected host tools. The public
``build.sh`` selects a copy implementation before source refresh and uses
``scripts/whp-build/seed-bin/cp`` for literal ``cp`` calls. Its copy probes
cover ordinary files, POSIX ``-R`` and ``-p``; they do not establish
support for every GNU, BSD or Apple-specific copying extension.

GNU Autotools seed pairing
^^^^^^^^^^^^^^^^^^^^^^^^^^

``seeds/automake.sh`` and ``seeds/autom4te.sh`` validate the
``automake``/``aclocal`` and ``autom4te``/``autoconf`` release pairs.
Implicit discovery requires the adjacent sibling from the selected
installation; a same-version executable elsewhere on ``PATH`` is not
sufficient evidence of a matching installation. Deliberately split
installations remain supported when both tool paths are explicitly selected
and their identities and versions validate. The host-tools stage emits
newline-delimited versions for deterministic pair comparison.

The new ``seeds/autoconf.sh`` is a POSIX entrypoint for **installed**
GNU Autoconf. It delegates provider resolution, version matching, and
explicit split-installation checks to ``seeds/autom4te.sh``, rather than
maintaining a second provider search. ``--print-seed`` returns the Autoconf
executable, ``--print-autom4te`` returns its validated companion,
``--check`` inspects both, and normal arguments execute Autoconf.
Both adapters reject recursive adapter selections, including symlink aliases.
The seed does not bootstrap Autoconf from its own unfinished output; the
managed Automake bootstrap consumes this independent seed pair.
``scripts/tests/test-autoconf-seed.py`` covers the focused behavior.

Native Homebrew package-manager seed
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The POSIX ``seeds/brew.sh`` adapter validates an installed Homebrew executable
and its active prefix before the macOS QEMU dependency-provider stage. Explicit
``WHP_BREW_SEED`` and the existing ``WHP_HOMEBREW_BREW`` lock must agree;
a mismatched ``HOMEBREW_PREFIX`` fails rather than selecting another
installation. The selected executable is published as
``WHP_HOMEBREW_BREW`` for existing formula inventory and firmware consumers.
The selected architecture and the current ``MACOS_ALLOW_MIXED_HOMEBREW``
policy remain authoritative; MacPorts and the system provider are distinct.

``/bin/sh seeds/brew.sh --check`` and ``--print-seed`` are read-only.
A deliberate ``/bin/sh seeds/brew.sh install <formula>`` forwards to the
selected package manager and may use the network, but QEMU does not install
Homebrew, run a remote installer, or change formulae automatically merely
because a dependency is missing. The build still validates the resulting
headers, libraries and package metadata before using them.
``scripts/tests/test-brew-seed.py`` exercises offline admission, prefix
conflicts, explicit command forwarding and recursion.

Host install seed
^^^^^^^^^^^^^^^^^

The public entry selects ``seeds/install.sh`` once before source refresh,
and ``scripts/whp-build/seed-bin/install`` resolves literal ``install``
commands through the locked ``WHP_INSTALL_SEED`` executable. The seed
probes the native utility's common GNU/BSD operations: creating directories,
installing non-executable data, installing executable files, and replacing
existing files. An invalid explicit override fails closed instead of
silently selecting another tool. ``--print-seed`` and ``--check``
are available for direct diagnosis; ``WHP_INSTALL_VERBOSE=1`` enables a
short per-invocation trace to stderr without changing the command's output.

This is a build-machine command selection, not a request for ``make install``,
a guarantee of GNU-specific ``install`` extensions, or an override of
Autotools' ``INSTALL`` / ``INSTALL_PROGRAM`` variables. Managed third-party
Autotools stages must still perform their independent install-target and
artifact checks. ``scripts/tests/test-install-seed-adapter.bash``
exercises the native adapter and literal bridge on Linux and macOS.

GNU-specific C++ probe: ``seeds/g++.sh`` is an optional native GNU
G++ selector, with ``WHP_GXX_SEED`` / ``GXX`` provider identity
independent of ``WHP_CXX_SEED`` and ``CXX_FOR_BUILD``.
Apple's executable named ``g++`` may be Clang, and Clang's
``__GNUC__`` macro is only GCC compatibility. The GNU seed checks
the GCC frontend, C++17 native execution and C++ standard-library
linking; it never automatically replaces Clang or builds GCC.

Host version and source pin comparison
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Run ``/bin/sh scripts/whp-build/host-version-report.sh`` from a checkout
to collect the same read-only, key/value report used by macOS CI. It records
the actual macOS version, selected Xcode/Command Line Tools directory,
macOS SDK and Clang version, executable discovery paths, host utility
versions, and the superproject's pinned toolchain gitlinks. A separately
checked-out submodule is reported as ``match``, ``drift``, or
``uninitialized``, rather than assuming the working tree matches the
gitlink. An explicit ``SDKROOT`` or ``DEVELOPER_DIR`` is reported separately
from the default discovered by ``xcrun``.

GitHub-hosted image labels, the actual installed tools and the pinned WHP
source revisions are three distinct version boundaries. CI prints this report
both before and, where practical, after Homebrew dependency installation.
A report is diagnostic only: it does not install or upgrade anything, choose
different tools, or establish that a particular compiler/SDK combination
will build the complete emulator. Compare the same keys on the local host
and in CI logs before assuming the runner reproduces a developer-machine
failure.

QEMU repair evidence — 2026-11-09
--------------------------------

ARM64e target identity
^^^^^^^^^^^^^^^^^^^^^

`QEMU commit 77747d65 <https://github.com/retrochristian5000/QEMU/commit/77747d65dddd74632d08876a550648c93cd02f5b>`_
updated ``scripts/whp-build/macos-target-abi.bash`` to distinguish explicit
``arm64e`` from ordinary ``arm64`` or ``aarch64`` triples. Cases for
``arm64e-apple-macosx`` and ``arm64e-apple-darwin`` were added to
``scripts/tests/test-native-llvm-macos-default-triple.py``. A standalone
Bash reproduction passed; full Python, native macOS, linker and runtime
checks were not run. ARM64e CPU features, Clang resource headers, BF16 and
ThinLTO remain separate unresolved investigations.

Native C/C++ seed pairing
^^^^^^^^^^^^^^^^^^^^^^^^^

`QEMU commit 509c06ec <https://github.com/retrochristian5000/QEMU/commit/509c06ecb41101c2a25aa628331466a827cb75fb>`_
changed ``seeds/cxx.sh`` so an explicit native C seed cannot silently
fall back to an unrelated Apple Clang++ when its paired C++17 driver fails.
An independently explicit, validated C++ selection remains permitted;
automatic discovery retains the Apple fallback. The synthetic Darwin
fixture in ``scripts/tests/test-bootstrap-compiler-policy.py`` was added
but not executed in that repair session.

Host copy seed
^^^^^^^^^^^^^^

`QEMU commit 7a400c2a <https://github.com/retrochristian5000/QEMU/commit/7a400c2a8c1bc8d9e6749b8d2f2e4bc0963f62aa>`_
added ``seeds/cp.sh``, a literal-command launcher, early bootstrap
selection and ``scripts/tests/test-cp-seed-adapter.bash``. The seed
accepts ``WHP_CP_SEED``, offers ``--print-seed`` and ``--check``,
and validates basic copying, ``-R`` and ``-p``. The regression was
committed but not executed in that repair session.

Each repair was pushed to ``master`` and the remote Git tree was checked
at publication time. This establishes publication and recorded file modes,
not a successful full QEMU/LLVM build.

Unverified execution and follow-up
----------------------------------

Run applicable focused tests from an actual QEMU checkout::

  python3 scripts/tests/test-native-llvm-macos-default-triple.py
  python3 scripts/tests/test-bootstrap-compiler-policy.py
  bash scripts/tests/test-cp-seed-adapter.bash

Then validate macOS compiler/SDK selection, native C and C++ targets,
Mach-O architecture and ARM64e linker/runtime, the Clang resource-header
producer/consumer chain, and ThinLTO on the intended host. A successful
seed probe does not prove the downstream LLVM bootstrap.

Documentation ownership
-----------------------

Keep QEMU-specific repair notes, diagnostics, file paths, branch decisions
and executable test results in this repository. Keep only general
cross-repository programming principles in the WHP Notion standard.
