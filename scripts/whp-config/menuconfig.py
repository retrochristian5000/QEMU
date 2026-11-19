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


def _edit_string(stdscr, prompt: str, current: str, allow_clear: bool = False) -> str:
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
        return value if allow_clear else (value or current)
    finally:
        curses.noecho()
        curses.curs_set(0)


def _flatten_items(filter_text: str = '', values=None):
    """Return only matching options, retaining their section/group context."""
    needle = filter_text.strip().casefold()
    rows = []
    for section, options in whp_config.sections(values):
        matching = [
            option for option in options
            if not needle or any(
                needle in item.casefold()
                for item in (section, option.group, option.label, option.key)
            )
        ]
        if not matching:
            continue
        rows.append(('section', section, None))
        current_group = None
        for option in matching:
            if option.group:
                if option.group != current_group:
                    rows.append(('group', option.group, None))
                current_group = option.group
            else:
                current_group = None
            rows.append(('option', option.label, option))
    return rows


def _selectable_positions(rows):
    return [index for index, row in enumerate(rows) if row[0] == 'option']


def _section_positions(rows, selectable):
    """Positions of the first selectable entry in each visible section."""
    return [
        index for index, row_index in enumerate(selectable)
        if index == 0 or any(
            rows[position][0] == 'section'
            for position in range(selectable[index - 1] + 1, row_index)
        )
    ]


