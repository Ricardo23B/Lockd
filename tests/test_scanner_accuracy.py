"""
tests/test_scanner_accuracy.py — El scanner no inventa resultados

Cubre los cinco caminos corregidos en el frente 3:
  1. check_firewall sin root: lee ufw.conf, no `ufw status`; sin datos → unknown.
  2. checks SSH en máquinas sin servidor OpenSSH: "secure" (sin exposición),
     no una recomendación de endurecer algo que no existe.
  3. check_proc_hidepid: fallo de findmnt → unknown, no "insecure".
  4. check_apparmor: aa-status sin privilegios → unknown con detail honesto.
  5. check_suid_binaries: alineado a la denylist del módulo — un Ubuntu
     estándar (fusermount3, polkit-agent-helper-1 con SUID) NO es "insecure".
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockd.engine import scanner  # noqa: E402


def _proc(rc=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode, p.stdout, p.stderr = rc, stdout, stderr
    return p


class TestFirewallSinRoot:
    def test_ufw_conf_enabled_es_secure(self, tmp_path):
        conf = tmp_path / "ufw.conf"
        conf.write_text("# comentario\nENABLED=yes\nLOGLEVEL=low\n")
        with patch.object(scanner.shutil, "which", return_value="/usr/sbin/ufw"), \
             patch.object(scanner, "Path", lambda p: conf if p == "/etc/ufw/ufw.conf" else Path(p)):
            r = scanner.check_firewall()
        assert r.status == "secure"

    def test_ufw_conf_disabled_es_insecure(self, tmp_path):
        conf = tmp_path / "ufw.conf"
        conf.write_text("ENABLED=no\n")
        with patch.object(scanner.shutil, "which", return_value="/usr/sbin/ufw"), \
             patch.object(scanner, "Path", lambda p: conf if p == "/etc/ufw/ufw.conf" else Path(p)):
            r = scanner.check_firewall()
        assert r.status == "insecure"

    def test_sin_datos_es_unknown_no_insecure(self, tmp_path):
        """El bug original: sin root y sin conf legible, el scanner inventaba
        'insecure'. Sin datos, la respuesta honesta es unknown."""
        with patch.object(scanner.shutil, "which", return_value="/usr/sbin/ufw"), \
             patch.object(scanner, "Path",
                          lambda p: (tmp_path / "no-existe") if p == "/etc/ufw/ufw.conf" else Path(p)), \
             patch.object(scanner.subprocess, "run",
                          return_value=_proc(rc=3, stdout="inactive\n")):
            r = scanner.check_firewall()
        assert r.status == "unknown"

    def test_jamas_invoca_ufw_status(self, tmp_path):
        """`ufw status` exige root; el check no debe llamarlo nunca."""
        calls = []

        def spy(cmd, **kw):
            calls.append(cmd)
            return _proc(rc=3)
        with patch.object(scanner.shutil, "which", return_value="/usr/sbin/ufw"), \
             patch.object(scanner, "Path",
                          lambda p: (tmp_path / "no-existe") if p == "/etc/ufw/ufw.conf" else Path(p)), \
             patch.object(scanner.subprocess, "run", side_effect=spy):
            scanner.check_firewall()
        assert all(c[:2] != ["ufw", "status"] for c in calls), calls


class TestSSHSinServidor:
    def test_password_sin_sshd_es_secure(self):
        with patch.object(scanner, "_sshd_installed", return_value=False):
            r = scanner.check_ssh_password()
        assert r.status == "secure"
        assert "no instalado" in r.detail

    def test_root_login_sin_sshd_es_secure(self):
        with patch.object(scanner, "_sshd_installed", return_value=False):
            r = scanner.check_ssh_root()
        assert r.status == "secure"

    def test_con_sshd_sigue_evaluando(self):
        with patch.object(scanner, "_sshd_installed", return_value=True), \
             patch.object(scanner, "_sshd_option", return_value="yes"):
            r = scanner.check_ssh_password()
        assert r.status == "insecure"


class TestHidepidYApparmor:
    def test_findmnt_fallido_es_unknown(self):
        with patch.object(scanner.subprocess, "run", return_value=_proc(rc=1)):
            r = scanner.check_proc_hidepid()
        assert r.status == "unknown"

    def test_aa_status_sin_privilegios_es_unknown(self):
        def fake_run(cmd, **kw):
            if cmd[:2] == ["systemctl", "is-active"]:
                return _proc(rc=0, stdout="active\n")
            return _proc(rc=4, stderr="You do not have enough privilege")
        with patch.object(scanner.shutil, "which", return_value="/usr/sbin/aa-status"), \
             patch.object(scanner.subprocess, "run", side_effect=fake_run):
            r = scanner.check_apparmor()
        assert r.status == "unknown"
        assert "privilegios" in r.detail.lower()


class TestSuidAlineadoAlModulo:
    UBUNTU_ESTANDAR = "\n".join([
        "/usr/bin/sudo", "/usr/bin/passwd", "/usr/bin/fusermount3",
        "/usr/lib/policykit-1/polkit-agent-helper-1", "/usr/bin/pkexec",
        "/usr/lib/openssh/ssh-keysign",
    ])

    def test_ubuntu_estandar_no_es_insecure(self):
        """El bug original: cualquier sistema estándar daba 'insecure' por
        binarios legítimos que el módulo además jamás tocaría."""
        with patch.object(scanner.subprocess, "run",
                          return_value=_proc(stdout=self.UBUNTU_ESTANDAR)):
            r = scanner.check_suid_binaries()
        assert r.status == "secure"

    def test_binario_de_la_denylist_si_es_insecure(self):
        salida = self.UBUNTU_ESTANDAR + "\n/usr/bin/ntfs-3g\n/usr/bin/chfn"
        with patch.object(scanner.subprocess, "run",
                          return_value=_proc(stdout=salida)):
            r = scanner.check_suid_binaries()
        assert r.status == "insecure"
        assert "ntfs-3g" in r.detail and "chfn" in r.detail
        assert r.fix_module_id == "restrict_suid_binaries"

    def test_denylist_del_scanner_coincide_con_el_modulo(self):
        """Si alguien edita la denylist del módulo y olvida el scanner (o al
        revés), este test lo detecta."""
        enable = (ROOT / "modules" / "restrict_suid_binaries" / "enable.sh").read_text()
        import re
        m = re.search(r'LOCKD_SUID_DENYLIST:-([^}]+)\}', enable)
        assert m, "no se pudo extraer la denylist del módulo"
        del_modulo = set(m.group(1).split())
        assert del_modulo == scanner._SUID_DENYLIST, (
            f"desincronizadas:\n  solo módulo: {del_modulo - scanner._SUID_DENYLIST}"
            f"\n  solo scanner: {scanner._SUID_DENYLIST - del_modulo}"
        )
