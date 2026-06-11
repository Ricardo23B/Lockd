"""
tests/test_executor.py — Tests unitarios del Executor

Verifican el contrato crítico del dry-run:
  1. Con dry_run=True el comando incluye el argumento --dry-run.
     (pkexec sanea el entorno del proceso hijo, por lo que la variable
      DRY_RUN no llega al script: el ARGUMENTO es el único canal confiable.)
  2. En dry-run el estado persistente NO se modifica.
  3. En ejecución real exitosa el estado SÍ se actualiza.
  4. Cancelación de pkexec (rc=126) no toca el estado.

No requieren root ni polkit — subprocess.run y pkexec están mockeados.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockd.engine.executor import Executor, CANCEL_CODE  # noqa: E402


def _fake_proc(rc=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode = rc
    p.stdout = stdout
    p.stderr = stderr
    return p


def _make_executor(tmp_path, dry_run):
    """Executor en MODO LEGACY (sin helper), con pkexec mockeado y un script
    ejecutable real en tmp. Se patchea _find_helper para que el test no
    dependa de si la máquina tiene lockd-helper instalado."""
    script = tmp_path / "enable.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    script.chmod(0o755)

    state = MagicMock()
    with patch("lockd.engine.executor.shutil.which", return_value="/usr/bin/pkexec"), \
         patch("lockd.engine.executor._find_helper", return_value=None):
        ex = Executor(state, dry_run=dry_run)
    return ex, state, script


class TestDryRunPropagation:
    def test_dry_run_pasa_flag_como_argumento(self, tmp_path):
        ex, _, script = _make_executor(tmp_path, dry_run=True)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", script, enable=True)

        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "/usr/bin/pkexec"
        assert cmd[1] == str(script)
        assert "--dry-run" in cmd, (
            "El flag --dry-run debe viajar como argumento: pkexec descarta "
            "las variables de entorno del invocante."
        )

    def test_dry_run_tambien_setea_env_redundante(self, tmp_path):
        ex, _, script = _make_executor(tmp_path, dry_run=True)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", script, enable=True)
        assert mock_run.call_args.kwargs["env"].get("DRY_RUN") == "1"

    def test_modo_real_no_pasa_flag(self, tmp_path):
        ex, _, script = _make_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", script, enable=True)
        cmd = mock_run.call_args.args[0]
        assert "--dry-run" not in cmd
        assert mock_run.call_args.kwargs["env"].get("DRY_RUN") is None

    def test_setter_dry_run_afecta_siguiente_ejecucion(self, tmp_path):
        ex, _, script = _make_executor(tmp_path, dry_run=False)
        ex.dry_run = True
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", script, enable=True)
        assert "--dry-run" in mock_run.call_args.args[0]


class TestModoHelper:
    """Con lockd-helper instalado, el comando viaja como (helper, action, id):
    el script lo resuelve el lado privilegiado, no el invocante."""

    def _make_helper_executor(self, tmp_path, dry_run):
        helper = tmp_path / "lockd-helper"
        helper.write_text("#!/usr/bin/env python3\n")
        state = MagicMock()
        with patch("lockd.engine.executor.shutil.which",
                   return_value="/usr/bin/pkexec"), \
             patch("lockd.engine.executor._find_helper", return_value=helper):
            ex = Executor(state, dry_run=dry_run)
        return ex, state, helper

    def test_comando_via_helper(self, tmp_path):
        ex, _, helper = self._make_helper_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", Path("/cualquier/ruta/enable.sh"), enable=True)
        cmd = mock_run.call_args.args[0]
        assert cmd == ["/usr/bin/pkexec", str(helper), "enable", "mod_x"]

    def test_dry_run_via_helper(self, tmp_path):
        ex, state, helper = self._make_helper_executor(tmp_path, dry_run=True)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", Path("/cualquier/ruta/enable.sh"), enable=True)
        cmd = mock_run.call_args.args[0]
        assert cmd == ["/usr/bin/pkexec", str(helper), "enable", "mod_x", "--dry-run"]
        state.set.assert_not_called()

    def test_disable_via_helper(self, tmp_path):
        ex, _, helper = self._make_helper_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()) as mock_run:
            ex.run("mod_x", Path("/cualquier/ruta/disable.sh"), enable=False)
        assert mock_run.call_args.args[0][2] == "disable"

    def test_dry_run_no_modifica_estado(self, tmp_path):
        ex, state, script = _make_executor(tmp_path, dry_run=True)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()):
            r = ex.run("mod_x", script, enable=True)
        assert r.ok and r.dry_run
        state.set.assert_not_called()

    def test_exito_real_marca_enabled(self, tmp_path):
        ex, state, script = _make_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc()):
            r = ex.run("mod_x", script, enable=True)
        assert r.ok and not r.dry_run
        state.set.assert_called_once_with("mod_x", "enabled")

    def test_fallo_real_marca_error(self, tmp_path):
        ex, state, script = _make_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc(rc=1, stderr="boom")):
            r = ex.run("mod_x", script, enable=True)
        assert not r.ok
        state.set.assert_called_once_with("mod_x", "error")

    def test_cancelacion_pkexec_no_toca_estado(self, tmp_path):
        ex, state, script = _make_executor(tmp_path, dry_run=False)
        with patch("lockd.engine.executor.subprocess.run",
                   return_value=_fake_proc(rc=CANCEL_CODE)):
            r = ex.run("mod_x", script, enable=True)
        assert r.cancelled and not r.ok
        state.set.assert_not_called()
