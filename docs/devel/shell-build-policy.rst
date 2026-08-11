Build shell policy
==================

The WHP build path uses two different shell contracts.  They must not be
collapsed into a single assumption about the user's login shell.

Public launchers
----------------

``build.sh`` and ``scripts/macos-builder.sh`` are small POSIX ``sh``
launchers.  They intentionally use only syntax accepted by traditional
Bourne-style shells so they may be entered from Bash, dash, zsh, or through
their declared ``/bin/sh`` interpreter.

The launchers locate GNU Bash 3.2 or newer, clear shell-startup variables, and
then replace themselves with a non-interactive Bash process.  On macOS the
default is ``/bin/bash``; set ``WHP_BUILD_BASH`` to an absolute executable
path to choose another Bash deliberately.

The clean handoff removes these inherited variables before Bash starts:

* ``BASH_ENV`` and ``ENV``, which can inject startup commands into
  non-interactive shells;
* ``POSIXLY_CORRECT``, which can alter Bash and utility behavior;
* ``SHELLOPTS`` and ``BASHOPTS``, which can import shell options from the
  parent environment.

The selected Bash runs with ``--noprofile --norc``.  User aliases, functions,
startup files, and login-shell choices are therefore not build inputs.

Bash orchestration layer
------------------------

``builder.sh`` is the ordered run of the build stages.
``scripts/whp-build/stages.bash`` loads the focused preparation,
source-input, configuration, and build-target modules in execution order.
``scripts/macos-builder.bash`` prepares macOS-specific policy before the run.
These scripts use features such as arrays, ``[[ ... ]]``, ``pipefail``,
indirect parameter expansion, here strings, and ``printf -v``.  They are not
dash scripts and must not be invoked directly with ``sh``, ``dash``, or
``zsh``.

Use one of the public launchers instead::

  sh build.sh

  sh scripts/macos-builder.sh

The launchers immediately normalize the process to ``WHP_BUILD_BASH``.
Calling ``sh builder.sh`` is not supported because an explicit interpreter
overrides the script's shebang.  A local checkout may mark ``build.sh``
executable and then use ``./build.sh`` as an equivalent convenience.

Configure shell boundary
------------------------

QEMU's top-level ``configure`` script declares ``#!/bin/sh`` and is maintained
as a POSIX-style shell script.  The WHP wrapper does not rewrite it as Bash and
does not run it under zsh.

GCC and binutils use a different rule.  Their nested configure recursion uses
``CONFIG_SHELL``, which the launchers set to the selected GNU Bash.  GCC's
build documentation recommends a working POSIX shell or Bash and explicitly
warns that zsh is not suitable for GCC configuration.  Bash is selected here
to avoid shell-specific correctness and performance failures in nested
configure scripts.

Shell comparison
----------------

``bash``
  Required for the WHP orchestration scripts.  Bash invoked by its normal name
  runs in Bash mode; invoking Bash as ``sh`` enables POSIX behavior and is not
  equivalent for a Bash program.

``dash``
  Appropriate for testing genuinely POSIX ``sh`` launchers and upstream shell
  scripts.  It does not implement the Bash arrays and conditional syntax used
  by ``builder.sh``.

``zsh``
  Suitable as an interactive login shell, but its default script mode is not
  POSIX-compatible and is not Bash-compatible.  It may start the small POSIX
  launcher, but it must not interpret the Bash implementation or GCC's
  configure recursion.

Verification
------------

The POSIX launchers should pass syntax checks with both ``dash -n`` and
``bash --posix -n``.  The implementation scripts should pass ``bash -n``.
A lightweight launcher check is available without starting a build::

  WHP_SHELL_PROBE_ONLY=1 sh build.sh

It prints the selected Bash version and ``CONFIG_SHELL`` and fails if Bash
POSIX mode is active.
