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

The submodule, host-tool, library, firmware, and conditional dependency edges
used by this orchestration are tracked in :ref:`whp-dependency-ledger`.
That ledger distinguishes a source that is merely available from one that is a
production build dependency, and records which pinned sources are WHP-owned
forks that may be edited directly.

Source refresh diagnostics
--------------------------

The early ``scripts/whp-build/update-source.sh`` stage runs before managed
Python, Bash, sed, or the native compiler, so its diagnostics use POSIX shell
and ``printf`` without introducing another tool dependency. Routine output
reports the *outcome*, not merely that Git was invoked:

* **Current** means the checked local HEAD equals its tracked upstream.
* **Fast-forwarded** means the branch HEAD actually advanced.
* **Local ahead** means a successful no-op fast-forward preserved a newer
  local HEAD without claiming it equals upstream.
* **Retained / refresh unverified** means an automatic refresh was not proven
  successful (for example, tracked edits, a detached checkout, unavailable
  upstream, or a failed fetch). The earlier warning explains why.
* **Error** means a required refresh (``WHP_SOURCE_UPDATE=1``) failed.

Normal messages remain short; to inspect the Git seed, branch, tracking ref,
advertised and local commit IDs, and before/after HEAD, opt in to diagnostic
messages on standard error::

  WHP_SOURCE_UPDATE_VERBOSE=1 ./build.sh

``WHP_SOURCE_UPDATE_VERBOSE`` accepts only ``0`` (default) or ``1``.
It controls **source-refresh details only**, not compiler command echoing,
Meson/Ninja verbosity, or QEMU runtime tracing. Invalid values fail early
without attempting a refresh. This switch does not authorize source resets,
force-pushes, submodule downloads, or network access during existing probe
and CI skip modes. A source refresh skipped under CI is not described as
verified current. The focused source-update fixture tests all four outcomes
and the diagnostic/validation boundary.

Explicit Git submodule remote refresh
-------------------------------------

Normal ``./build.sh`` runs reconcile initialized submodules only to QEMU's
recorded Gitlink revisions. Remote branch updates are **never automatic**.
A developer may explicitly advance one initialized, detached, clean
submodule whose ``.gitmodules`` entry declares a tracking branch::

  python3 scripts/whp-build/update-submodules.py --source . --remote toolchains/llvm-project

This guarded operation fetches only the selected branch and uses
``git submodule update --remote --no-fetch --checkout`` after verifying
ancestry, the unchanged parent index, worktree cleanliness, and the expected
remote tip. It refuses attached developer branches, divergence, unknown paths,
missing checkouts, and unprovable histories; newer descendant checkouts are
preserved. For a missing checkout, first initialize the exact recorded pin::

  git submodule update --init -- toolchains/llvm-project

Depth-one Git checkouts with a newer remote tip can contain the pinned
commit and current tip but not their intervening ancestry. The automatic
initialized-submodule updater now fetches bounded Git history (64, 256, and
1024 additional commits) before classifying such a checkout. It never moves
the checkout HEAD or parent gitlink merely to establish ancestry. When
history cannot be recovered, automatic mode preserves the checkout and strict
mode reports the blocker without resetting source files.

The legacy ``scripts/git-submodule.sh`` (used by firmware configuration)
now uses the same non-rewinding policy: ``update`` preserves proven descendants
and ``validate`` accepts them even when its status ledger has an older SHA.
It still rejects missing, divergent, or unprovable checkouts. Read-only
``status`` and ``validate`` do not create or rewrite the status
ledger; only a successful explicit ``update`` does so. This does not change
the Python bootstrap cache contract, which uses the actual checkout SHA.

The remote checkout does **not** update the parent repository's recorded
Gitlink. After validating the new source revision and build, explicitly
``git add toolchains/llvm-project``, commit and push QEMU ``master``, and
verify the remote tree's mode-``160000`` Gitlink. Meson-owned DTC wraps are not
Git submodules and do not belong in this operation.

Host identity boundary
----------------------

