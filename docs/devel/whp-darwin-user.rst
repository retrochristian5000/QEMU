.. _whp-darwin-user:

WHP Darwin/macOS user-mode recovery
===================================

Goal and terminology
--------------------

The WHP goal is to restore Darwin/macOS as a QEMU user-mode **guest ABI** so a
Darwin host can run Darwin binaries built for another CPU architecture through
TCG. The first practical lane is ``x86_64-darwin-user`` on an AArch64
Apple-Silicon host. A later ``aarch64-darwin-user`` lane provides the
inverse/cross-validation path.

This is not the same thing as adding another system-emulation machine. The
guest process keeps the Darwin userspace ABI while QEMU translates CPU
instructions, system calls, signals, memory operations, and process startup.

Apple ``arm64e`` is an AArch64 ABI variant with pointer-authentication
requirements. It is not a separate QEMU CPU architecture and must not be
confused with Windows ``arm64ec``. Initial AArch64 Darwin-user work targets
the ordinary arm64 ABI; arm64e is enabled only after its ABI-specific pointer
and dyld behavior has dedicated tests.

Historical recovery evidence
----------------------------

QEMU already contained ``darwin-user/``. It was removed by commit
``0adb124659cfadf9f0b5c99874c476116f0cf74f`` on 30 April 2012 because the
code was orphaned, had not compiled for a long time, and could not be tested
during the QOM conversion. The immediately preceding tree is
``148210301e334694badcc8ae72ecb522c6d7bac6``.

That tree is evidence, not drop-in production code. The removed implementation
contained:

* ``darwin-user/machload.c`` -- Mach-O loader and dyld handoff;
* ``darwin-user/syscall.c`` -- BSD/Darwin and Mach call translation;
* ``darwin-user/commpage.c`` -- commpage helpers;
* ``darwin-user/mmap.c`` -- guest memory mapping;
* ``darwin-user/signal.c`` -- signal delivery;
* ``darwin-user/main.c`` -- user-mode CPU loop and process startup; and
* i386/PPC ``*-darwin-user`` target configurations.

The last historical loader was 32-bit i386/PPC oriented. It has no
``MH_MAGIC_64``/64-bit Mach-O path, no x86_64 or AArch64 target state, and
predates modern dyld load commands. Its signal file also left target/host
``siginfo`` conversion empty. Restoring the directory verbatim would
therefore resurrect known incompleteness.

ABI formats
-----------

Darwin-user must explicitly track these formats instead of inheriting host
definitions accidentally:

* Mach-O executable and dylinker images, including 64-bit headers and load
  commands;
* fat/universal containers used to select the requested guest architecture;
* Darwin BSD syscall ABI;
* Mach trap and Mach IPC ABI;
* signal, ucontext, pthread, and thread-state layouts;
* dyld process bootstrap and shared-cache-facing interfaces;
* commpage layout and helpers; and
* AArch64 ABI variants, with arm64e kept separate from ordinary arm64.

Target ABI definitions must live in QEMU-owned target headers or generated
tables with provenance. Building on macOS must not silently make the host SDK
header layout equal to the guest layout.

Build architecture
------------------

Do not fold Darwin into ``bsd-user``. The current ``bsd-user`` build is
host/FreeBSD-shaped: it selects ``bsd-user/<host_os>`` and currently requires
host ``libelf``, ``libprocstat``, and ``libkvm``. Darwin needs a
separate target family so FreeBSD host assumptions cannot leak into Mach-O and
Mach ABI code.

The intended modern structure is::

  common user TCG / guest memory / plugins / gdb
                 |
       +---------+----------+
       |                    |
    linux-user            bsd-user
                            |
                         FreeBSD
       |
       +---------------- darwin-user
                            |
              +-------------+-------------+
              |                           |
        Mach-O/process loader       Darwin ABI translators
                                          |
                         +----------------+----------------+
                         |                                 |
                     BSD syscalls                    Mach traps / IPC

