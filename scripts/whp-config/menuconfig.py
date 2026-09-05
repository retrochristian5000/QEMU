#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse

try:
    import curses
except ImportError:  # Windows and minimal Python builds
    curses = None

import pathlib
import sys
from typing import List, Optional, Tuple

import config as whp_config


def cycle_value(kind: str, value: str, choices: Tuple[str, ...]) -> str:
    if kind == 'bool':
        return 'n' if value == 'y' else 'y'
    if kind == 'choice':
        index = choices.index(value)
        return choices[(index + 1) % len(choices)]
    return value


def display_value(kind: str, value: str) -> str:
    if kind == 'bool':
        return '[*]' if value == 'y' else '[ ]'
    if kind == 'choice':
        return f'<{value}>'
    return value


def _scroll_top(row_count: int, selected_row: int, top: int, viewport_rows: int) -> int:
    if row_count <= 0 or viewport_rows <= 0:
        return 0
    viewport_rows = min(viewport_rows, row_count)
    max_top = row_count - viewport_rows
    top = min(max(top, 0), max_top)
    selected_row = min(max(selected_row, 0), row_count - 1)
    if selected_row < top:
        return selected_row
    if selected_row >= top + viewport_rows:
        return min(selected_row - viewport_rows + 1, max_top)
    return top


def _edit_string(stdscr, prompt: str, current: str) -> str:
    height, width = stdscr.getmaxyx()
    curses.echo()
    curses.curs_set(1)
    try:
        stdscr.move(height - 2, 0)
        stdscr.clrtoeol()
        text = f'{prompt} [{current}]: '
        stdscr.addnstr(height - 2, 0, text, max(1, width - 1))
        raw = stdscr.getstr(height - 2, min(len(text), width - 1), max(1, width - len(text) - 1))
        value = raw.decode(errors='replace').strip()
        return value or current
    finally:
        curses.noecho()
        curses.curs_set(0)


def _flatten_items():
    rows = []
    for section, options in whp_config.sections():
        rows.append(('section', section, None))
        for option in options:
            rows.append(('option', option.label, option))
    return rows


def _run(stdscr, config_path: pathlib.Path, state) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    rows = _flatten_items()
    selectable = [i for i, row in enumerate(rows) if row[0] == 'option']
    selected_pos = 0
    scroll_top = 0
    dirty = False
    status = 'Arrows move  PgUp/PgDn page  Space/Enter change  s save  r defaults  q quit'

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, 'WHP QEMU Configuration', max(1, width - 1), curses.A_BOLD)
        stdscr.addnstr(1, 0, f'File: {config_path}', max(1, width - 1))
        current_row = selectable[selected_pos]
        viewport_rows = max(0, height - 6)
        scroll_top = _scroll_top(len(rows), current_row, scroll_top, viewport_rows)
        y = 3
        if viewport_rows:
            visible_end = min(len(rows), scroll_top + viewport_rows)
            for index in range(scroll_top, visible_end):
                row_kind, label, option = rows[index]
                if row_kind == 'section':
                    stdscr.addnstr(y, 0, label, max(1, width - 1), curses.A_BOLD)
                else:
                    assert option is not None
                    value = display_value(option.kind, state.values[option.key])
                    line = f'  {value:<10} {label}'
                    attr = curses.A_REVERSE if index == current_row else curses.A_NORMAL
                    stdscr.addnstr(y, 0, line, max(1, width - 1), attr)
                y += 1
        else:
            visible_end = scroll_top

        if height >= 3:
            more = []
            if scroll_top > 0:
                more.append('↑ more')
            if visible_end < len(rows):
                more.append('↓ more')
            if state.unknown:
                more.append(f'{len(state.unknown)} preserved unknown setting(s)')
            stdscr.addnstr(height - 3, 0, '  '.join(more), max(1, width - 1))

        stdscr.addnstr(height - 2, 0, status, max(1, width - 1))
        if dirty:
            stdscr.addnstr(height - 1, 0, 'Modified', max(1, width - 1), curses.A_BOLD)
        else:
            stdscr.addnstr(height - 1, 0, 'Saved', max(1, width - 1))
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord('k')):
            selected_pos = (selected_pos - 1) % len(selectable)
            continue
        if key in (curses.KEY_DOWN, ord('j')):
            selected_pos = (selected_pos + 1) % len(selectable)
            continue
        if key == curses.KEY_PPAGE:
            selected_pos = max(0, selected_pos - max(1, viewport_rows - 1))
            continue
        if key == curses.KEY_NPAGE:
            selected_pos = min(len(selectable) - 1, selected_pos + max(1, viewport_rows - 1))
            continue
        if key == curses.KEY_HOME:
            selected_pos = 0
            continue
        if key == curses.KEY_END:
            selected_pos = len(selectable) - 1
            continue
        if key in (ord(' '), curses.KEY_ENTER, 10, 13):
            option = rows[selectable[selected_pos]][2]
            assert option is not None
            old = state.values[option.key]
            if option.kind in ('bool', 'choice'):
                new = cycle_value(option.kind, old, option.choices)
            else:
                new = _edit_string(stdscr, option.label, old)
                try:
                    whp_config.validate_value(option, new)
                except (OSError, ValueError) as exc:
                    status = str(exc)
                    continue
            if new != old:
                state.values[option.key] = new
                dirty = True
                status = f'Changed {option.label}; press s to save'
            continue
        if key == ord('r'):
            state.values = whp_config.default_values()
            dirty = True
            status = 'Repository defaults loaded; press s to save'
            continue
        if key == ord('s'):
            whp_config.save_config(config_path, state)
            dirty = False
            status = f'Saved {config_path}'
            continue
        if key == ord('q'):
            if dirty:
                status = 'Unsaved changes: press q again to discard, or s to save'
                stdscr.erase()
                stdscr.addnstr(0, 0, status, max(1, width - 1), curses.A_BOLD)
                stdscr.refresh()
                confirm = stdscr.getch()
                if confirm != ord('q'):
                    continue
            return


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='?', default='.whpconfig')
    parser.add_argument('--dump', action='store_true')
    args = parser.parse_args(argv)
    config_path = pathlib.Path(args.config).resolve()

    try:
        state = whp_config.load_config(config_path)
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    if args.dump:
        for section, options in whp_config.sections():
            print(section)
            for option in options:
                print(f'  {display_value(option.kind, state.values[option.key]):<10} {option.label}')
        return 0

    if curses is None:
        print('error: terminal menu support is unavailable in this Python build', file=sys.stderr)
        print(f'edit {config_path} directly or use --dump to inspect settings', file=sys.stderr)
        return 2

    curses.wrapper(_run, config_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
