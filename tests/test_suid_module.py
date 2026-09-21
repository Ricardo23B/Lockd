"""
tests/test_suid_module.py — restrict_suid_binaries con lógica de denylist

El contrato de seguridad de este módulo (la versión anterior podía quitarle
el SUID a polkit-agent-helper-1 y romper la autenticación de polkit):

  1. SOLO pierde SUID lo que está en la denylist explícita.
  2. Lo no reconocido se AUDITA en un archivo, sin modificarse.
  3. NEVER_TOUCH es inviolable: aunque la denylist se sabotee para incluir
     binarios de infraestructura (polkit, sudo, dbus...), no se tocan.
  4. disable.sh restaura exactamente lo removido y limpia las listas.
  5. El dry-run no modifica ningún bit.

Corre como root (CI) contra un árbol de binarios falsos en tmp, usando los
overrides LOCKD_SUID_SEARCH_PATHS / LOCKD_BACKUP_BASE — en producción no
existen porque el helper pasa un entorno mínimo.
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT    = Path(__file__).resolve().parent.parent
ENABLE  = ROOT / "modules" / "restrict_suid_binaries" / "enable.sh"
DISABLE = ROOT / "modules" / "restrict_suid_binaries" / "disable.sh"

requires_root = pytest.mark.skipif(
    os.geteuid() != 0, reason="los scripts exigen root (CI corre como root)"
)

# nombre en denylist, nombre de infraestructura, nombre desconocido
DENY_BIN  = "chfn"
INFRA_BIN = "polkit-agent-helper-1"
OTHER_BIN = "custom_corporate_tool"


def _make_fake_bins(base: Path) -> dict:
    bins = {}
    bindir = base / "fakebin"
    bindir.mkdir()
    for name in (DENY_BIN, INFRA_BIN, OTHER_BIN, "sudo", "fusermount3"):
        p = bindir / name
        p.write_text("#!/bin/bash\nexit 0\n")
        p.chmod(0o4755)  # SUID activo
        bins[name] = p
    return bins


def _has_suid(p: Path) -> bool:
    return bool(p.stat().st_mode & stat.S_ISUID)


def _env(tmp_path, **extra):
    return {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LOCKD_SUID_SEARCH_PATHS": str(tmp_path / "fakebin"),
        "LOCKD_BACKUP_BASE": str(tmp_path / "backups"),
        **extra,
    }


def _run(script, env):
    return subprocess.run(["bash", str(script)], env=env,
                          capture_output=True, text=True, timeout=60)


@requires_root
class TestEnableDenylist:
    def test_solo_denylist_pierde_suid(self, tmp_path):
        bins = _make_fake_bins(tmp_path)
        r = _run(ENABLE, _env(tmp_path))
        assert r.returncode == 0, r.stderr

        assert not _has_suid(bins[DENY_BIN]), "chfn está en la denylist: debe perder SUID"
        for name in (INFRA_BIN, OTHER_BIN, "sudo", "fusermount3"):
            assert _has_suid(bins[name]), f"{name} NO debía ser tocado"

    def test_lo_desconocido_se_audita_sin_tocar(self, tmp_path):
        bins = _make_fake_bins(tmp_path)
        _run(ENABLE, _env(tmp_path))
        audit = (tmp_path / "backups" / "restrict_suid_binaries"
                 / "suid_audit.txt").read_text()
        assert str(bins[OTHER_BIN]) in audit
        assert str(bins[DENY_BIN]) not in audit, \
            "lo removido va a suid_removed.txt, no a la auditoría"

    def test_never_touch_es_inviolable_ante_denylist_saboteada(self, tmp_path):
        """Aunque la denylist incluya binarios de infraestructura, la red
        NEVER_TOUCH (hardcodeada, sin override) los protege."""
        bins = _make_fake_bins(tmp_path)
        env = _env(tmp_path, LOCKD_SUID_DENYLIST=(
            f"{INFRA_BIN} sudo fusermount3 {DENY_BIN}"
        ))
        r = _run(ENABLE, env)
        assert r.returncode == 0, r.stderr
        for name in (INFRA_BIN, "sudo", "fusermount3"):
            assert _has_suid(bins[name]), \
                f"NEVER_TOUCH violado: {name} perdió SUID"
        assert not _has_suid(bins[DENY_BIN]), \
            "chfn no es infraestructura: la denylist sí aplica"

    def test_dry_run_no_toca_ningun_bit(self, tmp_path):
        bins = _make_fake_bins(tmp_path)
        r = subprocess.run(["bash", str(ENABLE), "--dry-run"],
                           env=_env(tmp_path), capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        assert "[DRY-RUN]" in r.stdout + r.stderr
        assert all(_has_suid(p) for p in bins.values())
        assert not (tmp_path / "backups").exists(), \
            "dry-run no debe crear listas ni directorios"


@requires_root
class TestDisableRestore:
    def test_restaura_exactamente_lo_removido(self, tmp_path):
        bins = _make_fake_bins(tmp_path)
        env = _env(tmp_path)
        _run(ENABLE, env)
        assert not _has_suid(bins[DENY_BIN])

        r = _run(DISABLE, env)
        assert r.returncode == 0, r.stderr
        assert _has_suid(bins[DENY_BIN]), "disable debe devolver el SUID removido"

        bdir = tmp_path / "backups" / "restrict_suid_binaries"
        assert not (bdir / "suid_removed.txt").exists()
        assert not (bdir / "suid_audit.txt").exists()

    def test_disable_sin_lista_es_noop_exitoso(self, tmp_path):
        _make_fake_bins(tmp_path)
        r = _run(DISABLE, _env(tmp_path))
        assert r.returncode == 0
        assert "Nada que restaurar" in r.stdout + r.stderr

    def test_binario_desaparecido_no_rompe_restore(self, tmp_path):
        bins = _make_fake_bins(tmp_path)
        env = _env(tmp_path)
        _run(ENABLE, env)
        bins[DENY_BIN].unlink()  # el binario fue desinstalado entre medio
        r = _run(DISABLE, env)
        assert r.returncode == 0, r.stderr
