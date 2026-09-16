#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic qemu-system-i386 TCG microbenchmark.

The benchmark generates a 64 KiB PC BIOS image containing a tiny real-mode
program.  This avoids firmware, disks, display backends and guest OS noise so
host-side TCG changes can be compared on the same machine.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable

BIOS_SIZE = 64 * 1024
RESET_VECTOR = 0xFFF0
DEBUG_EXIT_PORT = 0x00F4
DEBUG_EXIT_VALUE = 0x10
DEBUG_EXIT_STATUS = (DEBUG_EXIT_VALUE << 1) | 1
DEFAULT_LOOPS = 8_000_000


@dataclass
class Code:
    data: bytearray = field(default_factory=bytearray)
    labels: dict[str, int] = field(default_factory=dict)
    rel8_fixups: list[tuple[int, str]] = field(default_factory=list)

    def emit(self, *values: int) -> None:
        self.data.extend(value & 0xFF for value in values)

    def u32(self, value: int) -> None:
        self.data.extend((value & 0xFFFFFFFF).to_bytes(4, "little"))

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label: {name}")
        self.labels[name] = len(self.data)

    def jcc8(self, opcode: int, target: str) -> None:
        self.emit(opcode, 0)
        self.rel8_fixups.append((len(self.data) - 1, target))

    def finish(self) -> bytes:
        for displacement_pos, target in self.rel8_fixups:
            if target not in self.labels:
                raise ValueError(f"undefined label: {target}")
            displacement = self.labels[target] - (displacement_pos + 1)
            if not -128 <= displacement <= 127:
                raise ValueError(
                    f"short jump to {target} is out of range: {displacement}"
                )
            self.data[displacement_pos] = displacement & 0xFF
        return bytes(self.data)


def emit_prologue(code: Code) -> None:
    code.emit(0xFA)              # cli
    code.emit(0x31, 0xC0)        # xor ax, ax
    code.emit(0x8E, 0xD8)        # mov ds, ax
    code.emit(0x8E, 0xD0)        # mov ss, ax
    code.emit(0xBC, 0x00, 0x70)  # mov sp, 0x7000


def emit_loop_count(code: Code, loops: int) -> None:
    code.emit(0x66, 0xB9)        # mov ecx, imm32
    code.u32(loops)


def emit_exit(code: Code) -> None:
    code.emit(0xBA, DEBUG_EXIT_PORT & 0xFF, DEBUG_EXIT_PORT >> 8)  # mov dx,0xf4
    code.emit(0xB0, DEBUG_EXIT_VALUE)                              # mov al,0x10
    code.emit(0xEE)                                                # out dx,al
    code.emit(0xF4)                                                # hlt, defensive


def workload_startup(code: Code, loops: int) -> None:
    del loops


def workload_branch(code: Code, loops: int) -> None:
    emit_loop_count(code, loops)
    code.label("loop")
    code.emit(0x66, 0x49)        # dec ecx
    code.jcc8(0x75, "loop")      # jnz loop


def workload_flags(code: Code, loops: int) -> None:
    emit_loop_count(code, loops)
    code.emit(0x66, 0x31, 0xC0)  # xor eax,eax
    code.emit(0x66, 0xBB)        # mov ebx,0x9e3779b9
    code.u32(0x9E3779B9)
    code.label("loop")
    code.emit(0x66, 0x01, 0xD8)              # add eax,ebx
    code.emit(0x66, 0x39, 0xD8)              # cmp eax,ebx
    code.emit(0x66, 0x83, 0xD0, 0x00)        # adc eax,0 (consume CF)
    code.emit(0x66, 0x31, 0xC3)              # xor ebx,eax
    code.emit(0x66, 0x83, 0xC3, 0x03)        # add ebx,3
    code.emit(0x66, 0x49)                    # dec ecx
    code.jcc8(0x75, "loop")                  # jnz loop


def workload_memory(code: Code, loops: int) -> None:
    emit_loop_count(code, loops)
    code.emit(0x66, 0x31, 0xC0)              # xor eax,eax
    code.emit(0x66, 0xA3, 0x00, 0x05)        # mov [0x0500],eax
    code.label("loop")
    code.emit(0x66, 0xA1, 0x00, 0x05)        # mov eax,[0x0500]
    code.emit(0x66, 0x83, 0xC0, 0x01)        # add eax,1
    code.emit(0x66, 0xA3, 0x00, 0x05)        # mov [0x0500],eax
    code.emit(0x66, 0x49)                    # dec ecx
    code.jcc8(0x75, "loop")                  # jnz loop


def workload_fcomi(code: Code, loops: int) -> None:
    emit_loop_count(code, loops)
    code.emit(0xDB, 0xE3)        # fninit
    code.emit(0xD9, 0xE8)        # fld1
    code.emit(0xD9, 0xE8)        # fld1
    code.label("loop")
    code.emit(0xDB, 0xF1)        # fcomi st,st(1)
    code.emit(0x66, 0x49)        # dec ecx
    code.jcc8(0x75, "loop")      # jnz loop
    code.emit(0xDD, 0xD8)        # fstp st(0)
    code.emit(0xDD, 0xD8)        # fstp st(0)


