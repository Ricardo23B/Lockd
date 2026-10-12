"""
tests/test_modo_test.py — Resguardos del modo test de _common.sh (LOCKD_SYSROOT)

LOCKD_SYSROOT redirige las rutas de los módulos a un árbol de prueba. Lo que
pueda salir mal tiene que fallar cerrado; estos tests lo fijan:
  - una raíz inexistente aborta; una que resuelve a "/" (también "//", "/." o
    un symlink) es el modo normal;
  - como root, el modo test aborta;
  - sin centinela ejecutable en $LOCKD_SYSROOT/.stubs/bin aborta: es como se
    manifiesta un /tmp montado noexec;
  - el PATH queda solo en .stubs/bin: un comando real que el árbol no provee
    no existe, y el intento queda anotado en .stubs/faltantes;
  - sin bus del sistema ni terminal; BACKUP_BASE cae dentro del árbol; avisa
    por stderr; check_root no exige root; find_sysctl no usa rutas absolutas.
Los del modo activo corren sin root; como root se saltean (en CI los cubre la
pasada sin privilegios).
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT   = Path(__file__).resolve().parent.parent
COMMON = ROOT / "modules" / "_common.sh"
BASE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
ES_ROOT = os.geteuid() == 0
solo_sin_root = pytest.mark.skipif(ES_ROOT, reason="el modo test no corre como root")


def _source(script: str, sysroot) -> subprocess.CompletedProcess:
    env = dict(BASE_ENV)
    if sysroot is not None:
        env["LOCKD_SYSROOT"] = str(sysroot)
    return subprocess.run(
        ["bash", "-c", f'source "{COMMON}"\n{script}'],
        capture_output=True, text=True, timeout=30, env=env,
    )


def _arbol(base: Path, centinela="#!/bin/sh\necho ok\n", modo: int = 0o755) -> Path:
    """Árbol mínimo de modo test: solo el centinela en .stubs/bin."""
    bin_ = base / ".stubs" / "bin"
    bin_.mkdir(parents=True)
    if centinela is not None:
        c = bin_ / "lockd-stubs"
        c.write_text(centinela)
        c.chmod(modo)
    return base


class TestResguardos:
    def test_raiz_inexistente_aborta(self, tmp_path):
        r = _source("echo SIGUIO", tmp_path / "no-existe")
        assert r.returncode == 1
        assert "SIGUIO" not in r.stdout

    @pytest.mark.parametrize("raiz", ["/", "//", "/."])
    def test_raiz_que_resuelve_a_barra_es_modo_normal(self, raiz):
        r = _source('echo "[$SYSROOT] $BACKUP_BASE"', raiz)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "[] /var/lib/lockd/backups"
        assert "MODO TEST" not in r.stderr

    def test_symlink_a_barra_es_modo_normal(self, tmp_path):
        link = tmp_path / "raiz"
        link.symlink_to("/")
        r = _source('echo "[$SYSROOT]"', link)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "[]"

    @pytest.mark.skipif(not ES_ROOT, reason="solo se puede probar como root")
    def test_como_root_aborta(self, tmp_path):
        r = _source("echo SIGUIO", _arbol(tmp_path))
        assert r.returncode == 1
        assert "SIGUIO" not in r.stdout
        assert "no corre como root" in r.stderr

    @solo_sin_root
    def test_sin_centinela_aborta(self, tmp_path):
        r = _source("echo SIGUIO", _arbol(tmp_path, centinela=None))
        assert r.returncode == 1
        assert "SIGUIO" not in r.stdout
        assert "no se pueden ejecutar" in r.stderr

    @solo_sin_root
    def test_centinela_no_ejecutable_aborta(self, tmp_path):
        # el mismo efecto que un /tmp montado noexec: el archivo está pero no corre
        r = _source("echo SIGUIO", _arbol(tmp_path, modo=0o644))
        assert r.returncode == 1
        assert "SIGUIO" not in r.stdout

    @solo_sin_root
    def test_centinela_que_no_responde_aborta(self, tmp_path):
        r = _source("echo SIGUIO", _arbol(tmp_path, centinela="#!/bin/sh\nexit 0\n"))
        assert r.returncode == 1
        assert "SIGUIO" not in r.stdout


@solo_sin_root
class TestModoActivo:
    def test_path_cerrado_backups_adentro_y_aviso(self, tmp_path):
        raiz = _arbol(tmp_path).resolve()
        r = _source('echo "$SYSROOT"; echo "$PATH"; echo "$BACKUP_BASE"', raiz)
        assert r.returncode == 0, r.stderr
        sysroot, path, backups = r.stdout.splitlines()
        assert sysroot == str(raiz)
        assert path == str(raiz / ".stubs" / "bin")
        assert backups == str(raiz / "var" / "lib" / "lockd" / "backups")
        assert "MODO TEST" in r.stderr

    def test_comando_real_sin_stub_no_existe_y_queda_anotado(self, tmp_path):
        # mount existe en el sistema, pero el árbol no lo provee
        raiz = _arbol(tmp_path)
        r = _source("mount --version 2>/dev/null || echo rc=$?", raiz)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "rc=127"
        assert (raiz / ".stubs" / "faltantes").read_text().split() == ["mount"]

    def test_sin_bus_del_sistema_ni_terminal(self, tmp_path):
        raiz = _arbol(tmp_path).resolve()
        r = _source('echo "$DBUS_SYSTEM_BUS_ADDRESS"\n'
                    '[ /dev/stdin -ef /dev/null ] && echo stdin-nulo', raiz)
        assert r.returncode == 0, r.stderr
        assert r.stdout.splitlines() == [f"unix:path={raiz}/.stubs/sin-bus", "stdin-nulo"]

    def test_check_root_no_exige_root(self, tmp_path):
        r = _source("check_root; echo PASO", _arbol(tmp_path))
        assert r.returncode == 0, r.stderr
        assert "PASO" in r.stdout

    def test_find_sysctl_no_usa_rutas_absolutas(self, tmp_path):
        # aunque exista /sbin/sysctl, en modo test solo cuenta el PATH cerrado
        r = _source('echo "[$SYSCTL]"', _arbol(tmp_path))
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "[]"


@solo_sin_root
class TestModoNormal:
    def test_sigue_exigiendo_root(self):
        r = _source("check_root; echo PASO", None)
        assert r.returncode == 1
        assert "PASO" not in r.stdout
