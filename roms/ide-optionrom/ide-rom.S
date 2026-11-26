/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Experimental ISA IDE option ROM: one primary master, read-only CHS. */
.code16
.section .text,"ax",@progbits
.global _start
_start:
    .word 0xaa55
    .byte (rom_end - _start) / 512
    lret                            /* PnP initialization; BCV connects disk. */
    .org 0x18
    .word 0                         /* Not a PCI ROM. */
    .word pnp_header - _start
pnp_header:
    .ascii "$PnP"
    .byte 1, 2                      /* Revision, length in 16-byte units. */
    .word 0
    .byte 0, 0                      /* Reserved, checksum (build tool). */
    .long 0
    .word manufacturer - _start, product - _start
    .byte 1, 1, 0, 0x14             /* Mass storage, IDE, IPL device. */
    .word connect - _start, 0, 0, 0, 0

.equ ATA_DATA, 0x1f0
.equ ATA_COUNT, 0x1f2
.equ ATA_DEVICE, 0x1f6
.equ ATA_STATUS, 0x1f7
.equ ATA_CONTROL, 0x3f6
.equ IVT_INT13, 0x4c
.equ BDA_STATUS, 0x474
.equ BDA_DRIVES, 0x475
.equ HEADS, 16
.equ SECTORS, 63
.equ CYL_SECTORS, HEADS * SECTORS
.equ POLL_LIMIT, 1000000

/* BCV: do not displace another BIOS disk provider. No runtime ROM writes. */
connect:
    pushfw
    cli
    pushal
    pushw %ds
    xorw %ax, %ax
    movw %ax, %ds
    cmpb $0, BDA_DRIVES
    jne connect_done
    call mask_irq
    call identify
    pushfw
    call unmask_irq
    popfw
    jc connect_done
    /* Expose only complete CHS cylinders, up to the INT 13h limit. */
    movl %esi, %eax
    xorl %edx, %edx
    movl $CYL_SECTORS, %ecx
    divl %ecx
    testl %eax, %eax
    jz connect_done
    cmpl $1024, %eax
    jbe 1f
    movw $1024, %ax
1:  movw %ax, %cs:cylinders
    cmpw %ax, %cs:cylinders          /* Requires writable option-ROM shadow. */
    jne connect_done
    movl IVT_INT13, %eax
    testl %eax, %eax
    jz connect_done
    movl %eax, %cs:previous_int13
    cmpl %eax, %cs:previous_int13
    jne connect_done
    movw $int13_handler - _start, IVT_INT13
    movw %cs, IVT_INT13+2
    movb $1, BDA_DRIVES
    movb $0, BDA_STATUS
connect_done:
    popw %ds
    popal
    popfw
    lret

/* Preserve caller flags before forwarding requests for other drives. */
int13_handler:
    pushfw
    cmpb $0x80, %dl
    je 1f
    popfw
    ljmpw *%cs:previous_int13
1:  popfw
    pushw %bp
    movw %sp, %bp
    pushal
    pushw %ds
    pushw %es
    xorw %ax, %ax
    movw %ax, %ds
    movb %ss:-3(%bp), %al            /* Saved AH. */
    cmpb $1, %al
    je last_status
    cmpb $2, %al
    je read_chs
    cmpb $3, %al
    je write_protected
    cmpb $8, %al
    je geometry
    movb $1, %ah                    /* Unsupported (including EDD/reset). */
    jmp finish
last_status:
    movb BDA_STATUS, %ah
    jmp finish
write_protected:
    movb $3, %ah
    jmp finish
geometry:
    movw %cs:cylinders, %ax
    decw %ax
    movb %al, %ss:-7(%bp)            /* CH: cylinder low bits. */
    andb $3, %ah
    shlb $6, %ah
    orb $SECTORS, %ah
    movb %ah, %ss:-8(%bp)            /* CL: cylinder high bits, sectors. */
    movw $((HEADS-1)*256+1), %ss:-12(%bp) /* DH: max head, DL: drives. */
    xorb %ah, %ah
    jmp finish

read_chs:
    movzbl %ss:-4(%bp), %ebx         /* Sector count. */
    testl %ebx, %ebx
    jz invalid_sector
    cmpl $127, %ebx
    ja invalid_sector
    movzbl %ss:-7(%bp), %eax
    movzbl %ss:-8(%bp), %ecx
    movl %ecx, %edx
    andl $0xc0, %edx
    shll $2, %edx
    orl %edx, %eax
    cmpw %cs:cylinders, %ax
    jae invalid_sector
    imull $HEADS, %eax, %eax
    movzbl %ss:-11(%bp), %edx
    cmpl $HEADS, %edx
    jae invalid_sector
    addl %edx, %eax
    imull $SECTORS, %eax, %eax
    andl $0x3f, %ecx
    jz invalid_sector
    decl %ecx
    addl %ecx, %eax
    movl %eax, %esi
    movzwl %cs:cylinders, %ecx
    imull $CYL_SECTORS, %ecx, %ecx
    addl %ebx, %eax
    cmpl %ecx, %eax
    ja invalid_sector
    movzwl %ss:-16(%bp), %edi        /* ES:BX buffer. */
    movl %ebx, %ecx
    shll $9, %ecx
    addl %edi, %ecx
    cmpl $65536, %ecx
    ja buffer_boundary
    cld
    call mask_irq
    call select_master
    jc read_failed
