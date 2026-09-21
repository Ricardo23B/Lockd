"""
tests/test_state_reconciliation.py — El estado de Lockd sale del sistema real

Contrato del frente "checks conectados":
  - verify(): exit 0 → enabled, 1 → disabled, 2/raro/timeout/ausente → unknown.
  - refresh_states(): un check determinante actualiza state.json; un unknown
    conserva lo registrado (no se inventa).
  - Controller verifica al arrancar (verify_on_init): un state.json que
    miente se corrige solo.
  - _verified(): si un script termina OK pero el check contradice el
    resultado, el estado pasa a 'error' — scripts que mienten quedan visibles.
  - Contrato global: los 16 check scripts declarados existen, tienen sintaxis
    válida y devuelven 0/1/2 en menos de 10s sin privilegios... y sin efectos.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockd.app.controller import Controller            # noqa: E402
from lockd.engine.executor import ExecResult            # noqa: E402

MODULES_DIR = ROOT / "modules"


# ── Catálogo falso con checks de comportamiento conocido ────────────────────
def _fake_catalog(tmp_path, checks: dict) -> Path:
    """
    checks: {module_id: rc}  — crea un catálogo mínimo donde cada módulo
    tiene enable/disable triviales y un check.sh que sale con `rc`.
    """
    mdir = tmp_path / "modules"
    entries = []
    for mid, rc in checks.items():
        d = mdir / mid
        d.mkdir(parents=True)
        (d / "enable.sh").write_text("#!/bin/bash\nexit 0\n")
        (d / "disable.sh").write_text("#!/bin/bash\nexit 0\n")
        (d / "check.sh").write_text(f"#!/bin/bash\nexit {rc}\n")
        entries.append(
            f"  - id: {mid}\n"
            f"    name: \"{mid}\"\n"
            f"    description: \"t\"\n"
            f"    category: hardening\n"
            f"    enable_script: \"{mid}/enable.sh\"\n"
            f"    disable_script: \"{mid}/disable.sh\"\n"
            f"    check_script: \"{mid}/check.sh\"\n"
        )
    (mdir / "modules.yaml").write_text("modules:\n" + "".join(entries))
    return mdir


def _ctrl(tmp_path, checks, verify_on_init=False):
    return Controller(
        modules_dir=_fake_catalog(tmp_path, checks),
        profiles_dir=tmp_path,            # sin perfiles: irrelevante acá
        state_file=tmp_path / "state.json",
        dry_run=False,
        verify_on_init=verify_on_init,
    )


class TestVerify:
    def test_mapeo_de_exit_codes(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_on": 0, "mod_off": 1, "mod_dunno": 2, "mod_raro": 7})
        assert c.verify("mod_on") == "enabled"
        assert c.verify("mod_off") == "disabled"
        assert c.verify("mod_dunno") == "unknown"
        assert c.verify("mod_raro") == "unknown"

    def test_modulo_sin_check_es_unknown(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_x": 0})
        (tmp_path / "modules" / "mod_x" / "check.sh").unlink()
        assert c.verify("mod_x") == "unknown"


class TestRefreshStates:
    def test_check_determinante_corrige_estado_que_miente(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_a": 0, "mod_b": 1})
        c.state.set("mod_a", "disabled")   # miente: el sistema dice enabled
        c.state.set("mod_b", "enabled")    # miente: el sistema dice disabled
        eff = c.refresh_states()
        assert eff == {"mod_a": "enabled", "mod_b": "disabled"}
        assert c.state.get("mod_a") == "enabled"
        assert c.state.get("mod_b") == "disabled"

    def test_unknown_conserva_lo_registrado(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_a": 2})
        c.state.set("mod_a", "enabled")
        eff = c.refresh_states()
        assert eff["mod_a"] == "enabled", "exit 2 no debe pisar el estado registrado"

    def test_controller_reconcilia_al_arrancar(self, tmp_path):
        state_file = tmp_path / "state.json"
        # primera instancia: estado mentiroso persistido
        c1 = _ctrl(tmp_path, {"mod_a": 0})
        c1.state.set("mod_a", "disabled")
        # segunda instancia sobre el MISMO state.json, con verificación inicial
        c2 = Controller(
            modules_dir=tmp_path / "modules",
            profiles_dir=tmp_path,
            state_file=state_file,
            verify_on_init=True,
        )
        assert c2.state.get("mod_a") == "enabled"


class TestPostOpVerification:
    def _result(self, mid, action="enable", ok=True, dry=False):
        return ExecResult(ok=ok, module_id=mid, action=action,
                          stdout="", stderr="", rc=0, dry_run=dry)

    def test_script_que_miente_marca_error(self, tmp_path):
        # check dice disabled (1) aunque el "enable" reportó éxito
        c = _ctrl(tmp_path, {"mod_a": 1})
        c.state.set("mod_a", "enabled")    # lo que el executor habría grabado
        r = c._verified(self._result("mod_a", action="enable"))
        assert r.ok                         # el resultado del script no se altera
        assert c.state.get("mod_a") == "error"

    def test_exito_confirmado_no_toca_estado(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_a": 0})
        c.state.set("mod_a", "enabled")
        c._verified(self._result("mod_a", action="enable"))
        assert c.state.get("mod_a") == "enabled"

    def test_check_unknown_confia_en_el_rc(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_a": 2})
        c.state.set("mod_a", "enabled")
        c._verified(self._result("mod_a", action="enable"))
        assert c.state.get("mod_a") == "enabled"

    def test_dry_run_y_fallos_no_se_verifican(self, tmp_path):
        c = _ctrl(tmp_path, {"mod_a": 1})
        c.state.set("mod_a", "enabled")
        c._verified(self._result("mod_a", dry=True))
        c._verified(self._result("mod_a", ok=False))
        assert c.state.get("mod_a") == "enabled"


# ── Contrato global de los 16 checks reales ─────────────────────────────────
def _declared_checks():
    data = yaml.safe_load((MODULES_DIR / "modules.yaml").read_text())
    return [(m["id"], MODULES_DIR / m["check_script"])
            for m in data["modules"] if m.get("check_script")]


CHECKS = _declared_checks()


@pytest.mark.parametrize("mid,script", CHECKS, ids=[m for m, _ in CHECKS])
def test_contrato_de_check_real(mid, script, tmp_path):
    assert script.exists(), f"check declarado pero ausente: {script}"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, \
        f"sintaxis inválida: {script}"

    marker = tmp_path / "marker"
    marker.touch()
    r = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, timeout=10,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
    )
    assert r.returncode in (0, 1, 2), (
        f"[{mid}] el check devolvió rc={r.returncode}; el contrato es "
        f"0=activo, 1=inactivo, 2=no determinable\nstderr: {r.stderr}"
    )
    # un check JAMÁS modifica el sistema
    changed = subprocess.run(
        ["find", "/etc", "/var/lib/lockd", "-newer", str(marker), "-type", "f"],
        capture_output=True, text=True,
    ).stdout.strip()
    assert not changed, f"[{mid}] el check modificó el sistema:\n{changed}"