WORKLOADS: dict[str, Callable[[Code, int], None]] = {
    "startup": workload_startup,
    "branch": workload_branch,
    "flags": workload_flags,
    "memory": workload_memory,
    "fcomi": workload_fcomi,
}


def make_bios(workload: str, loops: int) -> bytes:
    if workload not in WORKLOADS:
        raise ValueError(f"unknown workload: {workload}")
    if not 1 <= loops <= 0xFFFFFFFF:
        raise ValueError("loop count must fit in a non-zero 32-bit value")

    code = Code()
    emit_prologue(code)
    WORKLOADS[workload](code, loops)
    emit_exit(code)
    payload = code.finish()
    if len(payload) >= RESET_VECTOR:
        raise ValueError("benchmark payload overlaps the reset vector")

    bios = bytearray([0xFF]) * BIOS_SIZE
    bios[: len(payload)] = payload
    # x86 reset starts at F000:FFF0 for the 64 KiB BIOS alias.
    bios[RESET_VECTOR : RESET_VECTOR + 5] = bytes((0xEA, 0x00, 0x00, 0x00, 0xF0))
    return bytes(bios)


def qemu_command(qemu: str, bios: pathlib.Path, tcg_thread: str) -> list[str]:
    return [
        qemu,
        "-machine", "pc",
        "-accel", f"tcg,thread={tcg_thread}",
        "-cpu", "qemu32",
        "-smp", "1",
        "-m", "16M",
        "-nodefaults",
        "-display", "none",
        "-serial", "none",
        "-monitor", "none",
        "-no-reboot",
        "-bios", str(bios),
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]


def run_once(qemu: str, bios: pathlib.Path, tcg_thread: str, timeout: float) -> float:
    command = qemu_command(qemu, bios, tcg_thread)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != DEBUG_EXIT_STATUS:
        stderr = completed.stderr.strip()
        raise RuntimeError(
            f"QEMU exited with status {completed.returncode}, expected "
            f"{DEBUG_EXIT_STATUS}: {stderr}"
        )
    return elapsed


def median_runtime(
    qemu: str,
    bios: pathlib.Path,
    tcg_thread: str,
    rounds: int,
    timeout: float,
) -> tuple[float, list[float]]:
    samples = [run_once(qemu, bios, tcg_thread, timeout) for _ in range(rounds)]
    return statistics.median(samples), samples


def resolve_qemu(value: str) -> str:
    candidate = pathlib.Path(value)
    if candidate.exists():
        return str(candidate.resolve())
    found = shutil.which(value)
    if found:
        return found
    raise FileNotFoundError(f"qemu-system-i386 not found: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--loops", type=int, default=DEFAULT_LOOPS)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--tcg-thread", choices=("single", "multi"), default="single")
    parser.add_argument(
        "--workload",
        action="append",
        choices=tuple(WORKLOADS),
        help="benchmark only this workload; may be repeated",
    )
    parser.add_argument(
        "--emit-bios",
        metavar="PATH",
        help="write one BIOS image instead of running QEMU (requires one --workload)",
    )
    args = parser.parse_args()

    if args.rounds < 1:
        parser.error("--rounds must be at least 1")
    if not 1 <= args.loops <= 0xFFFFFFFF:
        parser.error("--loops must be between 1 and 4294967295")

    workloads = args.workload or list(WORKLOADS)
    if args.emit_bios:
        if len(workloads) != 1:
            parser.error("--emit-bios requires exactly one --workload")
        pathlib.Path(args.emit_bios).write_bytes(make_bios(workloads[0], args.loops))
        return 0

    qemu = resolve_qemu(args.qemu)
    print(f"QEMU:       {qemu}")
    print(f"TCG thread: {args.tcg_thread}")
    print(f"Loops:      {args.loops}")
    print(f"Rounds:     {args.rounds}")

    with tempfile.TemporaryDirectory(prefix="qemu-i386-tcg-bench-") as td:
        tempdir = pathlib.Path(td)
        medians: dict[str, float] = {}
        for workload in workloads:
            bios = tempdir / f"{workload}.bin"
            bios.write_bytes(make_bios(workload, args.loops))
            median, samples = median_runtime(
                qemu, bios, args.tcg_thread, args.rounds, args.timeout
            )
            medians[workload] = median
            sample_text = ", ".join(f"{sample * 1000:.1f}" for sample in samples)
            print(f"{workload:8s} median={median * 1000:9.1f} ms  samples=[{sample_text}] ms")

        startup = medians.get("startup")
        if startup is not None:
            print("\nNet time after subtracting startup median:")
            for workload in workloads:
                if workload == "startup":
                    continue
                net = max(0.0, medians[workload] - startup)
                print(f"{workload:8s} {net * 1000:9.1f} ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
