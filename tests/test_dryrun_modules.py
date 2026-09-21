"""
tests/test_dryrun_modules.py — Integración: el dry-run de cada módulo es inofensivo

Para CADA script enable/disable declarado en modules.yaml:
  1. Ejecutado con `--dry-run` como argumento (el canal que usa el Executor
     a través de pkexec) debe terminar con rc=0.
  2. No debe crear ni modificar NADA en los directorios del sistema que los
     módulos tocan (/etc/ssh, /etc/systemd, /etc/sysctl.d, /var/lib/lockd, ...).

Requiere root porque los scripts llaman check_root antes del guard de dry-run.
En CI (contenedores root) corre siempre; en local sin root se omite.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    yaml = None

ROOT        = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"

# Directorios que los módulos modifican en ejecución real.
# Si un dry-run escribe en cualquiera de estos, el test falla.
WATCHED_DIRS = [
    "/etc/ssh",
    "/etc/systemd/system",
    "/etc/sysctl.d",
    "/etc/modprobe.d",
    "/etc/fail2ban",
    "/etc/apt/apt.conf.d",
    "/etc/security",
    "/var/lib/lockd",
    "/var/log/lockd",
    "/var/quarantine",
]

requires_root = pytest.mark.skipif(
    os.geteuid() != 0,
    reason="los scripts llaman check_root; este test corre como root (CI)",
)


def _action_scripts():
    """Lee modules.yaml y devuelve [(module_id, action, Path)] de enable/disable."""
    if yaml is None:
        return []
    data = yaml.safe_load((MODULES_DIR / "modules.yaml").read_text(encoding="utf-8"))
    out = []
    for entry in data.get("modules", []):
        for key, action in (("enable_script", "enable"), ("disable_script", "disable")):
            rel = entry.get(key)
            if rel:
                out.append((entry["id"], action, MODULES_DIR / rel))
    return out


SCRIPTS = _action_scripts()


def _fs_changes_since(marker: Path) -> list[str]:
    """Archivos creados/modificados después del marker en los dirs vigilados."""
    changed = []
    for d in WATCHED_DIRS:
        if not os.path.isdir(d):
            continue
        r = subprocess.run(
            ["find", d, "-newer", str(marker), "-type", "f"],
            capture_output=True, text=True,
        )
        changed.extend(line for line in r.stdout.splitlines() if line)
    return changed


@requires_root
@pytest.mark.skipif(not SCRIPTS, reason="PyYAML no disponible o modules.yaml vacío")
@pytest.mark.parametrize(
    "module_id,action,script",
    SCRIPTS,
    ids=[f"{m}:{a}" for m, a, _ in SCRIPTS],
)
def test_dry_run_es_inofensivo(module_id, action, script, tmp_path):
    assert script.exists(), f"Script declarado en modules.yaml no existe: {script}"

    marker = tmp_path / "marker"
    marker.touch()
    # granularidad de mtime: asegurar que el marker quede estrictamente antes
    time.sleep(0.05)

    # Entorno limpio y SIN la variable DRY_RUN: queremos probar exactamente
    # lo que llega al script a través de pkexec (solo el argumento).
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root"}

    proc = subprocess.run(
        ["bash", str(script), "--dry-run"],
        capture_output=True, text=True, timeout=60, env=env,
    )

    assert proc.returncode == 0, (
        f"[{module_id}/{action}] dry-run salió con rc={proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "[DRY-RUN]" in (proc.stdout + proc.stderr), (
        f"[{module_id}/{action}] no anunció modo simulación — "
        f"¿falta el guard de DRY_RUN antes de los efectos?"
    )

    changed = _fs_changes_since(marker)
    assert not changed, (
        f"[{module_id}/{action}] el dry-run MODIFICÓ el filesystem:\n"
        + "\n".join(changed)
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