Do not add ``*-darwin-user.mak`` targets merely to make configure list them.
A target becomes build-visible only when its loader, syscall dispatch, signal
ABI, memory layer, and architecture entry state have smoke tests.

Recovery sequence
-----------------

**Stage 1 -- isolate target ABI data**

Create Darwin-owned constants and structures independent of host SDK layout.
Use public Darwin/XNU definitions as provenance, but copy only the target ABI
facts QEMU needs. Add compile-time size/offset tests for x86_64 and AArch64.

**Stage 2 -- modern Mach-O probe/loader**

Start with a parser that can identify architecture, bitness, segments, entry
metadata, dylinker requirements, and malformed load-command bounds without
executing anything. Then map 64-bit segments through current QEMU user-memory
helpers. Historical ``machload.c`` is a behavioral reference only.

The loader must understand the modern 64-bit command families needed by test
fixtures before a public target is enabled, including the executable entry and
dyld metadata used by current toolchains.

**Stage 3 -- process startup without broad syscall coverage**

Construct the Darwin initial stack/process metadata and enter a controlled
Mach-O fixture. The first fixture should be generated by the pinned WHP LLVM
toolchain and must avoid claiming general macOS binary compatibility.

**Stage 4 -- syscall-class split**

Keep Darwin BSD syscalls and Mach traps/IPC in separate dispatch tables.
Translation must be by target ABI number and target structure layout, not by
assuming host syscall numbers are identical. A macOS host may provide a useful
implementation backend, but passthrough is never the ABI definition.

**Stage 5 -- signals, threads, and commpage**

Port behavior rather than source text from the historical files. Modern tests
must cover signal frame construction, pthread/thread state, atomic helpers,
time helpers, and guest/host page-size mismatches.

**Stage 6 -- dyld and shared-cache path**

Add ``-L`` sysroot semantics for Darwin and validate the requested
``/usr/lib/dyld`` from that root. Dynamic binaries become a supported
milestone only after dyld-facing Mach VM/IPC behavior and shared-cache
requirements are understood and tested.

**Stage 7 -- ABI expansion**

After x86_64 Darwin binaries work on Apple Silicon, add ordinary AArch64
Darwin-user coverage. arm64e comes after ordinary arm64 and requires its own
pointer-authentication/dyld fixtures. No arm64e behavior may be inferred from
the spelling of arm64ec or from host ``-arch arm64e`` alone.

Circularity and isolation guards
--------------------------------

#. Darwin-user may consume Mach-O fixtures produced by WHP LLVM, but LLVM must
   never require Darwin-user to bootstrap.
#. Host macOS headers are evidence about the current host SDK, not a substitute
   for versioned target ABI definitions.
#. Wine/Windows PE work and Darwin/Mach-O work may share LLVM infrastructure,
   but PE/COFF, ARM64EC, Mach-O, and arm64e state must not bleed together.
#. Historical QEMU Darwin-user code must be recovered by file/commit provenance;
   do not paste an unlabelled copy into the modern tree.
#. The first enabled target must have loader and syscall smoke tests. A config
   file without an executable ABI path is not support.
#. Guest code signatures and hardened-runtime metadata must be parsed or
   deliberately ignored according to guest semantics; host code-signing policy
   must not be mistaken for guest validation.

Initial test matrix
-------------------

The minimum pre-enable matrix is:

.. list-table::
   :header-rows: 1

   * - Host
     - Guest
     - Milestone
   * - macOS AArch64
     - Darwin x86_64
     - Mach-O parse, segment map, entry-state fixture
   * - macOS AArch64
     - Darwin x86_64
     - direct Darwin/Mach syscall smoke fixture
   * - macOS AArch64
     - Darwin x86_64
     - dyld-backed command-line fixture
   * - macOS x86_64 or controlled cross host
     - Darwin AArch64
     - parser/ABI fixtures before execution
   * - macOS AArch64
     - Darwin arm64e ABI
     - pointer-authentication/dyld fixtures after ordinary arm64

The order is intentional: loader correctness and ABI boundaries come before
large application compatibility.