The public POSIX ``build.sh`` entry reads ``uname -s`` and ``uname -m``
once, before Python and native compiler/linker bootstraps. It normalizes the
kernel to ``WHP_HOST_OS`` and exports ``WHP_HOST_KERNEL`` and
``WHP_HOST_ARCH`` for downstream helpers. The Bash preparation stage
reuses those readings; the portable Python runner prefers them over
``platform.system()`` and ``platform.machine()`` while retaining normal
fallbacks for direct standalone invocation. An inherited host identity cannot
override the public entry's fresh readings. No build-directory tag or owner
schema is changed, and the macOS physical-vs-process architecture check still
uses its separate ``sysctl`` evidence.

Shell contract
--------------

``build.sh`` and ``scripts/macos-builder.sh`` are small POSIX ``sh`` launchers.
They locate GNU Bash 3.2 or newer, clear shell startup inputs such as
``BASH_ENV``, ``ENV``, ``POSIXLY_CORRECT``, ``SHELLOPTS``, and ``BASHOPTS``,
and then enter the Bash orchestration layer with ``--noprofile --norc``.

The terminal POSIX-to-Bash wrappers share ``whp_exec_bash`` from
``scripts/whp-build/shell-functions.sh``. Its ``exec`` handoff preserves
arguments and the child's exit status while removing inherited startup hooks
and shell-mode switches. The native LLVM bootstrap is deliberately different:
its POSIX parent must return from the Bash child to validate the installed
prefix and tools before reporting success.

``WHP_BUILD_BASH`` is the single public shell selector. The selected Bash path
is also used as ``CONFIG_SHELL`` for nested configure recursion. There is no
separate QEMU or PowerPC-toolchain shell selector. The POSIX
``seeds/bash.sh`` adapter validates an independent GNU Bash before the managed
fork is available. ``WHP_BASH_SEED`` explicitly chooses this root interpreter
and fails closed if unusable; ``WHP_BUILD_BASH`` still takes precedence.
When used, the root is recorded in ``WHP_BASH_BOOTSTRAP_SEED`` separately
from any later managed Bash promotion. The adapter guards recursion and
suppresses inherited Bash startup hooks during selection and forwarding.

``BOOTSTRAP_BASH=auto``
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

Windows PowerShell entry
------------------------

Windows users can enter the same build policy from Windows PowerShell 5.1 or
PowerShell 7 with ``build.ps1``.  The PowerShell launcher does not duplicate
QEMU configuration, firmware preparation, or build ordering.  It locates a
Windows-native MSYS2, Git-for-Windows, or Cygwin Bash, converts the checkout
path with ``cygpath``, pins that interpreter through ``WHP_BUILD_BASH``, and
then invokes ``build.sh`` with ``--noprofile --norc``::

  .\build.ps1 qemu-system-i386

MSYS2 is the preferred Windows environment because the native QEMU build still
needs its POSIX build tools and Windows compiler/dependency set.  Set
``WHP_WINDOWS_BASH`` to an explicit ``bash.exe`` when automatic discovery
should not choose among multiple installations.  WSL Bash is deliberately
rejected by this launcher: entering WSL would select a Linux host ABI rather
than build native Windows QEMU.

The PowerShell launcher also provides a narrow convenience switch for the
existing UEFI SeaBIOS graph::

  .\build.ps1 -SeaBIOSUefi qemu-system-i386

``-SeaBIOSUefi`` enables ``BUILD_SEABIOS_GRUB=1`` and
``BUILD_SEABIOS_HYBRID_ISO=1``.  Unless the caller already selected another
policy, it also sets ``GRUB_I386_BOOTSTRAP=1`` so the pinned WHP IA32 EFI
GRUB path is used instead of depending on an unrelated host GRUB.  This switch
does not install system packages and does not create a second firmware build
implementation.  The x86-64 EFI frontend continues to use the existing
``GRUB_X86_64_MKIMAGE``, ``GRUB_X86_64_MODULE_DIR``, and
``GRUB_X86_64_INSTALL_PREFIX`` discovery contract.

Use ``-NoSourceUpdate`` as the PowerShell spelling of a one-run
``WHP_SOURCE_UPDATE=0`` override.  All other WHP environment variables and
positional targets are passed through to ``build.sh``.

QEMU dependency downloads
-------------------------

``QEMU_DOWNLOAD_DEPENDENCIES`` defaults to ``y`` in both menuconfig
frontends. Both build runners explicitly pass ``--enable-download`` or
``--disable-download`` to QEMU configure. Configure also explicitly resets
Meson's wrap mode on incremental reconfiguration; an earlier offline build
cannot retain ``nodownload`` after downloads are enabled again.

Set the menu option to ``n`` (or ``QEMU_DOWNLOAD_DEPENDENCIES=0`` in the
launcher environment) to use locally available QEMU configure dependencies.
The pre-configure DTC network reconciliation is skipped in that mode;
configure retains its own offline DTC checks. Missing dependencies remain
errors instead of silently fetching. The independent DTC prefetch choice
still controls whether to prefetch rather than letting Meson fetch on demand.
This is not a global offline switch: parent source refresh, firmware and
managed toolchain bootstraps retain their separate policies. The managed
GLib helper follows configure's download permission for pinned wraps and
source initialization, while retaining its host-provider and loader checks.

``seeds/pip.sh`` selects pip through the chosen Python interpreter, not a
standalone executable on PATH. Use ``--python /path/to/python --check``
for a read-only probe, or ``--print-python`` to identify the interpreter.
Ordinary pip arguments are forwarded only when explicitly supplied. The
seed does not install pip or packages on its own. The managed Python
bootstrap still repairs its own pip using bundled ensurepip wheels, and
QEMU's virtual environment keeps its existing dependency resolver.
The explicit venv Meson provider now follows the same download flag as
the tooling group.

Host linker selection
---------------------

``QEMU_HOST_LINKER`` is a host-feature choice in ``./build.sh menuconfig``.
It accepts ``auto`` (preserve automatic selection), ``system`` (the compiler
driver's default linker), ``lld``, and ``mold``.  The choice does not depend
on ``HOST_OS``: the selected compiler, executable format, ABI, and runtime
probe determine compatibility.

Examples that preserve the existing build-tree ownership::

  QEMU_HOST_LINKER=system ./build.sh qemu-system-ppc
  QEMU_HOST_LINKER=lld ./build.sh qemu-system-ppc
  QEMU_HOST_LINKER=mold ./build.sh qemu-system-ppc

On macOS, an inherited ``LD=/opt/homebrew/bin/ld64.lld`` alone does
not select the linker used by Clang's C/C++ drivers. Use
``QEMU_HOST_LINKER=lld`` to request LLD with the host link probes.
The macOS flag audit still rejects conflicting ``-fuse-ld`` and
``--ld-path`` options. Managed native LLVM keeps its exact
``ld64.lld`` identity check; ASan and default arm64e safety gates
remain unchanged.

The Bash path probes C and C++ compiler-driver links and executes the host
results before selecting an alternative linker.  The mold path also retains
its archive/LTO probe. Explicit probe failures stop without silently changing
linkers. The portable Python path uses installed linkers with dual-language
link/run probes; it does not bootstrap the pinned mold submodule.

``BOOTSTRAP_MOLD`` remains a separate control for the WHP mold fork.
Both menuconfig frontends reject saving ``QEMU_HOST_LINKER=system`` or
``lld`` together with ``BOOTSTRAP_MOLD=y``. The Bash runner also rejects
``QEMU_HOST_LINKER=mold`` with ``BOOTSTRAP_MOLD=n`` (or environment value
``0``); selecting mold with ``auto`` or ``y`` requests the managed fork.
The portable runner can use an installed mold with ``auto`` or ``n`` but
cannot bootstrap it. These runner-specific checks remain at build time.
ARM64e authenticated-fixup and macOS AddressSanitizer runtime admissions
are not bypassed by trivial link tests.

The Bash build records effective LDFLAGS in its incremental configuration
identity. Switching linkers triggers ordinary QEMU reconfiguration without
resetting or relabeling the persistent build directory.

Build-tree transfers and ownership
----------------------------------

A WHP QEMU build directory is a persistent record, not a disposable scratch
directory. The owner marker records ``PROJECT_ID=retrochristian5000/QEMU``
alongside the current ``SOURCE_DIR`` and host ABI (``HOST_TAG``).
``SOURCE_DIR`` is not an immutable identity: a moved checkout on the same
host ABI can be adopted, including an older WHP owner marker or recognizable
pre-PGO ``.whp-config`` metadata, without deleting prior outputs or
``default.profdata`` and ``pgo-raw/``.

The public ``build.sh`` claims the build tree before dependency bootstraps
write to it; the Bash configuration stage uses the same ownership policy.
Conflicting project IDs, unknown build directories, and incompatible host ABI
records still stop safely. A successful ownership migration does not assert
that Meson's compiled artifacts are portable across different source paths,
SDKs, compilers, or hardware. Meson must reconfigure and may have to rebuild
affected objects; existing PGO profiles also require compatible compiler
instrumentation. The migration itself never deletes the directory.

Linux and macOS require separate build trees even on the same ARM64 CPU:
``build/whp-arm64-linux`` and ``build/whp-arm64-apple-darwin``. If an
inherited ``BUILD_DIR`` names a directory owned by the other OS, the build
stops with a suggested host-specific directory and preserves all previous
artifacts. ``HOST_TAG=arm64-`` is incomplete, not an alias for either host;
never infer the previous operating system from the current one or relabel
an unverified build to bypass the guard.

Source refresh
--------------

Normal local ``./build.sh`` runs resolve ``seeds/git.sh --print-seed``
before the parent checkout updater (and before Python, managed toolchain,
or QEMU configuration discovery). ``WHP_SOURCE_UPDATE=auto`` is the
default. The pre/post-refresh HEAD checks and every command in
``update-source.sh`` use this same validated Git executable. The updater
fast-forwards only the current QEMU branch from its configured upstream and
synchronizes submodule URL metadata. After host Git and Python preparation,
only already-initialized submodules are reconciled; unused firmware and
toolchains remain lazy.

The refresh performs targeted fetches and a fast-forward-only merge.  Bootstrap
guards then compare commit ancestry before touching any initialized submodule:
a clean detached ancestor may fast-forward to QEMU's gitlink, but a checkout
ahead of the gitlink is preserved.  Divergence, insufficient history, local
edits on a behind checkout, and an attached branch never authorize a checkout.
Lazy initialization still starts at the recorded pin.  Build-cache identities
use the actual checked-out revision, including when that revision is a verified
descendant of the parent pin.  QEMU's recorded gitlink is never silently
advanced; integrating a newer checkout requires a separately pushed gitlink
commit.

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

The ``Native LLVM bootstrap`` group is conditional. ``BOOTSTRAP_NATIVE_LLVM=n``
leaves the C++ language edition, PCH, macOS host ABI, LLDB/ASan diagnostics,
and LLVM-only job pools collapsed. Enabling the parent reveals them without
discarding previously saved values; disabling it hides them without clearing
those values. These controls apply to native LLVM preparation, not QEMU's own
``QEMU_HOST_LTO``, ``QEMU_HOST_OPTIMIZATION``, or guest-target settings.

The default ``auto`` job-pool values leave the existing bootstrap's
host-specific limits intact; explicit linker jobs must be positive, and
compile/TableGen pools accept ``0`` to request no explicit pool limit.
``NATIVE_LLVM_ENABLE_LLDB=auto`` preserves the bootstrap's macOS-on,
other-hosts-off policy. ASan validation and LLDB auto-debug replay are macOS
diagnostics; replay needs LLDB and ASan validation enabled. Selecting
``NATIVE_LLVM_MACOS_ARCH=arm64e`` is an explicit ABI request: the existing
bootstrap still requires C and C++ compile, link and execution capability
probes, and refuses unsupported hosts or SDKs. The menu never automatically
turns on expensive rebuilds, shared LLVM linking, or new target backends.

In the Python/curses interface, press ``/`` (or ``f``) to filter options by
setting key, label, section, or hardware group. An empty search restores the
full menu; an unmatched search keeps the previous selection and filter.
Use ``[`` and ``]`` to jump between sections, arrows or Page Up/Page Down to
navigate, ``Space`` or ``Enter`` to edit, ``?`` to inspect the selected
setting's allowed values, ``r`` for defaults, and ``s`` to save. The footer
identifies the exact configuration key and repository default; conflicting
sanitizer or LTO choices are reported as soon as they are edited, and invalid
combinations are still rejected at save time.

Without Python, the POSIX-shell fallback offers ``f`` to filter by the same
fields and ``a`` to return to all options. Displayed option numbers stay
stable under filtering, so a filtered selection edits the intended key.
Run ``./build.sh menuconfig --dump`` to inspect the complete menu without
editing the configuration file. Both interfaces retain unknown saved keys
rather than silently discarding older profile entries.

Each menu item carries its own repository default; optional diagnostics,
installation, and some build outputs are deliberately opt-in. The redundant
``BOOTSTRAP_SCCACHE`` menu checkbox has been retired: select
``COMPILER_CACHE=managed-sccache`` to build the pinned fork, or
``COMPILER_CACHE=sccache`` to use an installed cache. Existing
``BOOTSTRAP_SCCACHE=y`` profiles migrate on load without rewriting the
user-owned file until explicitly saved. The legacy environment variable
continues working.  The build-output
section includes ``qemu-img`` and the supported ``qemu-system-*`` selectors.
Disabling ``qemu-img`` passes ``--disable-tools`` to QEMU; enabling it passes
``--enable-tools``. The system-emulator selections derive QEMU's internal
target list, so the menu does not expose a conflicting raw target-list field.
Disabling every system emulator passes ``--disable-system`` for a tools-only
build.

Under ``System emulators``, ``BUILD_QEMU_SYSTEM_ALL`` offers an opt-in
shortcut to build all three WHP menu-supported system emulators: i386,
PowerPC, and SPARC. This does **not** mean every QEMU upstream target.
The switch defaults to ``n``, preserving existing per-target behavior.
When enabled, it collapses the three individual emulator toggles in both
the Python/curses menu and the POSIX-shell fallback and selects all three
in the Bash and portable build planners. The saved individual values are
**not** modified; turning the switch off expands the individual toggles
with their previous choices intact. An active ``QEMU_X86_FAMILY_LINK``
still substitutes x86_64 for the i386 backend using its existing guardrails.
Explicitly named build commands still retain their normal request handling.

As with other WHP target choices, an existing incremental build can retain
previously configured targets even after they are disabled in the menu.
To apply a smaller target set rather than preserving that union, use
``WHP_INCREMENTAL_BUILD=0`` or a separate ``BUILD_DIR``. Menu collapse
changes which settings are visible, not the contents of existing build outputs.

The ``QEMU hardware`` section is device-first. Each currently exposed audio
model appears once, with independent ``i386`` and ``ppc`` choices underneath:
Sound Blaster 16, AdLib, Gravis UltraSound, Crystal CS4231A, PC speaker,
Ensoniq ES1370, Intel AC'97, Crystal CS4630, and Intel HD Audio. Menu labels
spell out ``ISA bus`` and ``PCI bus`` where relevant. PowerPC is the guest CPU
instruction-set architecture; QEMU's ``ISA_BUS`` symbol names the unrelated
legacy peripheral bus. Each target choice is three-state: ``auto``, ``y``, or
``n``. ``auto`` leaves QEMU's Kconfig decision and dependency handling
unchanged for that architecture.

An explicit PowerPC ``y`` also writes the model's minimum Kconfig prerequisite
closure into the PPC preset. ISA-bus audio models require
``CONFIG_ISA_BUS=y``; PC speaker additionally requires ``CONFIG_I8254=y``;
and PCI audio models require ``CONFIG_PCI=y``. These are compile-time device
capabilities, not PowerPC machine selections: the resulting device can be used
with a PPC machine that exposes the matching bus, while machines without that
bus are not changed. ``CONFIG_PCI_DEVICES`` is deliberately left alone because
it controls a broader set of default PCI devices rather than the PCI core
required by the selected audio model.

Explicit ``n`` values write only the requested device disable. Explicit ``y``
values write the requested device plus the prerequisite closure described
above in the matching architecture preset, such as
``configs/devices/i386-softmmu/whp-user.mak`` or
``configs/devices/ppc-softmmu/whp-user.mak``. QEMU then receives the supported
``--with-devices-i386=whp-user`` or ``--with-devices-ppc=whp-user`` configure
hook for the affected target. When ``QEMU_X86_FAMILY_LINK=1``, x86-family
audio selections instead use
``configs/devices/x86_64-softmmu/whp-user.mak`` and
``--with-devices-x86_64=whp-user``. This preset inherits the same
i386 device defaults used by x86_64's tracked include, avoiding a duplicate
i386-only Game Blaster implementation. An x86-family choice never changes
the PowerPC preset, and a PowerPC choice never changes the x86 preset.

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


SeaBIOS guest RAM footprint
---------------------------

The pinned WHP SeaBIOS fork provides an **opt-in** POST report for
distinguishing firmware allocation pressure from QEMU's own host-memory
usage. Once the matching SeaBIOS firmware image is built, compare
identical machine types and devices with different RAM sizes::

  qemu-system-i386 -machine pc -m 64M -bios /path/to/bios-256k.bin \
    -fw_cfg name=opt/org.seabios/whp-memory-report,string=1 \
    -chardev file,id=seabios,path=seabios-memory.log \
    -device isa-debugcon,iobase=0x402,chardev=seabios

The new ``WHP SeaBIOS memory:`` lines report the conventional-memory
limit and EBDA size in KiB; **tracked, permanent dynamic allocations**
in the low, F-segment, and high zones in bytes; and high-zone whole
pages returned to the guest before boot in bytes. Existing level-1
SeaBIOS E820 messages provide the complementary final memory map.
The ``opt/org.seabios/whp-memory-report`` fw_cfg file enables
reporting by its presence; regular boots do not emit the extra summary.
The instrumentation does not allocate a new guest buffer.

These totals are **not** the emulator process RSS or every E820
reservation. The 0xA0000-0xFFFFF PC ROM/adapter address window is not
ordinary guest RAM, and the firmware's initial high-zone reserve of up
to 16 MiB is largely returned to E820 in whole pages when unused.
Temporary POST allocations likewise must not be counted as retained
guest memory. Compare the final E820 map, machine type, option ROMs,
EBDA and attached devices before lowering any firmware allocation limit.
For the native firmware source and logging details, consult
``roms/seabios/docs/Debugging.md``.


Active SeaBIOS POST self-tests
------------------------------

SeaBIOS does perform its real POST initialization (PIC, DMA, timers,
device enumeration, VGA and option ROMs). Discovery of emulated RAM,
however, is **not** a complete RAM read/write test. To request an
additional active check on the pinned WHP firmware::

  qemu-system-i386 -machine pc -m 64M -bios /path/to/bios-256k.bin \
    -fw_cfg name=opt/org.seabios/whp-extended-post,string=1 \
    -chardev file,id=seabios,path=seabios-post.log \
    -device isa-debugcon,iobase=0x402,chardev=seabios

When requested, the extended POST runs **after device/option-ROM setup
and before BIOS INT 19h**. It checks E820 range ordering, overlap and
overflow, the conventional-memory BDA/EBDA boundary and EBDA reserved
range, and tests 4 KiB of owned temporary RAM using address-dependent,
inverted and walking-bit patterns. It frees the buffer before boot. A
reported failure **halts** the BIOS instead of continuing with a
misleading PASS banner; the successful result is printed as
``WHP extended POST: ... PASS``. This test is disabled by default,
requires no persistent extra RAM, and is specific to QEMU SeaBIOS.

It does **not** claim to test all emulated RAM, exercise every PCI/USB
peripheral, or diagnose physical memory errors on the host. The
existing ``whp-memory-report`` option measures footprint, whereas
``whp-extended-post`` performs actual bounded reads and writes.
The two switches are independent. See the pinned firmware's
``docs/Debugging.md`` for firmware-side details.
