"""
tests/test_critical_modules.py — Contratos de los módulos con riesgo de
lockout o de rollback incompleto (enable_firewall, hardened_ssh_config,
kernel_sysctl_hardening), de la línea base de _common.sh y del resolvedor de
precedencia de sshd del scanner.

Todo corre sobre árboles temporales (variables LOCKD_* de test): no toca la
configuración real del sistema y no requiere root.
"""
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lockd.engine import scanner
from lockd.engine.scanner import _sshd_option

ROOT        = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"
COMMON      = MODULES_DIR / "_common.sh"
SSH_CHECK   = MODULES_DIR / "hardened_ssh_config" / "check.sh"
SYS_VERIFY  = MODULES_DIR / "kernel_sysctl_hardening" / "verify.sh"
BASE_ENV    = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}

not_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="root lee archivos sin permiso de lectura"
)


def _code(path: Path) -> str:
    """Contenido del script sin líneas de comentario."""
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _bash(script: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30,
        env={**BASE_ENV, **env},
    )


# ══════════════════════════════════════════════════════════════════════════════
# _common.sh — línea base por ciclo
# ══════════════════════════════════════════════════════════════════════════════

class TestBaseline:
    def test_restaura_estado_previo_y_la_reaplicacion_no_lo_pisa(self, tmp_path):
        bk, prev, nuevo = tmp_path / "bk", tmp_path / "a.conf", tmp_path / "b.conf"
        prev.write_text("original\n")
        r = _bash(f"""
            set -euo pipefail
            source "{COMMON}"
            baseline_begin mod "{prev}" "{nuevo}"
            echo lockd-1 > "{prev}"; echo creado-por-lockd > "{nuevo}"
            baseline_begin mod "{prev}" "{nuevo}"     # reaplicación
            echo lockd-2 > "{prev}"
            baseline_restore mod "{prev}" "{nuevo}"
            baseline_end mod
        """, LOCKD_BACKUP_BASE=str(bk))
        assert r.returncode == 0, r.stderr
        assert prev.read_text() == "original\n", "debe volver al estado PREVIO a Lockd"
        assert not nuevo.exists(), "un archivo que no existía antes debe eliminarse"
        assert not (bk / "mod" / ".baseline").exists(), "el ciclo debe quedar cerrado"

    def test_dry_run_no_escribe_nada(self, tmp_path):
        bk, f = tmp_path / "bk", tmp_path / "a.conf"
        f.write_text("x\n")
        r = _bash(f"""
            set -euo pipefail
            source "{COMMON}"
            baseline_begin mod "{f}"
            echo contenido | write_file "{tmp_path}/nuevo.conf"
        """, LOCKD_BACKUP_BASE=str(bk), DRY_RUN="1")
        assert r.returncode == 0, r.stderr
        assert not bk.exists()
        assert not (tmp_path / "nuevo.conf").exists()
        assert "contenido" in r.stdout, "el dry-run debe mostrar lo que escribiría"

    def test_write_file_es_atomico_y_aplica_modo(self, tmp_path):
        dest = tmp_path / "x.conf"
        r = _bash(f'source "{COMMON}"; printf "a\\nb\\n" | write_file "{dest}" 0600')
        assert r.returncode == 0, r.stderr
        assert dest.read_text() == "a\nb\n"
        assert oct(dest.stat().st_mode & 0o777) == "0o600"
        assert list(tmp_path.glob("x.conf.lockd.*")) == [], "no debe dejar temporales"


# ══════════════════════════════════════════════════════════════════════════════
# enable_firewall — regresiones de lockout
# ══════════════════════════════════════════════════════════════════════════════

class TestFirewall:
    def test_no_resetea_reglas_del_usuario(self):
        code = _code(MODULES_DIR / "enable_firewall" / "enable.sh")
        assert "ufw --force reset" not in code and "ufw reset" not in code

    def test_orden_sin_ventana_de_corte(self):
        code = _code(MODULES_DIR / "enable_firewall" / "enable.sh")
        i_limit  = code.index("ufw limit")
        i_deny   = code.index("ufw default deny incoming")
        i_enable = code.index("ufw --force enable")
        assert i_limit < i_deny < i_enable, \
            "primero las reglas SSH, después la política, al final la activación"

    def test_no_usa_el_puerto_de_etc_services(self):
        code = _code(MODULES_DIR / "enable_firewall" / "enable.sh")
        assert not re.search(r"ufw\s+limit\s+ssh\b", code), \
            "'ufw limit ssh' abre el 22 aunque sshd escuche en otro puerto"


# ══════════════════════════════════════════════════════════════════════════════
# hardened_ssh_config — precedencia de sshd
# ══════════════════════════════════════════════════════════════════════════════

LOCKD_DROPIN = (
    "PasswordAuthentication no\n"
    "KbdInteractiveAuthentication no\n"
    "PermitRootLogin no\n"
    "KexAlgorithms -diffie-hellman-*,ecdh-sha2-*\n"
)


def _sshd_tree(tmp_path, *, before_include="", dropins=None,
               lockd_name="00-lockd-hardening.conf", include=True):
    d = tmp_path / "sshd_config.d"
    d.mkdir()
    lines = [before_include] if before_include else []
    if include:
        lines.append(f"Include {d}/*.conf")
    lines.append("PasswordAuthentication yes")   # después del Include: no pesa
    main = tmp_path / "sshd_config"
    main.write_text("\n".join(lines) + "\n")
    for name, body in (dropins or {}).items():
        (d / name).write_text(body)
    if lockd_name:
        (d / lockd_name).write_text(LOCKD_DROPIN)
    return main, d


def _ssh_check(main: Path, d: Path) -> int:
    r = subprocess.run(
        ["bash", str(SSH_CHECK)], capture_output=True, text=True, timeout=10,
        env={**BASE_ENV,
             "LOCKD_SSHD_CONFIG": str(main),
             "LOCKD_SSHD_DROPIN": str(d / "00-lockd-hardening.conf"),
             "LOCKD_SSHD_DROPIN_LEGACY": str(d / "99-lockd-hardening.conf")},
    )
    return r.returncode


class TestSshCheck:
    def test_sin_dropin_es_inactivo(self, tmp_path):
        assert _ssh_check(*_sshd_tree(tmp_path, lockd_name=None)) == 1

    def test_dropin_00_gana_a_cloud_init(self, tmp_path):
        tree = _sshd_tree(tmp_path, dropins={"50-cloud-init.conf": "PasswordAuthentication yes\n"})
        assert _ssh_check(*tree) == 0

    def test_dropin_99_legacy_queda_pisado_por_cloud_init(self, tmp_path):
        """El bug original: el 99- existía, el check viejo decía 'activo', sshd no lo usaba."""
        tree = _sshd_tree(tmp_path, lockd_name="99-lockd-hardening.conf",
                          dropins={"50-cloud-init.conf": "PasswordAuthentication yes\n"})
        assert _ssh_check(*tree) == 1

    def test_opcion_antes_del_include_gana(self, tmp_path):
        assert _ssh_check(*_sshd_tree(tmp_path, before_include="PermitRootLogin yes")) == 1

    def test_sin_include_el_dropin_no_rige(self, tmp_path):
        assert _ssh_check(*_sshd_tree(tmp_path, include=False)) == 1

    def test_sintaxis_con_igual_y_alias_historico(self, tmp_path):
        tree = _sshd_tree(tmp_path, dropins={"00-aaa.conf": "ChallengeResponseAuthentication=yes\n"})
        assert _ssh_check(*tree) == 1

    def test_bloque_match_no_define_el_valor_global(self, tmp_path):
        tree = _sshd_tree(tmp_path, dropins={
            "00-aaa.conf": "Match User deploy\n    PasswordAuthentication yes\n"})
        assert _ssh_check(*tree) == 0

    @not_root
    def test_ilegible_antes_de_resolver_es_no_determinable(self, tmp_path):
        main, d = _sshd_tree(tmp_path, dropins={"00-aaa.conf": "X11Forwarding no\n"})
        (d / "00-aaa.conf").chmod(0)
        assert _ssh_check(main, d) == 2

    def test_enable_usa_prefijo_00_y_kex_sustractivo(self):
        src = (MODULES_DIR / "hardened_ssh_config" / "enable.sh").read_text(encoding="utf-8")
        assert 'DROP_IN="${DROP_DIR}/00-' in src
        assert re.search(r"^KexAlgorithms -", src, re.M), \
            "una lista cerrada de KEX elimina los híbridos post-cuánticos"