read_next:
    call read_sector
    jc read_failed
    incl %esi
    decl %ebx
    jnz read_next
    call unmask_irq
    xorb %ah, %ah
    jmp finish
read_failed:
    call unmask_irq
    subb %bl, %ss:-4(%bp)            /* Report completed sectors. */
    movb $0x20, %ah
    jmp finish
invalid_sector:
    movb $0, %ss:-4(%bp)
    movb $4, %ah
    jmp finish
buffer_boundary:
    movb $0, %ss:-4(%bp)
    movb $9, %ah
finish:
    movb %ah, BDA_STATUS
    movb %ah, %ss:-3(%bp)
    andw $0xfffe, %ss:6(%bp)         /* Carry in interrupted FLAGS. */
    testb %ah, %ah
    jz 1f
    orw $1, %ss:6(%bp)
1:  popw %es
    popw %ds
    popal
    popw %bp
    iretw

/* All transfers use polling, with an explicit bounded loop. */
mask_irq:
    movw $ATA_CONTROL, %dx
    movb $2, %al
    outb %al, %dx
    ret
unmask_irq:
    movw $ATA_STATUS, %dx
    inb %dx, %al                    /* Acknowledge pending ATA interrupt. */
    movw $ATA_CONTROL, %dx
    xorb %al, %al
    outb %al, %dx
    ret
ata_delay:
    movw $ATA_CONTROL, %dx
    inb %dx, %al
    inb %dx, %al
    inb %dx, %al
    inb %dx, %al
    ret
select_master:
    movw $ATA_DEVICE, %dx
    movb $0xe0, %al
    outb %al, %dx
    call ata_delay
    jmp wait_idle
wait_idle:
    movw $ATA_STATUS, %dx
    movl $POLL_LIMIT, %ecx
1:  inb %dx, %al
    cmpb $0xff, %al
    je ata_error
    testb $0x88, %al                 /* BSY or DRQ. */
    jnz 2f
    testb $0x40, %al                 /* DRDY. */
    jnz ata_ok
2:  decl %ecx
    jnz 1b
    jmp ata_error
wait_data:
    movw $ATA_STATUS, %dx
    movl $POLL_LIMIT, %ecx
1:  inb %dx, %al
    cmpb $0xff, %al
    je ata_error
    testb $0x80, %al
    jnz 2f
    testb $0x21, %al                 /* DF or ERR. */
    jnz ata_error
    testb $8, %al
    jnz ata_ok
2:  decl %ecx
    jnz 1b
ata_error:
    stc
    ret
ata_ok:
    clc
    ret
wait_complete:
    call wait_idle
    jc 1f
    testb $0x21, %al
    jnz ata_error
1:  ret

/* IDENTIFY: obtain LBA28 capacity; reject non-LBA/long logical sectors. */
identify:
    call select_master
    jc ata_error
    movw $ATA_COUNT, %dx
    xorb %al, %al
    outb %al, %dx
    incw %dx
    outb %al, %dx
    incw %dx
    outb %al, %dx
    incw %dx
    outb %al, %dx
    movw $ATA_STATUS, %dx
    movb $0xec, %al
    outb %al, %dx
    call ata_delay
    call wait_data
    jc ata_error
    xorw %bx, %bx
    xorl %esi, %esi
    xorw %di, %di
    xorw %cx, %cx
    movw $ATA_DATA, %dx
1:  inw %dx, %ax
    cmpw $49, %cx
    jne 2f
    movw %ax, %bx
2:  cmpw $60, %cx
    jne 3f
    movzwl %ax, %esi
3:  cmpw $61, %cx
    jne 4f
    movzwl %ax, %eax
    shll $16, %eax
    orl %eax, %esi
4:  cmpw $106, %cx
    jne 5f
    movw %ax, %di
5:  incw %cx
    cmpw $256, %cx
    jb 1b
    call wait_complete
    jc ata_error
    testw $0x200, %bx
    jz ata_error
    andw $0xd000, %di
    cmpw $0x5000, %di
    je ata_error
    testl %esi, %esi
    jz ata_error
    cmpl $0x10000000, %esi
    ja ata_error
    clc
    ret

/* ESI: LBA, ES:DI: output. Advances DI by one sector on transfer. */
read_sector:
    call wait_idle
    jc ata_error
    movl %esi, %eax
    shrl $24, %eax
    andb $0x0f, %al
    orb $0xe0, %al
    movw $ATA_DEVICE, %dx
    outb %al, %dx
    call ata_delay
    call wait_idle
    jc ata_error
    movw $ATA_COUNT, %dx
    movb $1, %al
    outb %al, %dx
    movl %esi, %eax
    incw %dx
    outb %al, %dx
    shrl $8, %eax
    incw %dx
    outb %al, %dx
    shrl $8, %eax
    incw %dx
    outb %al, %dx
    movw $ATA_STATUS, %dx
    movb $0x20, %al
    outb %al, %dx
    call ata_delay
    call wait_data
    jc ata_error
    movw $ATA_DATA, %dx
    movw $256, %cx
    rep insw
    call ata_delay
    jmp wait_complete

previous_int13: .long 0
cylinders: .word 0
manufacturer: .asciz "WHP"
product: .asciz "Experimental read-only ISA IDE"
    .byte 0
    .balign 512, 0
rom_end:
