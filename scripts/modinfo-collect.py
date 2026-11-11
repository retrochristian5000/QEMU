#!/usr/bin/env python3

import json
import shlex
import subprocess
import sys


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
                # Match the previous dictionary comprehension: last wins
                # if the same output occurs more than once.
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

    compile_commands = find_compile_commands(set(args))

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
