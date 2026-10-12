"""
tests/test_reversibility.py — Contrato de reversión de punta a punta

Para cada módulo, enable y después disable deben dejar el sistema exactamente
como estaba antes de Lockd: archivos (contenido y permisos), /etc/group,
opciones de montaje en ejecución, estado de los servicios y modos de
AppArmor. Los paquetes que instala Lockd quedan instalados por diseño y no se
comparan.

Corren sobre un árbol de prueba (LOCKD_SYSROOT) con comandos simulados
(tests/stubs/lockd_stub.py). El PATH del módulo queda solo en .stubs/bin, con
los stubs y enlaces a las HERRAMIENTAS inofensivas: un comando que el árbol no
provee no existe, y si el módulo lo intenta igual el test falla. No tocan el
sistema real y corren sin root; como root se saltean, porque el modo test
aborta (en CI los cubre la pasada sin privilegios).

Los casos que hoy no cumplen el contrato llevan xfail(strict=True) con su
motivo: son la lista ejecutable de deudas. Cuando un arreglo entra, el test
pasa, el modo estricto lo hace fallar y obliga a quitar la marca. La marca
solo cubre DiferenciaDeEstado: si el script falla, aborta en el resguardo o
pide un comando sin stub, el test falla aunque esté marcado.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT        = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"
STUB        = ROOT / "tests" / "stubs" / "lockd_stub.py"
COMANDOS    = ["mount", "findmnt", "systemctl", "apt-get", "aa-enforce",
               "aa-complain", "getent", "groupadd", "usermod", "id", "lockd-stubs"]
# Comandos reales que los módulos pueden usar en modo test: solo leen o escriben
# las rutas que reciben, que caen dentro del árbol. Sumar uno es una decisión:
# si actúa sobre el sistema (servicios, montajes, paquetes), lleva stub.
HERRAMIENTAS = ["basename", "cat", "chmod", "cp", "cut", "date", "dirname", "find",
                "grep", "head", "ls", "mkdir", "mktemp", "mv", "readlink", "rm",
                "rmdir", "sed", "tail"]
RUTA_SISTEMA = "/usr/sbin:/usr/bin:/sbin:/bin"
CATALOGO    = {m["id"]: m for m in yaml.safe_load(
    (MODULES_DIR / "modules.yaml").read_text(encoding="utf-8"))["modules"]}

pytestmark = pytest.mark.skipif(
    os.geteuid() == 0, reason="el modo test no corre como root (en CI: pasada sin privilegios)")


class DiferenciaDeEstado(AssertionError):
    """El sistema no quedó como estaba: lo único que puede causar una deuda."""


class FalloDeEjecucion(Exception):
    """El script falló, abortó en el resguardo o pidió un comando sin stub."""


def _sin_cambios(antes: dict, despues: dict) -> None:
    if despues != antes:
        partes = [k for k in antes if antes[k] != despues.get(k)]
        detalle = "\n".join(f"{k}:\n  antes:   {antes[k]}\n  después: {despues.get(k)}"
                            for k in partes)
        raise DiferenciaDeEstado(f"cambió {', '.join(partes)}\n{detalle}")


class Sistema:
    """Árbol de prueba con comandos simulados y estado inicial tipo Debian."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        for d in ("etc/apt/apt.conf.d", "etc/systemd/system", "etc/fail2ban/jail.d",
                  "etc/apparmor.d", "usr/bin", "var/lib/lockd", ".stubs/bin", ".stubs/state"):
            (raiz / d).mkdir(parents=True, exist_ok=True)
        self.escribir("etc/fstab", "# fstab de prueba\nUUID=1234 / ext4 errors=remount-ro 0 1\n")
        self.escribir("etc/group", "root:x:0:\npolkitd:x:997:\n")
        self.escribir("etc/passwd", "root:x:0:0:root:/root:/bin/bash\n"
                                    "polkitd:x:997:997::/nonexistent:/usr/sbin/nologin\n")
        self.montajes({"/proc": "rw,nosuid,nodev,noexec,relatime",
                       "/dev/shm": "rw,nosuid,nodev,relatime",
                       "/tmp": "rw,nosuid,nodev,relatime"})
        for c in COMANDOS:
            self.instalar_comando(c)
        for h in HERRAMIENTAS:
            real = shutil.which(h, path=RUTA_SISTEMA)
            assert real, f"falta {h} en el sistema"
            (raiz / ".stubs" / "bin" / h).symlink_to(real)

    # ── preparación ──────────────────────────────────────────────────────
    def escribir(self, rel: str, texto: str, modo: int = 0o644) -> Path:
        p = self.raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        p.chmod(modo)
        return p

    def _estado(self, nombre: str, dato) -> None:
        (self.raiz / ".stubs" / "state" / f"{nombre}.json").write_text(json.dumps(dato))

    def montajes(self, puntos: dict) -> None:
        self._estado("mounts", {p: o.split(",") for p, o in puntos.items()})

    def unidades(self, unidades: dict) -> None:
        self._estado("units", unidades)

    def apparmor(self, perfiles: dict) -> None:
        for nombre in perfiles:
            self.escribir(f"etc/apparmor.d/{nombre}", f"profile {nombre} {{}}\n")
        self._estado("aa", perfiles)

    def instalar_comando(self, nombre: str) -> None:
        # misma lógica para todos, con el intérprete que corre pytest
        destino = self.raiz / ".stubs" / "bin" / nombre
        codigo = STUB.read_text(encoding="utf-8").split("\n", 1)[1]
        destino.write_text(f"#!{sys.executable}\n{codigo}", encoding="utf-8")
        destino.chmod(0o755)

    # ── ejecución ────────────────────────────────────────────────────────
    def correr(self, modulo: str, accion: str) -> subprocess.CompletedProcess:
        clave = {"enable": "enable_script", "disable": "disable_script"}[accion]
        script = MODULES_DIR / CATALOGO[modulo][clave]
        r = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL,
            env={"PATH": RUTA_SISTEMA, "LANG": "C.UTF-8", "LOCKD_SYSROOT": str(self.raiz)},
        )
        faltantes = self.raiz / ".stubs" / "faltantes"
        if r.returncode != 0 or "MODO TEST" not in r.stderr or faltantes.exists():
            sin_stub = faltantes.read_text().split() if faltantes.exists() else []
            raise FalloDeEjecucion(f"{modulo} {accion} rc={r.returncode} sin stub={sin_stub}\n"
                                   f"{r.stdout}\n{r.stderr}")
        return r

    def ida_y_vuelta(self, modulo: str) -> None:
        self.correr(modulo, "enable")
        self.correr(modulo, "disable")

    # ── estado observable ────────────────────────────────────────────────
    def estado(self) -> dict:
        archivos = {}
        for p in sorted(self.raiz.rglob("*")):
            rel = p.relative_to(self.raiz)
            if rel.parts[0] == ".stubs" or rel.parts[:3] == ("var", "lib", "lockd"):
                continue                       # stubs y backups de Lockd
            if p.is_symlink():
                archivos[str(rel)] = ("link", os.readlink(p))
            elif p.is_dir():
                archivos[str(rel)] = ("dir", stat.S_IMODE(p.stat().st_mode))
            else:
                archivos[str(rel)] = ("file", stat.S_IMODE(p.stat().st_mode),
                                      p.read_text(encoding="utf-8", errors="replace"))
        st = self.raiz / ".stubs" / "state"

        def leer(nombre):
            f = st / f"{nombre}.json"
            return json.loads(f.read_text()) if f.exists() else {}

        return {
            "archivos": archivos,
            "montajes": {p: sorted(o) for p, o in leer("mounts").items()},
            "unidades": leer("units"),
            "apparmor": leer("aa"),
        }

    def llamadas(self) -> str:
        log = self.raiz / ".stubs" / "calls.log"
        return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.fixture
