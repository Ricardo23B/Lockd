"""
tests/test_helper.py — Integración del helper privilegiado (lockd-helper)

Verifican el contrato de seguridad y el journal:
  - Ejecuta el script correcto según modules.yaml y propaga su rc.
  - --dry-run llega al script como argumento Y como variable de entorno.
  - RECHAZA directorios de módulos no root-owned o escribibles por otros (rc=66).
  - Rechaza module_id desconocido (65) e inválido (64).
  - Escribe journal JSON-lines con eventos start/result coherentes.
  - backup() registra en el manifiesto de la operación (LOCKD_MANIFEST).

Requieren root (como el CI). Sin root se omiten.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT   = Path(__file__).resolve().parent.parent
HELPER = ROOT / "helper" / "lockd-helper"

requires_root = pytest.mark.skipif(
    os.geteuid() != 0, reason="el helper exige euid 0 (CI corre como root)"
)

MODULES_YAML = """\
modules:
  - id: demo_mod
    name: Demo
    enable_script: "demo_mod/enable.sh"
    disable_script: "demo_mod/disable.sh"
  - id: failing_mod
    name: Falla
    enable_script: "failing_mod/enable.sh"
"""

ENABLE_SH = """\
#!/bin/bash
set -euo pipefail
echo "args: $*"
echo "DRY_RUN=${DRY_RUN:-0} OP=${LOCKD_OP_ID:-none}"
# simular un backup registrado en el manifiesto de la operación
if [ -n "${LOCKD_MANIFEST:-}" ]; then
    printf '%s|demo_mod|/etc/fake.conf|/var/lib/lockd/backups/demo/fake.bak\\n' \
        "${LOCKD_OP_ID:-manual}" >> "$LOCKD_MANIFEST"
