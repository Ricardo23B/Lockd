"""
engine/scanner.py — motor de auditoría de seguridad

Ejecuta todos los checks registrados con @check y devuelve un SecurityReport con:
  - resultados por check: secure | insecure | unknown
  - score 0-100 ponderado
  - fixes recomendados (module IDs)
  - perfil de seguridad sugerido

Para añadir un check: decorar la función con @check y añadir su peso en _WEIGHTS.
Los pesos deben sumar 100.
"""
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger("lockd.scanner")

# ── Pesos de checks (deben sumar 100) ─────────────────────────────────────
_WEIGHTS: dict[str, int] = {
    "firewall":         16,
    "fail2ban":          6,
    "ssh_password":     14,
    "ssh_root":          8,
    "tmp_noexec":        8,
    "shm_noexec":        4,
    "proc_hidepid":      8,
    "usb_storage":       4,
    "auto_updates":      6,
    "core_dumps":        4,
    "ctrl_alt_del":      2,
    "sysctl_hardening":  8,
    "kernel_modules":    6,
    "apparmor":          6,
    "open_ports":        6,
    "suid_binaries":     4,
}

_CHECKS: List[Callable] = []


def check(fn: Callable) -> Callable:
    """Decorador que registra un check en el motor."""
    _CHECKS.append(fn)
    return fn


@dataclass
class CheckResult:
    id:            str
    name:          str
    status:        str             # "secure" | "insecure" | "unknown"
    detail:        str  = ""
    fix_module_id: Optional[str] = None
    category:      str  = ""


@dataclass
class SecurityReport:
    checks:            List[CheckResult] = field(default_factory=list)
    score:             int               = 0
    recommended_fixes: List[str]         = field(default_factory=list)
    suggested_profile: Optional[str]     = None

    def by_status(self, status: str) -> List[CheckResult]:
        return [c for c in self.checks if c.status == status]

    def by_category(self, category: str) -> List[CheckResult]:
        return [c for c in self.checks if c.category == category]

    @property
    def n_secure(self) -> int:
        return len(self.by_status("secure"))

    @property
    def n_insecure(self) -> int:
        return len(self.by_status("insecure"))

    @property
    def n_unknown(self) -> int:
        return len(self.by_status("unknown"))


# ── Checks individuales ────────────────────────────────────────────────────

@check
def check_firewall() -> CheckResult:
    if not shutil.which("ufw"):
        return CheckResult("firewall", "Cortafuegos (UFW)", "unknown",
                           "ufw no está instalado", "enable_firewall", "network")
    r = subprocess.run(["ufw", "status"], capture_output=True, text=True)
    if "active" in r.stdout.lower():
        return CheckResult("firewall", "Cortafuegos (UFW)", "secure",
                           "UFW activo", category="network")
    return CheckResult("firewall", "Cortafuegos (UFW)", "insecure",
                       "UFW instalado pero inactivo", "enable_firewall", "network")


@check
def check_fail2ban() -> CheckResult:
    if not shutil.which("fail2ban-client"):
        return CheckResult("fail2ban", "Fail2ban", "insecure",
                           "fail2ban no está instalado", "install_fail2ban", "network")
    r = subprocess.run(
        ["systemctl", "is-active", "fail2ban"],
        capture_output=True, text=True
    )
    if r.stdout.strip() == "active":
        return CheckResult("fail2ban", "Fail2ban", "secure",
                           "Servicio activo", category="network")
    return CheckResult("fail2ban", "Fail2ban", "insecure",
                       "Instalado pero no activo", "install_fail2ban", "network")


@check
def check_ssh_password() -> CheckResult:
    val = _sshd_option("PasswordAuthentication")
    if val == "no":
        return CheckResult("ssh_password", "SSH: autenticación por contraseña",
                           "secure", "PasswordAuthentication no", category="services")
    if val is None:
        return CheckResult("ssh_password", "SSH: autenticación por contraseña",
                           "unknown", "Sin config explícita",
                           "hardened_ssh_config", "services")
    return CheckResult("ssh_password", "SSH: autenticación por contraseña",
                       "insecure", f"PasswordAuthentication {val}",
                       "hardened_ssh_config", "services")


@check
def check_ssh_root() -> CheckResult:
    val = _sshd_option("PermitRootLogin")
    if val in ("no", "prohibit-password"):
        return CheckResult("ssh_root", "SSH: login root", "secure",
                           f"PermitRootLogin {val}", category="services")
    if val is None:
        return CheckResult("ssh_root", "SSH: login root", "unknown",
                           "Sin config explícita", "hardened_ssh_config", "services")
    return CheckResult("ssh_root", "SSH: login root", "insecure",
                       f"PermitRootLogin {val}", "hardened_ssh_config", "services")


