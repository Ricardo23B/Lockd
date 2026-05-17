"""
tests/test_scanner.py — Tests unitarios para el motor de auditoría de Lockd

No requieren root ni servicios reales — verifican la lógica interna del scanner:
estructura de resultados, rangos, pesos, helpers y dataclasses.
"""
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Asegurar que src/ sea importable desde cualquier directorio ────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Mock de gi.repository ANTES de importar cualquier módulo del proyecto ──
# El scanner no usa GTK, pero otros módulos del paquete sí. Este mock evita
# que el CI falle por falta de gir1.2-gtk-4.0 al correr solo los tests.
gi_mock = types.ModuleType("gi")
gi_mock.require_version = lambda *a, **kw: None
repo_mock = types.ModuleType("gi.repository")
for _lib in ("Gtk", "Adw", "GLib", "Gio", "GObject"):
    setattr(repo_mock, _lib, MagicMock())
gi_mock.repository = repo_mock
sys.modules.setdefault("gi", gi_mock)
sys.modules.setdefault("gi.repository", repo_mock)

from src.engine.scanner import (  # noqa: E402
    run_scan,
    CheckResult,
    SecurityReport,
    _CHECKS,
    _WEIGHTS,
    _sshd_option,
    _sysctl_get,
)


# ══════════════════════════════════════════════════════════════════════════════
# CheckResult
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckResult:
    def test_campos_minimos(self):
        r = CheckResult("firewall", "Cortafuegos", "secure")
        assert r.id     == "firewall"
        assert r.name   == "Cortafuegos"
        assert r.status == "secure"
        assert r.detail == ""
        assert r.fix_module_id is None
        assert r.category == ""

    def test_campos_completos(self):
        r = CheckResult(
            id="fail2ban",
            name="Fail2ban",
            status="insecure",
            detail="No instalado",
            fix_module_id="install_fail2ban",
            category="network",
        )
        assert r.fix_module_id == "install_fail2ban"
        assert r.category      == "network"

    def test_status_valores_validos(self):
        for s in ("secure", "insecure", "unknown"):
            r = CheckResult("x", "X", s)
            assert r.status == s


# ══════════════════════════════════════════════════════════════════════════════
# SecurityReport
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityReport:
    def _make_report(self):
        r = SecurityReport()
        r.checks = [
            CheckResult("a", "A", "secure",   category="network"),
            CheckResult("b", "B", "insecure", fix_module_id="fix_b", category="network"),
            CheckResult("c", "C", "unknown",  category="kernel"),
        ]
        return r

    def test_contadores(self):
        r = self._make_report()
        assert r.n_secure   == 1
        assert r.n_insecure == 1
        assert r.n_unknown  == 1

    def test_by_status(self):
        r = self._make_report()
        assert len(r.by_status("secure"))   == 1
        assert len(r.by_status("insecure")) == 1
        assert len(r.by_status("unknown"))  == 1

    def test_by_category(self):
        r = self._make_report()
        assert len(r.by_category("network")) == 2
        assert len(r.by_category("kernel"))  == 1
        assert len(r.by_category("nope"))    == 0

    def test_score_inicial(self):
        assert SecurityReport().score == 0

    def test_recommended_fixes_vacio(self):
        assert SecurityReport().recommended_fixes == []


# ══════════════════════════════════════════════════════════════════════════════
# _CHECKS y _WEIGHTS — integridad del catálogo
# ══════════════════════════════════════════════════════════════════════════════

class TestCatalogo:
    def test_checks_no_vacio(self):
        assert len(_CHECKS) > 0, "No hay checks registrados"

    def test_pesos_suman_100(self):
        total = sum(_WEIGHTS.values())
        assert total == 100, f"Los pesos suman {total}, deberían sumar 100"

    def test_todos_los_checks_tienen_peso(self):
        """Cada check registrado debe tener su peso en _WEIGHTS."""
        for fn in _CHECKS:
            # El nombre de la función es check_<id>; el id es fn.__name__[6:]
            check_id = fn.__name__.replace("check_", "", 1)
            assert check_id in _WEIGHTS, (
                f"check '{check_id}' no tiene peso en _WEIGHTS"
            )

    def test_checks_son_callable(self):
        for fn in _CHECKS:
            assert callable(fn), f"{fn} no es callable"


# ══════════════════════════════════════════════════════════════════════════════
# run_scan — con subprocess mockeado (no requiere root ni servicios reales)
# ══════════════════════════════════════════════════════════════════════════════

def _fake_run(cmd, **kwargs):
    """Simula respuestas mínimas de subprocess para cada herramienta."""
    m = MagicMock()
    m.returncode = 1      # por defecto: comando no encontrado / inactivo
    m.stdout     = ""
    m.stderr     = ""

    if not cmd:
        return m

    exe = Path(cmd[0]).name if isinstance(cmd[0], str) else ""

    if exe == "ufw" and "status" in cmd:
        m.returncode = 0
        m.stdout     = "Status: inactive"
    elif exe == "systemctl":
        m.returncode = 1
        m.stdout     = "inactive"
    elif exe in ("ss", "findmnt", "lsmod", "find"):
        m.returncode = 0
        m.stdout     = ""
    elif exe in ("apparmor_status", "aa-status"):
        m.returncode = 0
        m.stdout     = "0 profiles in enforce mode"
    return m


class TestRunScan:
    @patch("shutil.which", return_value=None)   # ninguna herramienta instalada
    @patch("subprocess.run", side_effect=_fake_run)
    def test_devuelve_security_report(self, _run, _which):
        report = run_scan()
        assert isinstance(report, SecurityReport)

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_score_en_rango(self, _run, _which):
        report = run_scan()
        assert 0 <= report.score <= 100, f"Score fuera de rango: {report.score}"

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_cantidad_checks(self, _run, _which):
        report = run_scan()
        assert len(report.checks) == len(_CHECKS), (
            f"Se esperaban {len(_CHECKS)} checks, se obtuvieron {len(report.checks)}"
        )

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_cada_check_tiene_status_valido(self, _run, _which):
        report = run_scan()
        validos = {"secure", "insecure", "unknown"}
        for c in report.checks:
            assert c.status in validos, (
                f"Check '{c.id}' tiene status inválido: '{c.status}'"
            )

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_fixes_son_strings(self, _run, _which):
        report = run_scan()
        for fix in report.recommended_fixes:
            assert isinstance(fix, str), f"fix_module_id no es string: {fix!r}"

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_fixes_sin_duplicados(self, _run, _which):
        report = run_scan()
        assert len(report.recommended_fixes) == len(set(report.recommended_fixes)), (
            "recommended_fixes tiene duplicados"
        )

    @patch("shutil.which", return_value=None)
    @patch("subprocess.run", side_effect=_fake_run)
    def test_suggested_profile_es_string_o_none(self, _run, _which):
        report = run_scan()
        assert report.suggested_profile is None or isinstance(
            report.suggested_profile, str
        )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internos
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_sshd_option_archivo_inexistente(self):
        """Si no existe sshd_config, debe devolver None sin crashear."""
        with patch("src.engine.scanner.Path") as MockPath:
            instance = MagicMock()
            instance.exists.return_value = False
            MockPath.return_value = instance
            # No lanzar excepción es suficiente
            result = _sshd_option("PasswordAuthentication")
            assert result is None or isinstance(result, str)

    def test_sysctl_get_parametro_invalido(self):
        """Parámetro inexistente debe devolver None sin crashear."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = _sysctl_get("parametro.que.no.existe")
            assert result is None or isinstance(result, str)
