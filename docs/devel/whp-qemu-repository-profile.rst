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

Host compiler and copy seed contracts
-------------------------------------

QEMU separates native build-machine compilers ``CC_FOR_BUILD`` and
``CXX_FOR_BUILD`` from target C/C++ tools and flags. Its ``seeds/cc.sh``,
``seeds/cxx.sh``, ``seeds/cpp.sh`` and ``seeds/ld.sh`` choose and validate
build-machine tools. Seed wrappers must reject invalid explicit selections,
avoid recursion and preserve the actual compiler, SDK and linker boundary.

``seeds/git.sh``, ``seeds/awk.sh``, ``seeds/grep.sh``, ``seeds/sed.sh``,
and ``seeds/cp.sh`` provide other selected host tools. The public
``build.sh`` selects a copy implementation before source refresh and uses
``scripts/whp-build/seed-bin/cp`` for literal ``cp`` calls. Its copy probes
cover ordinary files, POSIX ``-R`` and ``-p``; they do not establish
support for every GNU, BSD or Apple-specific copying extension.

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
