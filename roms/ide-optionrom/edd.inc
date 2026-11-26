/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Preliminary EDD 1.1 packet services. No AH=41h subset advertised until
 * write, verify and seek are implemented. FS is caller DS; SS:BP is frame. */
edd_read:
    movw %ss:-28(%bp), %si
    cmpw $0xfff0, %si
    ja edd_invalid
    cmpb $16, %fs:(%si)
    jb edd_invalid
    cmpb $0, %fs:1(%si)
    jne edd_invalid
    cmpb $0, %fs:3(%si)
    jne edd_invalid
    movzwl %fs:2(%si), %ebx
    cmpl $127, %ebx
    ja edd_invalid
    cmpl $0, %fs:12(%si)
    jne edd_range
    movl %fs:8(%si), %eax
    cmpl %cs:capacity, %eax
    jae edd_range
    movl %eax, %ecx
    addl %ebx, %ecx
    jc edd_range
    cmpl %cs:capacity, %ecx
    ja edd_range
    testl %ebx, %ebx
    jz edd_success
    cmpw $0xffff, %fs:4(%si)
    jne 1f
    cmpw $0xffff, %fs:6(%si)
    je edd_boundary
1:  movzwl %fs:4(%si), %edi
    movw %fs:6(%si), %es
    movl %ebx, %ecx
    shll $9, %ecx
    addl %edi, %ecx
    cmpl $65536, %ecx
    ja edd_boundary
    movl %eax, %esi
    cld
    call mask_irq
    call select_master
    jc edd_failed
edd_next:
    call read_sector
    jc edd_failed
    incl %esi
    decl %ebx
    jnz edd_next
    call unmask_irq
edd_success:
    xorb %ah, %ah
    jmp finish
edd_failed:
    call unmask_irq
    movw %ss:-28(%bp), %si
    subw %bx, %fs:2(%si)
    movb $0x20, %ah
    jmp finish
edd_range:
    movw $0, %fs:2(%si)
    movb $4, %ah
    jmp finish
edd_boundary:
    movw $0, %fs:2(%si)
    movb $9, %ah
    jmp finish
edd_invalid:
    movb $1, %ah
    jmp finish
edd_write_protected:
    /* Do not claim write completion or access the disk. */
    movw %ss:-28(%bp), %si
    cmpw $0xfff0, %si
    ja edd_invalid
    cmpb $16, %fs:(%si)
    jb edd_invalid
    cmpb $0, %fs:1(%si)
    jne edd_invalid
    cmpb $0, %fs:3(%si)
    jne edd_invalid
    movw $0, %fs:2(%si)
    movb $3, %ah
    jmp finish
edd_parameters:
    movw %ss:-28(%bp), %si
    cmpw $0xfffe, %si
    ja edd_invalid
    cmpw $26, %fs:(%si)
    jb edd_invalid
    cmpw $0xffe6, %si
    ja edd_invalid
    /* Basic 26-byte table; no DPTE or EDD 3.0 path claimed. */
    movw $26, %fs:(%si)
    movw $0, %fs:2(%si)             /* Physical geometry not asserted. */
    movl $0, %fs:4(%si)
    movl $0, %fs:8(%si)
    movl $0, %fs:12(%si)
    movl %cs:capacity, %eax
    movl %eax, %fs:16(%si)
    movl $0, %fs:20(%si)
    movw $512, %fs:24(%si)
    jmp edd_success