def _run(stdscr, config_path: pathlib.Path, state) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    filter_text = ''
    rows = _flatten_items(values=state.values)
    selectable = _selectable_positions(rows)
    selected_pos = 0
    scroll_top = 0
    saved_values = dict(state.values)
    dirty = False
    status = 'Arrows/PgUp/PgDn move  [] sections  / find  Space edit  s save  ? help  q quit'

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        if height < 8 or width < 40:
            if height > 1 and width > 2:
                stdscr.addnstr(
                    0, 0, 'Resize terminal to at least 40x8', width - 1,
                )
                stdscr.addnstr(1, 0, 'Settings are preserved; resize to continue', width - 1)
            stdscr.refresh()
            if stdscr.getch() == ord('q') and not dirty:
                return
            continue

        current_row = selectable[selected_pos]
        option = rows[current_row][2]
        assert option is not None
        viewport_rows = height - 6
        scroll_top = _scroll_top(len(rows), current_row, scroll_top, viewport_rows)
        visible_end = min(len(rows), scroll_top + viewport_rows)

        stdscr.addnstr(0, 0, 'WHP QEMU Configuration', width - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, f'File: {config_path}', width - 1)
        match_count = len(selectable)
        scope = f'Filter: {filter_text}' if filter_text else 'All options'
        stdscr.addnstr(2, 0, f'{scope} ({match_count} matches)', width - 1)

        for index in range(scroll_top, visible_end):
            row_kind, label, row_option = rows[index]
            y = 3 + index - scroll_top
            if row_kind == 'section':
                stdscr.addnstr(y, 0, label, width - 1, curses.A_BOLD)
            elif row_kind == 'group':
                if label == 'System emulators':
                    mode = 'collapsed' if state.values['BUILD_QEMU_SYSTEM_ALL'] == 'y' else 'expanded'
                    label = f'{label} ({mode})'
                stdscr.addnstr(y, 2, label, width - 3, curses.A_BOLD)
            else:
                assert row_option is not None
                value = display_value(row_option.kind, state.values[row_option.key])
                indent = '    ' if row_option.group else '  '
                line = f'{indent}{value:<10} {label}'
                attr = curses.A_REVERSE if index == current_row else curses.A_NORMAL
                stdscr.addnstr(y, 0, line, width - 1, attr)

        details = f'{option.key}={state.values[option.key]}  default={option.default}'
        if scroll_top:
            details += '  ↑ more'
        if visible_end < len(rows):
            details += '  ↓ more'
        if state.unknown:
            details += f'  {len(state.unknown)} preserved unknown setting(s)'
        stdscr.addnstr(height - 3, 0, details, width - 1)
        stdscr.addnstr(height - 2, 0, status, width - 1)
        stdscr.addnstr(
            height - 1, 0, 'Modified' if dirty else 'Saved',
            width - 1, curses.A_BOLD if dirty else curses.A_NORMAL,
        )
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
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
        if key in (curses.KEY_HOME, ord('g')):
            selected_pos = 0
            continue
        if key in (curses.KEY_END, ord('G')):
            selected_pos = len(selectable) - 1
            continue
        if key in (ord('['), ord(']')):
            starts = _section_positions(rows, selectable)
            if key == ord(']'):
                selected_pos = next(
                    (pos for pos in starts if pos > selected_pos), starts[0],
                )
            else:
                selected_pos = next(
                    (pos for pos in reversed(starts) if pos < selected_pos),
                    starts[-1],
                )
            continue
        if key in (ord('/'), ord('f')):
            candidate = _edit_string(
                stdscr, 'Filter (empty shows all)', filter_text, allow_clear=True,
            )
            matching = _flatten_items(candidate, state.values)
            new_selectable = _selectable_positions(matching)
            if not new_selectable:
                status = f'No settings match {candidate!r}; previous filter retained'
                continue
            selected_key = option.key
            rows, selectable, filter_text = matching, new_selectable, candidate
            selected_pos = next(
                (
                    pos for pos, index in enumerate(selectable)
                    if rows[index][2].key == selected_key
                ),
                0,
            )
            scroll_top = 0
            status = 'Filter cleared' if not filter_text else f'Filtering by {filter_text!r}'
            continue
        if key == ord('?'):
            choices = ', '.join(option.choices) if option.choices else option.kind
            status = f'{option.key}: {choices}; default={option.default}'
            continue
        if key in (ord(' '), curses.KEY_ENTER, 10, 13):
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
                dirty = state.values != saved_values
                if option.key == 'BUILD_QEMU_SYSTEM_ALL':
                    # Rebuild from current values without mutating stored
                    # individual selections; turning all off restores them.
                    rows = _flatten_items(filter_text, state.values)
                    selectable = _selectable_positions(rows)
                    selected_pos = next(
                        (
                            pos for pos, index in enumerate(selectable)
                            if rows[index][2].key == option.key
                        ),
                        0,
                    )
                    scroll_top = 0
                try:
                    whp_config.validate_combinations(state.values)
                except ValueError as exc:
                    status = f'Conflict (fix before saving): {exc}'
                else:
                    status = f'Changed {option.label}; press s to save'
            continue
        if key == ord('r'):
            state.values = whp_config.default_values()
            dirty = state.values != saved_values
            rows = _flatten_items(filter_text, state.values)
            selectable = _selectable_positions(rows)
            if not selectable:
                filter_text = ''
                rows = _flatten_items(values=state.values)
                selectable = _selectable_positions(rows)
            selected_pos = 0
            scroll_top = 0
            status = 'Repository defaults loaded; press s to save'
            continue
        if key == ord('s'):
            try:
                whp_config.save_config(config_path, state)
            except (OSError, ValueError) as exc:
                status = f'Cannot save: {exc}'
                continue
            saved_values = dict(state.values)
            dirty = False
            status = f'Saved {config_path}'
            continue
        if key == ord('q'):
            if dirty:
                status = 'Unsaved changes: press q again to discard, or any key to return'
                stdscr.erase()
                stdscr.addnstr(0, 0, status, width - 1, curses.A_BOLD)
                stdscr.refresh()
                if stdscr.getch() != ord('q'):
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
        for section, options in whp_config.sections(state.values):
            print(section)
            current_group = None
            for option in options:
                if option.group:
                    if option.group != current_group:
                        print(f'  {option.group}')
                    current_group = option.group
                    indent = '    '
                else:
                    current_group = None
                    indent = '  '
                print(
                    f'{indent}{display_value(option.kind, state.values[option.key]):<10} '
                    f'{option.label}'
                )
        return 0

    if curses is None:
        print('error: terminal menu support is unavailable in this Python build', file=sys.stderr)
        print(f'edit {config_path} directly or use --dump to inspect settings', file=sys.stderr)
        return 2

    curses.wrapper(_run, config_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
