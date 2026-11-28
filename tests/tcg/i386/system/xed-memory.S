/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Controlled flat protected-mode guest for the XED capture plugin. */
    .text
    .code32
    .globl main
main:
    pushl %ebp
    pushl %ebx
    pushl %esi
    pushl %edi
    movl $0x11223344, 0x5000
    movl $0x55667788, 0x5004
    movl $0x99aabbcc, 0x5008
    movl $0x5004, %eax
    movl $1, %ecx
    movl $0xfff0, %ebx
    movl $0x5010, %esi

    .globl xed_capture_start
xed_capture_start:
    movl (%eax,%ecx,4), %edx
    movw -2(%eax), %di
    addr16 movl (%bx,%si), %ebp
    movl %ebp, 4(%eax)
    .globl xed_capture_end
xed_capture_end:
    cmpl $0x99aabbcc, %edx
    jne 1f
    cmpw $0x1122, %di
    jne 1f
    cmpl $0x11223344, %ebp
    jne 1f
    cmpl $0x11223344, 0x5008
    jne 1f
    xorl %eax, %eax
    jmp 2f
1:  movl $1, %eax
2:  popl %edi
    popl %esi
    popl %ebx
    popl %ebp
    ret
    .section .note.GNU-stack,"",@progbits