fi
exit 0
"""


def _make_catalog(base: Path, world_writable: bool = False) -> Path:
    """Catálogo de módulos de juguete con permisos controlados."""
    mdir = base / "modules"
    (mdir / "demo_mod").mkdir(parents=True)
    (mdir / "failing_mod").mkdir(parents=True)
    (mdir / "modules.yaml").write_text(MODULES_YAML)
    (mdir / "demo_mod" / "enable.sh").write_text(ENABLE_SH)
    (mdir / "demo_mod" / "disable.sh").write_text("#!/bin/bash\nexit 0\n")
    (mdir / "failing_mod" / "enable.sh").write_text("#!/bin/bash\nexit 7\n")
    mode_dir, mode_file = (0o757, 0o646) if world_writable else (0o755, 0o644)
    for p in mdir.rglob("*"):
        p.chmod(mode_file if p.is_file() else mode_dir)
    mdir.chmod(mode_dir)
    os.chown(mdir, 0, 0)
    for p in mdir.rglob("*"):
        os.chown(p, 0, 0)
    return mdir


def _run_helper(*args, env_extra=None):
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        capture_output=True, text=True, timeout=60, env=env,
    )


def _journal_entries():
    jf = Path("/var/lib/lockd/journal.jsonl")
    if not jf.exists():
        return []
    return [json.loads(line) for line in jf.read_text().splitlines() if line]


@requires_root
class TestHelperEjecucion:
    def test_enable_ok_y_journal(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        before = len(_journal_entries())
        r = _run_helper("enable", "demo_mod", "--modules-dir", str(mdir))
        assert r.returncode == 0, r.stderr
        assert "args: --dry-run" not in r.stdout

        entries = _journal_entries()[before:]
        assert len(entries) == 2
        start, result = entries
        assert start["event"] == "start" and start["module"] == "demo_mod"
        assert result["event"] == "result" and result["ok"] is True
        assert result["rc"] == 0 and result["op_id"] == start["op_id"]
        # el script escribió en el manifiesto → el journal lo referencia
        assert result["manifest"] and Path(result["manifest"]).exists()
        content = Path(result["manifest"]).read_text()
        assert start["op_id"] in content and "/etc/fake.conf" in content

    def test_dry_run_llega_por_ambos_canales(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        r = _run_helper("enable", "demo_mod", "--dry-run", "--modules-dir", str(mdir))
        assert r.returncode == 0, r.stderr
        assert "args: --dry-run" in r.stdout      # canal argumento
        assert "DRY_RUN=1" in r.stdout            # canal entorno (helper→script directo)
        last = _journal_entries()[-1]
        assert last["dry_run"] is True

    def test_rc_del_script_se_propaga(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        r = _run_helper("enable", "failing_mod", "--modules-dir", str(mdir))
        assert r.returncode == 7
        last = _journal_entries()[-1]
        assert last["ok"] is False and last["rc"] == 7


@requires_root
class TestHelperSeguridad:
    def test_rechaza_directorio_escribible_por_otros(self, tmp_path):
        mdir = _make_catalog(tmp_path, world_writable=True)
        r = _run_helper("enable", "demo_mod", "--modules-dir", str(mdir))
        assert r.returncode == 66
        assert "insegura" in r.stderr.lower()

    def test_rechaza_directorio_no_root(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        os.chown(mdir, 1000, 1000)
        r = _run_helper("enable", "demo_mod", "--modules-dir", str(mdir))
        assert r.returncode == 66

    def test_rechaza_modulo_desconocido(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        r = _run_helper("enable", "no_existe", "--modules-dir", str(mdir))
        assert r.returncode == 65

    def test_rechaza_id_invalido(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        r = _run_helper("enable", "../../../etc/passwd", "--modules-dir", str(mdir))
        assert r.returncode == 64

    def test_rechaza_script_fuera_del_catalogo(self, tmp_path):
        mdir = _make_catalog(tmp_path)
        evil = tmp_path / "evil.sh"
        evil.write_text("#!/bin/bash\nexit 0\n")
        yaml_path = mdir / "modules.yaml"
        yaml_path.chmod(0o644)
        yaml_path.write_text(
            "modules:\n  - id: escape\n    name: E\n"
            "    enable_script: \"../evil.sh\"\n"
        )
        os.chown(yaml_path, 0, 0)
        r = _run_helper("enable", "escape", "--modules-dir", str(mdir))
        assert r.returncode == 66


@requires_root
class TestBackupGeneracional:
    """backup()/restore() de _common.sh: generaciones, retención y manifiesto."""

    def test_generaciones_retencion_y_restore(self, tmp_path):
        target = tmp_path / "config.conf"
        manifest = tmp_path / "op.manifest"
        script = tmp_path / "driver.sh"
        script.write_text(f"""\
#!/bin/bash
set -euo pipefail
source "{ROOT}/modules/_common.sh"
export BACKUP_BASE="{tmp_path}/backups"
for i in 1 2 3 4 5 6 7; do
    echo "version $i" > "{target}"
    backup "{target}" demo
    sleep 1.05   # granularidad de segundo en el timestamp del nombre
done
echo "ultima" > "{target}"
restore "{target}" demo
""")
        env = {
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LOCKD_BACKUP_KEEP": "3",
            "LOCKD_MANIFEST": str(manifest),
            "LOCKD_OP_ID": "test-op-1",
        }
        r = subprocess.run(["bash", str(script)], capture_output=True,
                           text=True, timeout=60, env=env)
        assert r.returncode == 0, r.stderr

        gens = sorted((tmp_path / "backups" / "demo").glob("config.conf.bak.*"))
        assert len(gens) == 3, f"retención falló: {[g.name for g in gens]}"
        # restore trajo la generación más reciente (version 7)
        assert target.read_text().strip() == "version 7"
        # cada backup quedó en el manifiesto
        lines = manifest.read_text().splitlines()
        assert len(lines) == 7
        assert all(line.startswith("test-op-1|demo|") for line in lines)
