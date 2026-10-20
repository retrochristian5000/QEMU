Sccache memory and cache policy
===============================

QEMU, the shared native LLVM bootstrap and the bundled Ninja bootstrap can
use ``COMPILER_CACHE=sccache`` without installing cache data in the target
toolchain. The defaults are intentionally conservative: sccache cannot limit
the memory consumed by an arbitrary compiler or linker process.

Managed WHP sccacher fork
-------------------------

Set ``BOOTSTRAP_SCCACHE=y`` in ``.whpconfig`` (or export
``BOOTSTRAP_SCCACHE=1``) to build the pinned
``retrochristian5000/sccacher`` source under ``toolchains/sccacher``.
This is explicitly opt-in: ordinary builds retain existing system
ccache/sccache discovery and do not require Rust. The fork must be pinned by
the QEMU gitlink; the bootstrap refuses a dirty or mismatched checkout.
The output is installed under the build directory, not QEMU's install prefix.

The fork needs Rust 1.91 or newer and Cargo. The managed build uses
``cargo build --locked --release --no-default-features --bin sccache``,
keeping local compilation caching without building the optional distributed
and cloud backends. Its Cargo release profile overrides full LTO
(``false``), uses 8 codegen units, and disables debug info, avoiding
single-codegen-unit LTO memory pressure. The persistent Cargo target tree
is reused on rebuilds; a matching pinned source/compiler/profile identity
reuses the already installed executable.

``WHP_SCCACHE_BUILD_JOBS`` defaults to 2 and independently limits Cargo
concurrency. The Rust bootstrap clears inherited compiler wrappers to avoid
building sccache recursively through sccache. On success, it exports
``WHP_COMPILER_CACHE_CMD`` and ``COMPILER_CACHE=sccache`` before bundled Ninja, LLVM, and QEMU builds. Explicit conflicting cache settings are rejected. Cargo
dependencies may require an initial network fetch unless already cached.

A new executable does not automatically stop an old running sccache server:
restart only when other builds have finished. Check hit rates and measure
actual compiler/linker peak memory; the fork does not itself cap Clang RSS.

LLVM precompiled headers with sccache
-------------------------------------

With ``NATIVE_LLVM_PCH=auto``, native macOS builds using Apple Clang or LLVM
Clang 18+ now enable LLVM's LLVMSupport PCH even when the managed sccacher is
selected. ``NATIVE_LLVM_PCH=1`` explicitly requests PCH, and ``0`` retains
the previous opt-out. Because sccache PCH reuse is not established as safe,
the bootstrap clears the **LLVM C++** CMake compiler launcher while PCH is on.
It keeps sccache enabled for LLVM C objects and for the later QEMU build;
with PCH off, LLVM C++ objects are cacheable again. This conservative split
does not attempt to classify individual PCH compiler arguments.

For example::

    BOOTSTRAP_NATIVE_LLVM=1 BOOTSTRAP_SCCACHE=1 NATIVE_LLVM_PCH=1 ./build.sh

PCH creation can increase peak memory, so compare native LLVM clean and
incremental builds before claiming a speedup or RSS reduction. The LLVM
CMake config identity includes both launcher options and the PCH setting:
changing modes reconfigures the existing Ninja tree without requiring a
fresh checkout or re-bootstrap of sccacher.

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
limits simultaneous links with ``NATIVE_LLVM_LINK_JOBS`` (default 2).
On macOS the native LLVM bootstrap also caps concurrent compile jobs at 2
(``NATIVE_LLVM_COMPILE_JOBS``) and TableGen jobs at 1
(``NATIVE_LLVM_TABLEGEN_JOBS``), using separate Ninja pools. Explicit positive
integers override each limit; setting either pool variable to ``0`` disables
its limit. Other hosts keep uncapped compile and TableGen pools by default.
These scheduling controls do not change the compiler ABI or invalidate the
installed toolchain. ``MACOS_BUILD_POWER=eco|balanced|performance`` selects
the outer macOS job budget unless ``JOBS`` is explicit. Pool limits are not a
whole-build RSS cap: compile, link, and TableGen jobs may run concurrently.

``SCCACHE_CACHE_SIZE`` limits disk cache space, not resident memory.

For a more memory-conservative build, for example::

    COMPILER_CACHE=sccache JOBS=2 NATIVE_LLVM_COMPILE_JOBS=1 \
      NATIVE_LLVM_LINK_JOBS=1 NATIVE_LLVM_TABLEGEN_JOBS=1 \
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