class TestScannerSshd:
    def test_primer_valor_gana_con_include_en_posicion(self, tmp_path):
        main, _ = _sshd_tree(tmp_path, dropins={"50-cloud-init.conf": "PasswordAuthentication yes\n"})
        assert _sshd_option("PasswordAuthentication", main) == "no"

    def test_opcion_antes_del_include(self, tmp_path):
        main, _ = _sshd_tree(tmp_path, before_include="PermitRootLogin yes")
        assert _sshd_option("PermitRootLogin", main) == "yes"

    def test_alias_y_match(self, tmp_path):
        main, _ = _sshd_tree(tmp_path, lockd_name=None, dropins={
            "00-aaa.conf": "Match User x\n  KbdInteractiveAuthentication yes\n",
            "10-bbb.conf": "ChallengeResponseAuthentication no\n"})
        assert _sshd_option("KbdInteractiveAuthentication", main) == "no"

    @not_root
    def test_ilegible_antes_de_resolver_es_none(self, tmp_path):
        main, d = _sshd_tree(tmp_path, dropins={"00-aaa.conf": "X11Forwarding no\n"})
        (d / "00-aaa.conf").chmod(0)
        assert _sshd_option("PasswordAuthentication", main) is None

    def test_without_password_es_alias_seguro(self):
        with patch.object(scanner, "_sshd_installed", return_value=True), \
             patch.object(scanner, "_sshd_option", return_value="without-password"):
            assert scanner.check_ssh_root().status == "secure"


# ══════════════════════════════════════════════════════════════════════════════
# kernel_sysctl_hardening — verify contra valores en ejecución
# ══════════════════════════════════════════════════════════════════════════════

def _fake_proc(tmp_path, values: dict) -> Path:
    proc = tmp_path / "proc_sys"
    for key, val in values.items():
        p = proc / key.replace(".", "/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{val}\n")
    return proc


def _verify(conf: Path, proc: Path) -> int:
    return subprocess.run(
        ["bash", str(SYS_VERIFY)], capture_output=True, text=True, timeout=10,
        env={**BASE_ENV, "LOCKD_SYSCTL_CONF": str(conf), "LOCKD_PROC_SYS": str(proc)},
    ).returncode


class TestSysctlVerify:
    CONF = "net.ipv4.tcp_syncookies = 1\nkernel.dmesg_restrict = 1\nnet.ipv4.ip_forward = 0\n"

    def test_valores_en_ejecucion_coinciden(self, tmp_path):
        conf = tmp_path / "99.conf"
        conf.write_text("# comentario\n" + self.CONF)
        proc = _fake_proc(tmp_path, {"net.ipv4.tcp_syncookies": 1,
                                     "kernel.dmesg_restrict": 1,
                                     "net.ipv4.ip_forward": 1})   # Docker lo encendió
        assert _verify(conf, proc) == 0, "ip_forward no debe contar"

    def test_valor_pisado_en_ejecucion_es_inactivo(self, tmp_path):
        conf = tmp_path / "99.conf"
        conf.write_text(self.CONF)
        proc = _fake_proc(tmp_path, {"net.ipv4.tcp_syncookies": 1, "kernel.dmesg_restrict": 0})
        assert _verify(conf, proc) == 1

    def test_sin_conf_es_inactivo(self, tmp_path):
        assert _verify(tmp_path / "no-existe.conf", tmp_path) == 1

    def test_clave_ilegible_es_no_determinable(self, tmp_path):
        conf = tmp_path / "99.conf"
        conf.write_text(self.CONF)
        proc = _fake_proc(tmp_path, {"net.ipv4.tcp_syncookies": 1})
        assert _verify(conf, proc) == 2
