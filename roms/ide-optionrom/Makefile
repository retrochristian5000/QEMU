# SPDX-License-Identifier: GPL-2.0-or-later
OUT ?= out
CROSS_PREFIX ?=
AS = $(CROSS_PREFIX)as
LD = $(CROSS_PREFIX)ld
OBJCOPY = $(CROSS_PREFIX)objcopy
PYTHON ?= python3

all: $(OUT)/ide-isa.rom

$(OUT)/.toolchain: FORCE
	@mkdir -p "$(OUT)"
	@set -e; umask 077; tmp=$$(mktemp "$@.XXXXXX"); \
	    trap 'rm -f "$$tmp"' EXIT; \
	    printf '%s\n' "$(AS)" "$(LD)" "$(OBJCOPY)" "$(PYTHON)" > "$$tmp"; \
	    if ! cmp -s "$$tmp" "$@"; then mv "$$tmp" "$@"; fi

$(OUT)/ide.o: ide-rom.S $(OUT)/.toolchain Makefile
	$(AS) --32 -o "$@" "$<"

$(OUT)/ide.elf: $(OUT)/ide.o ide-rom.ld
	$(LD) -m elf_i386 -T ide-rom.ld -o "$@" "$<"

$(OUT)/ide.raw: $(OUT)/ide.elf
	$(OBJCOPY) -O binary -j .text "$<" "$@"

$(OUT)/ide-isa.rom: $(OUT)/ide.raw seal.py
	$(PYTHON) seal.py "$<" "$@"

.PHONY: all FORCE
