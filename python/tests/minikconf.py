# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
from pathlib import Path
import sys

import pytest


MINIKCONF_PATH = Path(__file__).resolve().parents[2] / "scripts" / "minikconf.py"
SPEC = importlib.util.spec_from_file_location("qemu_minikconf", MINIKCONF_PATH)
assert SPEC is not None
assert SPEC.loader is not None
minikconf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = minikconf
SPEC.loader.exec_module(minikconf)


def test_missing_include_reports_parser_error(tmp_path):
    kconfig = tmp_path / "Kconfig"
    kconfig.write_text("source missing/Kconfig\n", encoding="utf-8")

    data = minikconf.KconfigData()
    with kconfig.open("rt", encoding="utf-8") as fp:
        with pytest.raises(minikconf.KconfigParserError) as excinfo:
            minikconf.KconfigParser.parse(fp, data)

    assert "missing/Kconfig" in str(excinfo.value)


def test_include_tracking_preserves_dependency_order(tmp_path):
    child = tmp_path / "child.Kconfig"
    child.write_text("config CHILD\nbool\n", encoding="utf-8")

    kconfig = tmp_path / "Kconfig"
    kconfig.write_text(
        "source child.Kconfig\nsource child.Kconfig\n",
        encoding="utf-8",
    )

    data = minikconf.KconfigData()
    with kconfig.open("rt", encoding="utf-8") as fp:
        minikconf.KconfigParser.parse(fp, data)

    expected = [str(kconfig.resolve()), str(child.resolve())]
    assert data.previously_included == expected
    assert data._included_files == set(expected)
