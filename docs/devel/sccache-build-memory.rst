Sccache memory and cache policy
===============================

QEMU, the shared native LLVM bootstrap and the bundled Ninja bootstrap can
use ``COMPILER_CACHE=sccache`` without installing cache data in the target
toolchain. The defaults are intentionally conservative: sccache cannot limit
the memory consumed by an arbitrary compiler or linker process.

Build-time settings
-------------------

* ``SCCACHE_IDLE_TIMEOUT=180`` (seconds) is the WHP default whenever the
  sccache launcher is selected and no explicit ``SCCACHE_CONF`` is set.
  This makes the local server exit sooner after builds become idle. Explicit
  ``SCCACHE_IDLE_TIMEOUT=0`` disables idle shutdown. User values take
  precedence. This option does **not** cap peak server or compiler RSS.

* ``SCCACHE_DIR`` stores disk artifacts. Ninja now honors the user-provided
  directory and otherwise uses the same ``sccache-<OS>-<arch>`` path as
  the QEMU and native LLVM wrappers. This avoids accidental cache-path
  differences due only to capitalization of the host OS tag.

* ``SCCACHE_CACHE_SIZE=4G`` is an **optional example** disk limit. sccache
  itself defaults to 10G when not configured. Smaller sizes save storage but
  may evict expensive LLVM objects and increase rebuild time. They do not
  limit resident memory.

* ``SCCACHE_CLIENT_SIDE=1`` is optional and requires a compatible sccache
  release (introduced in 0.17.0). It moves preprocessing and compilation
  into the client process rather than the server. This may reduce server
  residency, but concurrent client processes still consume RAM, and this
  mode does not cap total system RSS. Confirm cache hits before enabling.
  It may be ignored when distributed compilation or an error log is active.

* Existing ``SCCACHE_CONF``, ``SCCACHE_CACHE_SIZE``,
  ``SCCACHE_CLIENT_SIDE``, and remote-cache settings remain authoritative.
  No shared sccache server is automatically stopped or restarted, because
  other processes may be using it. Some server settings take effect only
  when the server next starts.

Compiler and linker memory
--------------------------

Parallel processes typically dominate peak memory during LLVM builds, not
the on-disk cache. The QEMU build accepts ``JOBS``; native LLVM additionally
limits simultaneous links with ``NATIVE_LLVM_LINK_JOBS``. On macOS,
``MACOS_BUILD_POWER=eco|balanced|performance`` selects a default job budget
unless ``JOBS`` is explicit. Avoid pretending that
``SCCACHE_CACHE_SIZE`` limits RSS.

For a more memory-conservative build, for example::

    COMPILER_CACHE=sccache JOBS=2 NATIVE_LLVM_LINK_JOBS=1 \
      SCCACHE_IDLE_TIMEOUT=120 SCCACHE_CACHE_SIZE=4G ./build.sh

These settings affect the build machine, not the guest CPU ABI or installed
QEMU artifacts. For a diagnostic baseline, compare builds with
``COMPILER_CACHE=none`` and record peak resident memory as well as wall time.

Diagnostics and cleanup
-----------------------

Inspect cache behavior with ``sccache --show-stats``; check cache hits
and misses before assuming a tuning improves performance. Inspect the
build processes with the host's process monitor (Activity Monitor on macOS,
or ``ps``/``top`` on Linux). Use ``sccache --stop-server`` **only after**
all build clients are finished; it is a manual administrative action,
not part of the QEMU build.

Sccache references:

* https://github.com/mozilla/sccache/blob/main/docs/Configuration.md
* https://github.com/mozilla/sccache/blob/main/docs/Local.md
* https://github.com/mozilla/sccache/blob/main/docs/Architecture.md

WHP test coverage: ``python3 scripts/tests/test-compiler-cache-policy.py``.
