#!/usr/bin/env python3

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def process_command(src, command):
    skip = False
    out = []
    for item in shlex.split(command):
        if skip:
            skip = False
            continue
        if item == '-MF' or item == '-MQ' or item == '-o':
            skip = True
            continue
        if item == '-c':
            skip = True
            continue
        out.append(item)
    out.append('-DQEMU_MODINFO')
    out.append('-E')
    out.append(src)
    return out


def find_compile_commands(outputs, database='compile_commands.json'):
    """Find only requested objects without loading the whole compilation DB.

    Meson can launch multiple modinfo collectors simultaneously. json.load()
    replicated the entire compilation database in each process, even though
    each collector uses only a handful of objects. Decode one JSON object at
    a time with the standard library, retaining only matching entries.
    """
    decoder = json.JSONDecoder()
    found = {}
    buffer = ''
    position = 0
    chunk_size = 64 * 1024

    with open(database, encoding='utf-8') as stream:
        def next_nonspace():
            nonlocal buffer, position
            while True:
                if position >= len(buffer):
                    buffer = stream.read(chunk_size)
                    position = 0
                    if not buffer:
                        return None
                if buffer[position].isspace():
                    position += 1
                else:
                    return buffer[position]

        if next_nonspace() != '[':
            raise ValueError(f'{database}: expected JSON array')
        position += 1
        first = True
        while True:
            char = next_nonspace()
            if char is None:
                raise ValueError(f'{database}: truncated JSON array')
            if char == ']':
                position += 1
                break
            if not first:
                if char != ',':
                    raise ValueError(f'{database}: expected comma')
                position += 1
            if next_nonspace() != '{':
                raise ValueError(f'{database}: expected compile command object')

            while True:
                try:
                    entry, position = decoder.raw_decode(buffer, position)
                    break
                except json.JSONDecodeError as exc:
                    # raw_decode() cannot distinguish incomplete JSON from
                    # invalid JSON until it sees the rest of this one entry.
                    # Hold at most one entry plus one read chunk at a time.
                    remaining = buffer[position:]
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        raise ValueError(
                            f'{database}: invalid compile command JSON'
                        ) from exc
                    buffer = remaining + chunk
                    position = 0

            if not isinstance(entry, dict):
                raise ValueError(f'{database}: expected JSON object')
            output = entry['output']
            if output in outputs:
                # Some Ninja versions list generated headers as separate
                # entries for the same compile edge. Do not let one hide
                # the C source. For equal kinds retain last-wins ordering.
                previous = found.get(output)
                if (previous is None or entry['file'].endswith('.c') or
                        not previous['file'].endswith('.c')):
                    found[output] = entry
            first = False

        if buffer[position:].strip():
            raise ValueError(f'{database}: trailing JSON data')
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            if chunk.strip():
                raise ValueError(f'{database}: trailing JSON data')
    return found


def find_module_compile_commands(outputs):
    """Query Ninja's current graph without reading the full compilation DB."""
    ninja = shutil.which(os.environ.get('NINJA') or 'ninja')
    if not ninja and not os.environ.get('NINJA'):
        ninja = shutil.which('ninja-build')
    if ninja and Path('build.ninja').is_file():
        with tempfile.TemporaryDirectory(prefix='qemu-modinfo-') as work:
            database = Path(work) / 'commands.json'
            with database.open('w', encoding='utf-8') as stream:
                result = subprocess.run(
                    [ninja, '-t', 'compdb-targets', '-x', *sorted(outputs)],
                    stdout=stream, stderr=subprocess.PIPE, text=True,
                )
            if result.returncode == 0:
                selected = find_compile_commands(outputs, database)
                if outputs <= selected.keys():
                    return selected
            # Older Ninja releases lack compdb-targets. Keep the existing
            # bounded-memory reader as the compatibility path. Never reuse
            # a database from a different build graph.
    return find_compile_commands(outputs)


def emit_preprocessed_modinfo(cmdline):
    """Stream compiler output; keep no full preprocessor output in RAM."""
    with subprocess.Popen(cmdline, stdout=subprocess.PIPE, text=True) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            if 'MODINFO' in line:
                print(line, end='' if line.endswith('\n') else '\n')
        return proc.wait()


def main(args):
    target = ''
    if args[0] == '--target':
        args.pop(0)
        target = args.pop(0)
        print("MODINFO_DEBUG target %s" % target)
        arch = target[:-8]  # cut '-softmmu'
        print('MODINFO_START arch "%s" MODINFO_END' % arch)

    compile_commands = find_module_compile_commands(set(args))

    for obj in args:
        entry = compile_commands.get(obj)
        if not entry:
            sys.stderr.write(f'modinfo: Could not find object file {obj}')
            sys.exit(1)
        src = entry['file']
        if not src.endswith('.c'):
            print("MODINFO_DEBUG skip %s" % src)
            continue
        command = entry['command']
        print("MODINFO_DEBUG src %s" % src)
        cmdline = process_command(src, command)
        print("MODINFO_DEBUG cmd", cmdline)
        result = emit_preprocessed_modinfo(cmdline)
        if result != 0:
            sys.exit(result)


if __name__ == "__main__":
    main(sys.argv[1:])
