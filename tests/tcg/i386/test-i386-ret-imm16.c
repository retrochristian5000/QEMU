/*
 * Check unsigned 16-bit RET/RETF cleanup on a 32-bit stack.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The initial stack is saved before using a private stack with room
 * on both sides of the initial pointer. No libc or newer ISA required.
 */
__asm__(
    ".text\n"
    ".globl _start\n"
    "_start:\n"
    "movl %esp, %edx\n"
    "leal scratch+65536, %esp\n"
    ".macro check_ret insn, count, far=0\n"
    "movl %esp, %ecx\n"
    ".if \\far\n"
    "pushl %cs\n"
    ".endif\n"
    "call 1f\n"
    "movl %esp, %eax\n"
    "subl %ecx, %eax\n"
    "movl %ecx, %esp\n"
    "cmpl $\\count, %eax\n"
    "jne 3f\n"
    "jmp 4f\n"
    "1: \\insn $\\count\n"
    "4:\n"
    ".endm\n"
    "check_ret ret, 0\n"
    "check_ret ret, 0x7fff\n"
    "check_ret ret, 0x8000\n"
    "check_ret ret, 0xffff\n"
    "check_ret lret, 0, 1\n"
    "check_ret lret, 0x7fff, 1\n"
    "check_ret lret, 0x8000, 1\n"
    "check_ret lret, 0xffff, 1\n"
    "xorl %ebx, %ebx\n"
    "jmp 5f\n"
    "3: movl $1, %ebx\n"
    "5: movl %edx, %esp\n"
    "movl $1, %eax\n"
    "int $0x80\n"
    ".bss\n"
    ".balign 16\n"
    "scratch: .skip 131072\n"
);