def sistema(tmp_path):
    return Sistema(tmp_path / "raiz")


# ══════════════════════════════════════════════════════════════════════════════
# Escenarios previos a Lockd
# ══════════════════════════════════════════════════════════════════════════════

def _sin_preparacion(s: Sistema) -> None:
    pass


def _ubuntu_con_actualizaciones(s: Sistema) -> None:
    # unattended-upgrades viene activo de fábrica en Ubuntu (debconf: true)
    s.escribir("etc/apt/apt.conf.d/20auto-upgrades",
               'APT::Periodic::Update-Package-Lists "1";\n'
               'APT::Periodic::Unattended-Upgrade "1";\n')
    s.unidades({"unattended-upgrades": {"enabled": True, "active": True, "masked": False}})


def _fail2ban_propio(s: Sistema) -> None:
    s.instalar_comando("fail2ban-client")
    s.escribir("etc/fail2ban/jail.d/propio.conf", "[sshd]\nenabled = true\nmaxretry = 3\n")
    s.unidades({"fail2ban": {"enabled": True, "active": True, "masked": False}})


def _binarios_suid(s: Sistema) -> None:
    for nombre in ("chfn", "chsh", "passwd", "otro_suid"):
        s.escribir(f"usr/bin/{nombre}", "#!/bin/sh\n", modo=0o4755)


