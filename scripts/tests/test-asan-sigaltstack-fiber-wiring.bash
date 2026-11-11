#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
sigaltstack="$ROOT/util/coroutine-sigaltstack.c"

# Darwin uses the sigaltstack coroutine backend.  ASan must be told whenever
# QEMU moves execution between the leader stack and coroutine stacks; otherwise
# __asan_handle_no_return can mistake the coroutine stack for the thread stack.
grep -Fq '#ifdef QEMU_SANITIZE_ADDRESS' "$sigaltstack"
grep -Fq '#ifdef CONFIG_ASAN_IFACE_FIBER' "$sigaltstack"
grep -Fq '#include <sanitizer/asan_interface.h>' "$sigaltstack"
grep -Fq '__sanitizer_start_switch_fiber' "$sigaltstack"
grep -Fq '__sanitizer_finish_switch_fiber' "$sigaltstack"

# Initial stack bootstrap, normal coroutine switches, and pooled coroutine
# teardown all need explicit ASan transitions.
grep -Fq 'start_switch_fiber_asan(&fake_stack_save,' "$sigaltstack"
grep -Fq 'finish_switch_fiber(fake_stack_save);' "$sigaltstack"
grep -Fq 'start_switch_fiber_asan(NULL, to->stack, to->stack_size);' "$sigaltstack"

grep -Fq 'CONFIG_ASAN' "$sigaltstack"
grep -Fq 'CONFIG_COROUTINE_POOL' "$sigaltstack"

printf 'ASan sigaltstack coroutine fiber wiring: verified\n'
