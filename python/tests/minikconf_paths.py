# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
from pathlib import Path
import sys


MINIKCONF_PATH = Path(__file__).resolve().parents[2] / "scripts" / "minikconf.py"
SPEC = importlib.util.spec_from_file_location("qemu_minikconf_paths", MINIKCONF_PATH)
assert SPEC is not None
assert SPEC.loader is not None
minikconf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = minikconf
SPEC.loader.exec_module(minikconf)


def test_include_tracking_normalizes_paths(tmp_path):
    child = tmp_path / "child.Kconfig"
    child.write_text("config CHILD\nbool\n", encoding="utf-8")

    kconfig = tmp_path / "Kconfig"
    kconfig.write_text(
        "source child.Kconfig\nsource ./child.Kconfig\n",
        encoding="utf-8",
    )

    data = minikconf.KconfigData()
    with kconfig.open("rt", encoding="utf-8") as fp:
        minikconf.KconfigParser.parse(fp, data)

    expected = [str(kconfig.resolve()), str(child.resolve())]
    assert data.previously_included == expected
    assert data._included_files == set(expected)


def test_depfile_path_escaping():
    assert minikconf.escape_depfile_path("plain/path") == "plain/path"
    assert minikconf.escape_depfile_path("path with space") == "path\\ with\\ space"
    assert minikconf.escape_depfile_path("hash#path") == "hash\\#path"
    assert minikconf.escape_depfile_path("cash$path") == "cash$$path"
    assert minikconf.escape_depfile_path("back\\ slash") == "back\\\\\\ slash"