def _perfiles_mixtos(s: Sistema) -> None:
    s.apparmor({"usr.bin.alfa": "enforce", "usr.bin.beta": "complain",
                "usr.sbin.gama": "enforce"})
    s.unidades({"apparmor": {"enabled": True, "active": True, "masked": False}})


def _deuda(motivo: str):
    return pytest.mark.xfail(strict=True, raises=DiferenciaDeEstado, reason=motivo)


CASOS = [
    pytest.param("secure_shared_memory", _sin_preparacion, marks=_deuda(
        "disable no quita noexec de /dev/shm en ejecución: remount sin opciones (martes)")),
    pytest.param("hide_procs_nonroot", _sin_preparacion, marks=_deuda(
        "disable fuerza hidepid=0 y deja el grupo procview con sus miembros (martes)")),
    pytest.param("secure_tmp_partition", _sin_preparacion, marks=_deuda(
        "disable deja noexec en /tmp hasta reiniciar (martes)")),
    pytest.param("automatic_security_updates", _ubuntu_con_actualizaciones, marks=_deuda(
        "disable escribe 20auto-upgrades con \"0\" en vez de restaurar el previo (miércoles)")),
    pytest.param("install_fail2ban", _fail2ban_propio, marks=_deuda(
        "disable detiene y deshabilita un fail2ban que ya estaba activo (miércoles)")),
    pytest.param("restrict_suid_binaries", _binarios_suid),
    pytest.param("apparmor_enforce_mode", _perfiles_mixtos, marks=_deuda(
        "disable pasa a complain perfiles que estaban en enforce (jueves)")),
]


# ══════════════════════════════════════════════════════════════════════════════
# Contrato: enable + disable = estado previo
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("modulo, preparar", CASOS)
def test_ida_y_vuelta_restaura_el_estado_previo(sistema, modulo, preparar):
    preparar(sistema)
    antes = sistema.estado()
    sistema.ida_y_vuelta(modulo)
    _sin_cambios(antes, sistema.estado())


@_deuda("disable restaura fstab entero y borra la línea de otro módulo (martes)")
def test_fstab_compartido_respeta_la_linea_de_otro_modulo(sistema):
    sistema.correr("secure_shared_memory", "enable")
    sistema.correr("hide_procs_nonroot", "enable")
    sistema.correr("secure_shared_memory", "disable")
    fstab = (sistema.raiz / "etc" / "fstab").read_text()
    if "# lockd-shm" in fstab or "# lockd-hide-procs" not in fstab:
        raise DiferenciaDeEstado(f"fstab tras disable de secure_shared_memory:\n{fstab}")


