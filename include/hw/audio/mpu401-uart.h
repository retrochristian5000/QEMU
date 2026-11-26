/*
 * Reusable ISA MPU-401 UART-compatible interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_MPU401_UART_H
#define HW_AUDIO_MPU401_UART_H

#define TYPE_MPU401_UART "mpu401-uart-compat"

/* irq=UINT32_MAX routes the named irq output through a containing board. */
#define MPU401_UART_SHARED_IRQ UINT32_MAX

#endif
