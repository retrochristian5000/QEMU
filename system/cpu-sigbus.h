/* SPDX-License-Identifier: MIT */
#ifndef SYSTEM_CPU_SIGBUS_H
#define SYSTEM_CPU_SIGBUS_H

/* Initialize host machine-check signal handling before CPU threads start. */
void qemu_init_sigbus(void);

#endif
