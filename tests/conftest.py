"""
tests/conftest.py — Temporales donde se pueda ejecutar

Varios tests ejecutan archivos que crean en tmp_path: los stubs y el centinela
del modo test, los scripts de prueba del executor. Si el temporal está montado
con noexec (lo que Lockd mismo recomienda para /tmp), esos archivos no corren
y los tests fallarían por eso y no por lo que prueban. En ese caso, salvo que
se pase --basetemp, los temporales van a $XDG_CACHE_HOME/lockd-pytest
(~/.cache/lockd-pytest), con un aviso que se ve aun con -q. pytest borra ese
directorio al empezar cada corrida.
"""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


def _permite_ejecutar(directorio: Path) -> bool:
    directorio.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directorio) as tmp:
        prueba = Path(tmp) / "prueba-exec"
        prueba.write_text("#!/bin/sh\nexit 0\n")
        prueba.chmod(0o700)
        try:
            return subprocess.run([str(prueba)], timeout=10).returncode == 0
        except OSError:                      # EACCES en un montaje noexec
            return False


@pytest.hookimpl(tryfirst=True)              # antes de que pytest arme tmp_path
def pytest_configure(config):
    if config.option.basetemp:               # quien corre eligió: se respeta
        return
    raiz = Path(os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir())
    if _permite_ejecutar(raiz):
        return
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if not _permite_ejecutar(cache):
        raise pytest.UsageError(
            f"Ni {raiz} ni {cache} permiten ejecutar archivos (noexec): "
            "pasá --basetemp=<directorio que lo permita>.")
    destino = cache / "lockd-pytest"
    config.option.basetemp = str(destino)
    config.issue_config_time_warning(pytest.PytestConfigWarning(
        f"{raiz} no permite ejecutar archivos (noexec): los temporales de los "
        f"tests van a {destino}"), stacklevel=2)
