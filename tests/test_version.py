"""
tests/test_version.py — La versión es la misma en todas partes

Hay dos fuentes que se editan a mano: lockd/__init__.py (lo que imprime
`lockd --version`) y pyproject.toml (lo que instalan pip y el .deb). Una
fuente única leída por setuptools choca con el shim lockd.py de la raíz, así
que este test las compara entre sí y con la versión upstream de
debian/changelog (la parte anterior a "+" o "-": 1.0.2+parrot1 -> 1.0.2).
"""
import re
import tomllib
from pathlib import Path

import lockd

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _debian_upstream_version() -> str:
    first = (ROOT / "debian" / "changelog").read_text(encoding="utf-8").splitlines()[0]
    m = re.match(r"^lockd \(([^)]+)\)", first)
    assert m, f"Primera línea inesperada en debian/changelog: {first!r}"
    upstream = re.match(r"^(\d+(?:\.\d+)*)", m.group(1))
    assert upstream, f"Versión Debian sin parte upstream numérica: {m.group(1)!r}"
    return upstream.group(1)


def test_init_coincide_con_pyproject():
    assert lockd.__version__ == _pyproject_version()


def test_debian_changelog_coincide_con_pyproject():
    assert _debian_upstream_version() == _pyproject_version()