@_deuda("un segundo enable vacía la lista y disable no restaura el SUID (miércoles)")
def test_suid_reaplicar_no_pierde_la_lista(sistema):
    # aplicar un nivel vuelve a ejecutar enable de todos sus módulos
    _binarios_suid(sistema)
    antes = sistema.estado()
    sistema.correr("restrict_suid_binaries", "enable")
    sistema.correr("restrict_suid_binaries", "enable")
    sistema.correr("restrict_suid_binaries", "disable")
    _sin_cambios(antes, sistema.estado())


# ══════════════════════════════════════════════════════════════════════════════
# Los stubs imitan lo que importa (si mienten, el contrato no prueba nada)
# ══════════════════════════════════════════════════════════════════════════════

def _cmd(sistema: Sistema, *args) -> subprocess.CompletedProcess:
    exe = sistema.raiz / ".stubs" / "bin" / args[0]
    return subprocess.run([str(exe), *args[1:]], capture_output=True, text=True, timeout=30)


class TestStubs:
    def test_remount_con_opciones_combina(self, sistema):
        assert _cmd(sistema, "mount", "-o", "remount,noexec", "/dev/shm").returncode == 0
        assert "noexec" in _cmd(sistema, "findmnt", "-n", "-o", "OPTIONS", "/dev/shm").stdout
        _cmd(sistema, "mount", "-o", "remount,exec", "/dev/shm")
        opciones = _cmd(sistema, "findmnt", "-n", "-o", "OPTIONS", "/dev/shm").stdout.strip()
        assert "noexec" not in opciones.split(",") and "exec" in opciones.split(",")

    def test_remount_sin_opciones_ni_fstab_conserva(self, sistema):
        _cmd(sistema, "mount", "-o", "remount,noexec", "/tmp")
        _cmd(sistema, "mount", "-o", "remount", "/tmp")
        assert "noexec" in _cmd(sistema, "findmnt", "-n", "-o", "OPTIONS", "/tmp").stdout

    def test_remount_sin_opciones_con_fstab_aplica_fstab(self, sistema):
        sistema.escribir("etc/fstab", "tmpfs /tmp tmpfs defaults,nosuid 0 0\n")
        _cmd(sistema, "mount", "-o", "remount,noexec", "/tmp")
        _cmd(sistema, "mount", "-o", "remount", "/tmp")
        assert "noexec" not in _cmd(sistema, "findmnt", "-n", "-o", "OPTIONS", "/tmp").stdout

    def test_findmnt_punto_no_montado(self, sistema):
        assert _cmd(sistema, "findmnt", "-n", "/no/montado").returncode == 1

    def test_systemctl_recuerda_estado(self, sistema):
        assert _cmd(sistema, "systemctl", "is-active", "--quiet", "demo").returncode == 3
        _cmd(sistema, "systemctl", "enable", "--now", "demo.service")
        assert _cmd(sistema, "systemctl", "is-active", "--quiet", "demo").returncode == 0
        _cmd(sistema, "systemctl", "stop", "demo")
        assert _cmd(sistema, "systemctl", "is-active", "--quiet", "demo").returncode == 3
        assert _cmd(sistema, "systemctl", "is-enabled", "--quiet", "demo").returncode == 0

    def test_grupos_sobre_el_arbol(self, sistema):
        assert _cmd(sistema, "getent", "group", "procview").returncode == 2
        _cmd(sistema, "groupadd", "procview")
        _cmd(sistema, "usermod", "-aG", "procview", "polkitd")
        linea = _cmd(sistema, "getent", "group", "procview").stdout.strip()
        assert linea.startswith("procview:x:") and linea.endswith(":polkitd")
        assert _cmd(sistema, "id", "polkitd").returncode == 0
        assert _cmd(sistema, "id", "nadie").returncode == 1

    def test_estado_detecta_cambios(self, sistema):
        antes = sistema.estado()
        sistema.escribir("etc/nuevo.conf", "x\n")
        assert sistema.estado() != antes