@check
def check_tmp_noexec() -> CheckResult:
    r = subprocess.run(
        ["findmnt", "-n", "-o", "OPTIONS", "/tmp"],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        opts = r.stdout.strip()
        if "noexec" in opts:
            return CheckResult("tmp_noexec", "/tmp: opciones de montaje", "secure",
                               f"Flags: {opts}", category="filesystem")
        return CheckResult("tmp_noexec", "/tmp: opciones de montaje", "insecure",
                           f"Montado sin noexec ({opts})",
                           "secure_tmp_partition", "filesystem")
    return CheckResult("tmp_noexec", "/tmp: opciones de montaje", "unknown",
                       "No se pudo verificar", "secure_tmp_partition", "filesystem")


@check
def check_shm_noexec() -> CheckResult:
    r = subprocess.run(
        ["findmnt", "-n", "-o", "OPTIONS", "/dev/shm"],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        opts = r.stdout.strip()
        if "noexec" in opts:
            return CheckResult("shm_noexec", "/dev/shm: opciones de montaje", "secure",
                               f"Flags: {opts}", category="filesystem")
        return CheckResult("shm_noexec", "/dev/shm: opciones de montaje", "insecure",
                           f"Montado sin noexec ({opts})",
                           "secure_shared_memory", "filesystem")
    return CheckResult("shm_noexec", "/dev/shm: opciones de montaje", "unknown",
                       "No se pudo verificar", "secure_shared_memory", "filesystem")


@check
def check_proc_hidepid() -> CheckResult:
    r = subprocess.run(
        ["findmnt", "-n", "-o", "OPTIONS", "/proc"],
        capture_output=True, text=True
    )
    opts = r.stdout.strip()
    if "hidepid=2" in opts or "hidepid=invisible" in opts:
        return CheckResult("proc_hidepid", "/proc: visibilidad de procesos", "secure",
                           f"hidepid activo: {opts}", category="access_control")
    return CheckResult("proc_hidepid", "/proc: visibilidad de procesos", "insecure",
                       "hidepid no configurado — usuarios ven procesos ajenos",
                       "hide_procs_nonroot", "access_control")


@check
def check_usb_storage() -> CheckResult:
    bl = Path("/etc/modprobe.d/lockd-usb-storage.conf")
    if bl.exists() and "blacklist usb-storage" in bl.read_text():
        return CheckResult("usb_storage", "Almacenamiento USB", "secure",
                           "usb-storage en lista negra del kernel",
                           category="access_control")
    r = subprocess.run(["lsmod"], capture_output=True, text=True)
    if "usb_storage" in r.stdout:
        return CheckResult("usb_storage", "Almacenamiento USB", "insecure",
                           "Módulo usb-storage cargado y activo",
                           "disable_usb_storage", "access_control")
    return CheckResult("usb_storage", "Almacenamiento USB", "unknown",
                       "No cargado actualmente (puede cargarse al conectar un USB)",
                       category="access_control")


@check
def check_auto_updates() -> CheckResult:
    for path in (
        "/etc/apt/apt.conf.d/20auto-upgrades",
        "/etc/apt/apt.conf.d/10periodic",
    ):
        p = Path(path)
        if p.exists() and 'Unattended-Upgrade "1"' in p.read_text():
            return CheckResult("auto_updates", "Actualizaciones automáticas", "secure",
                               "Unattended-Upgrade activo", category="system_hardening")
    return CheckResult("auto_updates", "Actualizaciones automáticas", "insecure",
                       "No configuradas", "automatic_security_updates", "system_hardening")


@check
def check_core_dumps() -> CheckResult:
    limit_conf = Path("/etc/security/limits.d/lockd-coredumps.conf")
    sysctl_val = _sysctl_get("kernel.core_pattern")
    if limit_conf.exists() or sysctl_val == "|/bin/false":
        return CheckResult("core_dumps", "Core dumps", "secure",
                           "Core dumps deshabilitados", category="system_hardening")
    return CheckResult("core_dumps", "Core dumps", "insecure",
                       "Core dumps habilitados — pueden exponer datos en memoria",
                       "disable_core_dumps", "system_hardening")


@check
def check_ctrl_alt_del() -> CheckResult:
    r = subprocess.run(
        ["systemctl", "is-enabled", "ctrl-alt-del.target"],
        capture_output=True, text=True
    )
    status = r.stdout.strip()
    if status == "masked":
        return CheckResult("ctrl_alt_del", "Ctrl+Alt+Del", "secure",
                           "Reinicio por teclado deshabilitado", category="system_hardening")
    return CheckResult("ctrl_alt_del", "Ctrl+Alt+Del", "insecure",
                       f"ctrl-alt-del.target: {status or 'activo'}",
                       "disable_ctrl_alt_del", "system_hardening")


@check
def check_sysctl_hardening() -> CheckResult:
    conf = Path("/etc/sysctl.d/99-lockd-hardening.conf")
    if conf.exists():
        return CheckResult("sysctl_hardening", "Parámetros kernel (sysctl)", "secure",
                           "Configuración de hardening aplicada", category="kernel")
    # verificar algunos parámetros clave
    checks_ok = 0
    for param, expected in [
        ("net.ipv4.tcp_syncookies", "1"),
        ("net.ipv4.conf.all.accept_redirects", "0"),
        ("net.ipv4.conf.all.send_redirects", "0"),
    ]:
        val = _sysctl_get(param)
        if val == expected:
            checks_ok += 1
    if checks_ok == 3:
        return CheckResult("sysctl_hardening", "Parámetros kernel (sysctl)", "secure",
                           "Parámetros de red seguros", category="kernel")
    return CheckResult("sysctl_hardening", "Parámetros kernel (sysctl)", "insecure",
                       "Parámetros del kernel sin endurecer",
                       "kernel_sysctl_hardening", "kernel")


@check
def check_kernel_modules() -> CheckResult:
    dangerous = ["cramfs", "freevxfs", "jffs2", "hfs", "hfsplus", "udf",
                 "dccp", "sctp", "rds", "tipc"]
    r = subprocess.run(["lsmod"], capture_output=True, text=True)
    loaded = r.stdout.lower()
    found  = [m for m in dangerous if re.search(rf"\b{m}\b", loaded)]

    bl = Path("/etc/modprobe.d/lockd-module-blacklist.conf")
    if bl.exists():
        return CheckResult("kernel_modules", "Módulos kernel innecesarios", "secure",
                           "Lista negra de módulos aplicada", category="kernel")
    if found:
        return CheckResult("kernel_modules", "Módulos kernel innecesarios", "insecure",
                           f"Módulos peligrosos cargados: {', '.join(found)}",
                           "kernel_module_blacklist", "kernel")
    return CheckResult("kernel_modules", "Módulos kernel innecesarios", "unknown",
                       "No cargados actualmente (se podrían cargar bajo demanda)",
                       "kernel_module_blacklist", "kernel")


@check
def check_apparmor() -> CheckResult:
    if not shutil.which("apparmor_status") and not shutil.which("aa-status"):
        return CheckResult("apparmor", "AppArmor", "insecure",
                           "AppArmor no está instalado",
                           "apparmor_enforce_mode", "access_control")
    r = subprocess.run(
        ["systemctl", "is-active", "apparmor"],
        capture_output=True, text=True
    )
    if r.stdout.strip() != "active":
        return CheckResult("apparmor", "AppArmor", "insecure",
                           "AppArmor instalado pero inactivo",
                           "apparmor_enforce_mode", "access_control")

    tool = shutil.which("apparmor_status") or shutil.which("aa-status")
    r2 = subprocess.run([tool], capture_output=True, text=True)
    if "enforce" in r2.stdout.lower():
        return CheckResult("apparmor", "AppArmor", "secure",
                           "Activo con perfiles en modo enforce",
                           category="access_control")
    return CheckResult("apparmor", "AppArmor", "unknown",
                       "Activo pero sin perfiles en enforce",
                       "apparmor_enforce_mode", "access_control")


@check
def check_open_ports() -> CheckResult:
    r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
    if r.returncode != 0:
        return CheckResult("open_ports", "Puertos abiertos", "unknown",
                           "No se pudo ejecutar ss", category="network")
    risky = {"21", "23", "135", "139", "445", "1433", "3306", "3389", "5900"}
    ports = []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            ports.append(parts[3].rsplit(":", 1)[-1])
    found = risky & set(ports)
    if found:
        return CheckResult("open_ports", "Puertos abiertos", "insecure",
                           f"Puertos de riesgo: {', '.join(sorted(found))}",
                           category="network")
    return CheckResult("open_ports", "Puertos abiertos", "secure",
                       f"Puertos en escucha: {', '.join(ports) or 'ninguno'}",
                       category="network")


@check
def check_suid_binaries() -> CheckResult:
    # lista de binarios SUID conocidos y necesarios
    safe_suid = {
        "sudo", "su", "mount", "umount", "passwd", "newgrp", "chfn",
        "chsh", "gpasswd", "pkexec", "ping", "ping6",
    }
    try:
        r = subprocess.run(
            ["find", "/usr", "/bin", "/sbin", "-perm", "-4000", "-type", "f"],
            capture_output=True, text=True, timeout=15
        )
        found = [Path(p).name for p in r.stdout.splitlines() if p.strip()]
        risky = [f for f in found if f not in safe_suid]
        if risky:
            return CheckResult("suid_binaries", "Binarios SUID", "insecure",
                               f"SUID no esenciales: {', '.join(risky[:5])}{'...' if len(risky)>5 else ''}",
                               "restrict_suid_binaries", "access_control")
        return CheckResult("suid_binaries", "Binarios SUID", "secure",
                           f"Solo binarios SUID esenciales ({len(found)} encontrados)",
                           category="access_control")
    except (subprocess.TimeoutExpired, OSError):
        return CheckResult("suid_binaries", "Binarios SUID", "unknown",
                           "No se pudo escanear el sistema de archivos",
                           "restrict_suid_binaries", "access_control")


# ── Motor principal ────────────────────────────────────────────────────────

def run_scan() -> SecurityReport:
    """Ejecuta todos los checks y devuelve el SecurityReport completo."""
    report = SecurityReport()

    for fn in _CHECKS:
        try:
            result = fn()
        except Exception as e:
            log.error(f"Error en check '{fn.__name__}': {e}")
            result = CheckResult(
                fn.__name__, fn.__name__, "unknown",
                f"Error interno: {e}"
            )
        report.checks.append(result)
        icon = "✓" if result.status == "secure" else "✗" if result.status == "insecure" else "?"
        log.debug(f"  {icon} {result.id}: {result.status}")

    # score ponderado
    score = 0
    for r in report.checks:
        w = _WEIGHTS.get(r.id, 0)
        if r.status == "secure":
            score += w
        elif r.status == "unknown":
            score += w // 2
    report.score = min(100, max(0, score))

    # fixes recomendados (únicos, en orden)
    seen:  set[str] = set()
    fixes: list[str] = []
    for r in report.checks:
        if r.status == "insecure" and r.fix_module_id and r.fix_module_id not in seen:
            seen.add(r.fix_module_id)
            fixes.append(r.fix_module_id)
    report.recommended_fixes = fixes

    # sugerir perfil de seguridad
    report.suggested_profile = _suggest_profile(report)

    log.info(
        f"Scan completo — Score: {report.score}/100 | "
        f"✓{report.n_secure} ✗{report.n_insecure} ?{report.n_unknown}"
    )
    return report


def _suggest_profile(report: SecurityReport) -> Optional[str]:
    """Sugiere el perfil más adecuado basado en los resultados del scan."""
    score = report.score
    insecure_ids = {r.id for r in report.by_status("insecure")}

    # servidor si SSH inseguro es el problema principal y no hay escritorio
    if "ssh_password" in insecure_ids and score < 60:
        return "server"
    if score >= 80:
        return "paranoid"
    if score >= 60:
        return "developer_workstation"
    if score >= 40:
        return "home_desktop"
    return "home_desktop"


# ── Helpers internos ───────────────────────────────────────────────────────

def _sshd_option(option: str) -> Optional[str]:
    """Lee un campo de sshd_config y sus drop-ins. Devuelve el último valor efectivo."""
    files = [Path("/etc/ssh/sshd_config")]
    d = Path("/etc/ssh/sshd_config.d")
    if d.exists():
        files += sorted(d.glob("*.conf"))
    val = None
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            m = re.match(rf"(?i){re.escape(option)}\s+(\S+)", line)
            if m:
                val = m.group(1).lower()
    return val


def _find_sysctl() -> Optional[str]:
    """Busca el binario sysctl en las rutas habituales de Debian/Ubuntu."""
    return (
        shutil.which("sysctl")
        or shutil.which("sysctl", path="/sbin:/usr/sbin:/bin:/usr/bin")
        or next(
            (p for p in ("/sbin/sysctl", "/usr/sbin/sysctl", "/bin/sysctl")
             if Path(p).exists()),
            None,
        )
    )


def _sysctl_get(param: str) -> Optional[str]:
    """
    Lee un parámetro sysctl.
    Intenta el binario sysctl primero; si no está en PATH usa /proc/sys directamente.
    Devuelve None si no se puede leer.
    """
    # Método 1: binario sysctl (puede estar en /sbin o /usr/sbin en Debian)
    cmd = _find_sysctl()
    if cmd:
        try:
            r = subprocess.run(
                [cmd, "-n", param],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except OSError:
            pass

    # Método 2: leer /proc/sys directamente (siempre disponible en Linux)
    # net.ipv4.tcp_syncookies  →  /proc/sys/net/ipv4/tcp_syncookies
    try:
        proc_path = Path("/proc/sys") / param.replace(".", "/")
        if proc_path.exists():
            return proc_path.read_text().strip()
    except OSError:
        pass

    return None
