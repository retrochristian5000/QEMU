#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMON = ROOT / 'scripts' / 'qapi' / 'common.py'


def load_common():
    spec = importlib.util.spec_from_file_location('qapi_common_c23_test', COMMON)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {COMMON}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    common = load_common()

    c23_keywords = (
        'alignas',
        'alignof',
        'constexpr',
        'nullptr',
        'static_assert',
        'thread_local',
        'typeof_unqual',
        '_BitInt',
        '_Decimal32',
        '_Decimal64',
        '_Decimal128',
    )

    for keyword in c23_keywords:
        require(
            common.c_name(keyword) == f'q_{keyword}',
            f'C23 keyword {keyword!r} was not protected',
        )
        require(
            common.c_name(keyword, protect=False) == keyword,
            f'protect=False unexpectedly changed {keyword!r}',
        )

    # These C23 keywords were already protected by the pre-existing GNU/C++
    # compatibility sets. Keep that coverage explicit so future refactors do
    # not accidentally drop them.
    for keyword in ('bool', 'false', 'true', 'typeof'):
        require(
            common.c_name(keyword) == f'q_{keyword}',
            f'existing keyword protection regressed for {keyword!r}',
        )

    require(common.c_name('ordinary_name') == 'ordinary_name',
            'ordinary identifiers must remain unchanged')
    require(common.c_name('x-name') == 'x_name',
            'identifier sanitization regressed')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
