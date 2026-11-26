/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Disposable guest test; success is isa-debug-exit value 0x10. */
.code16
.text
.global _start
_start:
    cli
    xorw %ax, %ax
    movw %ax, %ss
    movw $0x7c00, %sp
    movw %ax, %ds
    movw %ax, %es
    sti
    cld
    movw $0x0080, %dx
    movw $0x0800, %ax
    int $0x13
    jc fail_geometry
    cmpb $15, %dh
    jne fail_geometry
    cmpb $1, %dl
    jne fail_geometry
    andb $63, %cl
    cmpb $63, %cl
    jne fail_geometry

    movw $0x0202, %ax
    movw $0x0002, %cx
    movw $0x0080, %dx
    movw $0x0600, %bx
    int $0x13
    jc fail_read
    cmpw $2, %ax
    jne fail_read
    movw $0x0600, %di
    movw $256, %cx
    movw $0x5a5a, %ax
    repe scasw
    jne fail_data
    movw $256, %cx
    movw $0xa5a5, %ax
    repe scasw
    jne fail_data

    movw $0x0301, %ax
    movw $2, %cx
    movw $0x0080, %dx
    movw $0x0600, %bx
    int $0x13
    jnc fail_write
    cmpb $3, %ah
    jne fail_write

    movw $0x0201, %ax
    xorw %cx, %cx
    movw $0x0080, %dx
    int $0x13
    jnc fail_invalid
    cmpb $4, %ah
    jne fail_invalid
    movw $0x0100, %ax
    int $0x13
    jnc fail_invalid
    cmpb $4, %ah
    jne fail_invalid
    /* Exercise packet read through original DS:SI and inspect capacity. */
    movw $dap, %si
    movw $0x4200, %ax
    movw $0x0080, %dx
    int $0x13
    jc fail_edd
    movw $0x1000, %di
    movw $256, %cx
    movw $0x5a5a, %ax
    repe scasw
    jne fail_edd
    movw $256, %cx
    movw $0xa5a5, %ax
    repe scasw
    jne fail_edd
    movw $params, %si
    movw $0x4800, %ax
    int $0x13
    jc fail_edd
    cmpw $26, params
    jne fail_edd
    cmpl $4096, params+16
    jne fail_edd
    cmpw $512, params+24
    jne fail_edd
    movw $dap, %si
    movl $1, dap+12
    movw $0x4200, %ax
    int $0x13
    jnc fail_edd
    cmpb $4, %ah
    jne fail_edd
    cmpw $0, dap+2
    jne fail_edd
    movw $0x4100, %ax
    movw $0x55aa, %bx
    int $0x13
    jnc fail_edd
    movb $0x10, %al
    jmp report
fail_edd:      movb $0x16, %al; jmp report
fail_geometry: movb $0x11, %al; jmp report
fail_read:     movb $0x12, %al; jmp report
fail_data:     movb $0x13, %al; jmp report
fail_write:    movb $0x14, %al; jmp report
fail_invalid:  movb $0x15, %al
report:
    movzbl %al, %eax
    movw $0xf4, %dx
    outl %eax, %dx
1:  cli
    hlt
    jmp 1b
    .balign 4
dap:
    .byte 16, 0
    .word 2, 0x1000, 0
    .quad 1
params:
    .word 26
    .space 24
    .org 510
    .word 0xaa55
