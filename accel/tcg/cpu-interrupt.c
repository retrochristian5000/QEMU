/*
 * TCG system interrupt dispatch.
 *
 * Copyright (c) 2003-2005 Fabrice Bellard
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include "qemu/osdep.h"
#include "hw/core/cpu.h"
#include "accel/tcg/cpu-ops.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"
#include "exec/replay-core.h"
#include "qemu/atomic.h"
#include "qemu/main-loop.h"
#include "internal-common.h"

/*
 * Slow path entered after the execution loop clears its TB exit flag and
 * observes a pending interrupt. Recheck the live request under the BQL:
 * target hooks can change pending bits, especially EXITTB. Keep the
 * post-hook EXITTB test separate from the interrupt snapshot.
 */
bool tcg_process_interrupt(CPUState *cpu, TranslationBlock **last_tb)
{
    bql_lock();
    if (cpu_test_interrupt(cpu, CPU_INTERRUPT_DEBUG)) {
        cpu_reset_interrupt(cpu, CPU_INTERRUPT_DEBUG);
        cpu->exception_index = EXCP_DEBUG;
        bql_unlock();
        return true;
    }
    if (replay_mode == REPLAY_MODE_PLAY && !replay_has_interrupt()) {
        /* Do nothing */
    } else if (cpu_test_interrupt(cpu, CPU_INTERRUPT_HALT)) {
        replay_interrupt();
        cpu_reset_interrupt(cpu, CPU_INTERRUPT_HALT);
        cpu->halted = 1;
        cpu->exception_index = EXCP_HLT;
        bql_unlock();
        return true;
    } else {
        const TCGCPUOps *tcg_ops = cpu->cc->tcg_ops;
        int interrupt_request = qatomic_load_acquire(&cpu->interrupt_request);

        if (cpu_test_interrupt(cpu, CPU_INTERRUPT_RESET)) {
            replay_interrupt();
            tcg_ops->cpu_exec_reset(cpu);
            bql_unlock();
            return true;
        }

        if (unlikely(cpu->singlestep_flags & SSTEP_NOIRQ)) {
            /* Mask out external interrupts for this step. */
            interrupt_request &= ~CPU_INTERRUPT_SSTEP_MASK;
        }

        /*
         * The target hook has 3 exit conditions:
         * False when the interrupt isn't processed,
         * True when it is, and we should restart on a new TB,
         * and via longjmp via cpu_loop_exit.
         */
        if (tcg_ops->cpu_exec_interrupt(cpu, interrupt_request)) {
            if (!tcg_ops->need_replay_interrupt ||
                tcg_ops->need_replay_interrupt(interrupt_request)) {
                replay_interrupt();
            }
            /*
             * After processing the interrupt, ensure an EXCP_DEBUG is
             * raised when single-stepping so that GDB doesn't miss the
             * next instruction.
             */
            if (unlikely(cpu_single_stepping(cpu))) {
                cpu->exception_index = EXCP_DEBUG;
                bql_unlock();
                return true;
            }
            cpu->exception_index = -1;
            *last_tb = NULL;
        }
    }
    if (cpu_test_interrupt(cpu, CPU_INTERRUPT_EXITTB)) {
        cpu_reset_interrupt(cpu, CPU_INTERRUPT_EXITTB);
        /* ensure that no TB jump will be modified as
           the program flow was changed */
        *last_tb = NULL;
    }

    /* If we exit via cpu_loop_exit/longjmp it is reset in cpu_exec */
    bql_unlock();
    return false;
}
