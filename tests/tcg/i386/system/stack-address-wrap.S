/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Real-mode RETF must wrap each stack-slot address independently. */
    .text
    .code32
    .globl main
main:
    cli
    movl %esp, saved_esp
    cld
    movl $real_blob, %esi
    movl $0x7000, %edi
    movl $(real_end - real_blob), %ecx
    rep movsb
    movl $real_blob, %esi
    movl $0x9000, %edi
    movl $(real_end - real_blob), %ecx
    rep movsb
    lgdt test_gdtr
    ljmp $0x18, $0

    .code16
real_blob:
    /* Establish 16-bit segment caches before clearing PE. */
    movw $0x20, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    movl %cr0, %eax
    andl $~1, %eax
    movl %eax, %cr0
    ljmp $0x700, $(real_start - real_blob)
real_start:
    movw $0x2000, %ax
    movw %ax, %ss
    movw $0x3000, %ax
    movw %ax, %es

    /* CS must come from SS:0000, not the following linear segment. */
    movw $(return16 - real_blob), %ss:0xfffe
    movw $0x700, %ss:0
    movw $0x900, %es:0
    movl $0x1234fffe, %esp
    lretw
return16:
    movw %cs, %ax
    cmpw $0x700, %ax
    jne fail
    cmpl $0x12340002, %esp
    jne fail

    /* Repeat with a 32-bit operand and the same 16-bit stack. */
    movl $(return32 - real_blob), %ss:0xfffc
    movl $0x700, %ss:0
    movl $0x900, %es:0
    movl $0x5678fffc, %esp
    lretl
return32:
    movw %cs, %ax
    cmpw $0x700, %ax
    jne fail
    cmpl $0x56780004, %esp
    jne fail
    xorl %edx, %edx
    jmp finish
fail:
    movl $1, %edx
finish:
    movl %cr0, %eax
    orl $1, %eax
    movl %eax, %cr0
    ljmpl $0x8, $protected_return
real_end:

    .code32
protected_return:
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    movl saved_esp, %esp
    movl %edx, %eax
    ret

    .data
    .balign 8
test_gdt:
    .quad 0
    .quad 0x00cf9b000000ffff /* flat 32-bit code */
    .quad 0x00cf93000000ffff /* flat 32-bit data */
    .quad 0x00009b007000ffff /* 16-bit code at 0x7000 */
    .quad 0x000093000000ffff /* 16-bit data at 0 */
test_gdt_end:
test_gdtr:
    .word test_gdt_end - test_gdt - 1
    .long test_gdt
saved_esp:
    .long 0
    .section .note.GNU-stack,"",@progbits
