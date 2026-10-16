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
COMANDOS    = ["mount", "findmnt", "systemctl", "apt-get", "dpkg-query", "aa-enforce",
               "aa-complain", "apparmor_parser", "aa-enabled", "getent", "groupadd",
               "groupdel", "usermod", "gpasswd", "id", "lockd-stubs"]
# Comandos reales que los módulos pueden usar en modo test: solo leen o escriben
# las rutas que reciben, que caen dentro del árbol. Sumar uno es una decisión:
# si actúa sobre el sistema (servicios, montajes, paquetes), lleva stub.
HERRAMIENTAS = ["basename", "cat", "chmod", "cp", "cut", "date", "dirname", "find",
                "grep", "head", "ln", "ls", "mkdir", "mktemp", "mv", "readlink", "rm",
                "rmdir", "sed", "sha256sum", "tail", "tr"]
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

    def montar(self, punto: str, opciones: str) -> None:
        f = self.raiz / ".stubs" / "state" / "mounts.json"
        actuales = json.loads(f.read_text())
        actuales[punto] = opciones.split(",")
        f.write_text(json.dumps(actuales))

    def fallar_remontaje(self, *puntos: str) -> None:
        self._estado("fallos", {"mount": list(puntos)})

    def agregar_linea(self, rel: str, linea: str) -> None:
        p = self.raiz / rel
        p.write_text(p.read_text(encoding="utf-8") + linea + "\n", encoding="utf-8")

    def unidades(self, unidades: dict) -> None:
        self._estado("units", unidades)

    def apparmor(self, perfiles: dict) -> None:
        # Archivo, enlaces y modo en ejecución coherentes: enforce, complain
        # (bandera en la cabecera), complain-enlace (enlace en
        # force-complain/), unconfined y deshabilitado (enlace en disable/, sin
        # cargar). La cabecera en complain lleva otra bandera sin espacio:
        # aa-complain no la deja igual, así que solo la vuelta desde lo
        # guardado cumple el contrato.
        base = self.raiz / "etc" / "apparmor.d"
        banderas = {"complain": "attach_disconnected,complain", "unconfined": "unconfined"}
        aa = {}
        for nombre, modo in perfiles.items():
            cabecera = f"profile {nombre} /usr/bin/{nombre}"
            if modo in banderas:
                cabecera += f" flags=({banderas[modo]})"
            self.escribir(f"etc/apparmor.d/{nombre}",
                          "abi <abi/4.0>,\ninclude <tunables/global>\n\n"
                          f"{cabecera} {{\n  include <abstractions/base>\n"
                          f"  /usr/bin/{nombre} mr,\n}}\n")
            enlace = {"complain-enlace": "force-complain", "deshabilitado": "disable"}.get(modo)
            if enlace:
                (base / enlace).mkdir(exist_ok=True)
                (base / enlace / nombre).symlink_to(f"/etc/apparmor.d/{nombre}")
            if modo != "deshabilitado":
                aa[nombre] = "complain" if modo == "complain-enlace" else modo
        self._estado("aa", aa)

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

    def correr_esperando_fallo(self, modulo: str, accion: str) -> subprocess.CompletedProcess:
        try:
            r = self.correr(modulo, accion)
        except FalloDeEjecucion as e:
            if "sin stub=[]" not in str(e) or "MODO TEST" not in str(e):
                raise
            return e
        raise AssertionError(f"{modulo} {accion} debía fallar y terminó bien:\n{r.stdout}\n{r.stderr}")

    def ida_y_vuelta(self, modulo: str) -> None:
        self.correr(modulo, "enable")
        self.correr(modulo, "disable")

    def chequear(self, modulo: str) -> int:
        # como lo corre el controlador: sin privilegios y sin _common.sh; el
        # PATH queda solo en los stubs y las herramientas del árbol
        script = MODULES_DIR / CATALOGO[modulo]["check_script"]
        r = subprocess.run(
            [shutil.which("bash", path=RUTA_SISTEMA), str(script)], capture_output=True,
            text=True, timeout=30, stdin=subprocess.DEVNULL,
            env={"PATH": str(self.raiz / ".stubs" / "bin"), "LANG": "C.UTF-8",
                 "LOCKD_SYSROOT": str(self.raiz)},
        )
        return r.returncode

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

        # una unidad deshabilitada, inactiva y sin máscara equivale a no tenerla
        unidades = {n: d for n, d in leer("units").items() if any(d.values())}
        return {
            "archivos": archivos,
            "montajes": {p: sorted(o) for p, o in leer("mounts").items()},
            "unidades": unidades,
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
    s._estado("pkgs", ["fail2ban"])
    s.escribir("etc/fail2ban/jail.d/propio.conf", "[sshd]\nenabled = true\nmaxretry = 3\n")
    s.unidades({"fail2ban": {"enabled": True, "active": True, "masked": False}})


def _binarios_suid(s: Sistema) -> None:
    for nombre in ("chfn", "chsh", "passwd", "otro_suid"):
        s.escribir(f"usr/bin/{nombre}", "#!/bin/sh\n", modo=0o4755)


def _shm_ya_endurecido(s: Sistema) -> None:
    # quien ya tenía noexec en /dev/shm lo conserva al desactivar
    s.montar("/dev/shm", "rw,nosuid,nodev,noexec,relatime")


def _fstab_del_usuario_shm(s: Sistema) -> None:
    s.agregar_linea("etc/fstab", "tmpfs /dev/shm tmpfs defaults,size=2G 0 0")
    s.montar("/dev/shm", "rw,nosuid,nodev,relatime,size=2097152k")


def _procview_existente(s: Sistema) -> None:
    s.agregar_linea("etc/passwd", "alguien:x:1000:1000::/home/alguien:/bin/bash")
    s.agregar_linea("etc/group", "procview:x:1500:alguien")


def _proc_del_usuario(s: Sistema) -> None:
    # línea típica de una guía de endurecimiento, con /proc como queda al
    # arrancar con ella; el kernel muestra hidepid=2 como invisible
    s.agregar_linea("etc/fstab", "proc /proc proc defaults,hidepid=2 0 0")
    s.montar("/proc", "rw,relatime,hidepid=invisible")


def _tmp_ya_endurecido(s: Sistema) -> None:
    s.montar("/tmp", "rw,nosuid,nodev,noexec,relatime")


def _perfiles_mixtos(s: Sistema) -> None:
    s._estado("pkgs", ["apparmor", "apparmor-utils"])
    s.unidades({"apparmor": {"enabled": True, "active": True, "masked": False}})
    s.apparmor({"usr.bin.alfa": "enforce", "usr.bin.beta": "complain",
                "usr.sbin.gama": "complain-enlace", "usr.sbin.delta": "deshabilitado",
                "epsilon": "unconfined"})


def _deuda(motivo: str):
    return pytest.mark.xfail(strict=True, raises=DiferenciaDeEstado, reason=motivo)


CASOS = [
    pytest.param("secure_shared_memory", _sin_preparacion),
    pytest.param("secure_shared_memory", _shm_ya_endurecido),
    pytest.param("secure_shared_memory", _fstab_del_usuario_shm),
    pytest.param("hide_procs_nonroot", _sin_preparacion),
    pytest.param("hide_procs_nonroot", _procview_existente),
    pytest.param("hide_procs_nonroot", _proc_del_usuario),
    pytest.param("secure_tmp_partition", _sin_preparacion),
    pytest.param("secure_tmp_partition", _tmp_ya_endurecido),
    pytest.param("automatic_security_updates", _sin_preparacion),
    pytest.param("automatic_security_updates", _ubuntu_con_actualizaciones),
    pytest.param("install_fail2ban", _sin_preparacion),
    pytest.param("install_fail2ban", _fail2ban_propio),
    pytest.param("restrict_suid_binaries", _binarios_suid),
    pytest.param("apparmor_enforce_mode", _sin_preparacion),
    pytest.param("apparmor_enforce_mode", _perfiles_mixtos),
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


def test_fstab_compartido_respeta_la_linea_de_otro_modulo(sistema):
    sistema.correr("secure_shared_memory", "enable")
    sistema.correr("hide_procs_nonroot", "enable")
    sistema.correr("secure_shared_memory", "disable")
    fstab = (sistema.raiz / "etc" / "fstab").read_text()
    if "# lockd-shm" in fstab or "# lockd-hide-procs" not in fstab:
        raise DiferenciaDeEstado(f"fstab tras disable de secure_shared_memory:\n{fstab}")


MONTAJES = [("secure_shared_memory", "/dev/shm"), ("hide_procs_nonroot", "/proc"),
            ("secure_tmp_partition", "/tmp")]


@pytest.mark.parametrize("modulo, punto", MONTAJES)
def test_reaplicar_enable_conserva_las_opciones_previas(sistema, modulo, punto):
    # aplicar un nivel vuelve a ejecutar enable: lo guardado no se pisa
    antes = sistema.estado()
    sistema.correr(modulo, "enable")
    sistema.correr(modulo, "enable")
    sistema.correr(modulo, "disable")
    _sin_cambios(antes, sistema.estado())


@pytest.mark.parametrize("modulo, punto", MONTAJES)
def test_enable_es_atomico_si_el_remontaje_falla(sistema, modulo, punto):
    sistema.fallar_remontaje(punto)
    antes = sistema.estado()
    sistema.correr_esperando_fallo(modulo, "enable")
    _sin_cambios(antes, sistema.estado())
    # ni opciones previas ni grupos guardados: el próximo enable empieza limpio
    respaldo = sistema.raiz / "var" / "lib" / "lockd" / "backups" / modulo
    assert not list(respaldo.glob("montaje-*.previas"))
    assert not (respaldo / "grupos.estado").exists()


def test_fstab_del_usuario_se_fusiona_sin_duplicar(sistema):
    _fstab_del_usuario_shm(sistema)
    sistema.correr("secure_shared_memory", "enable")
    lineas = (sistema.raiz / "etc" / "fstab").read_text().splitlines()
    activas = [x for x in lineas if not x.startswith("#") and x.split()[1:2] == ["/dev/shm"]]
    assert activas == ["tmpfs /dev/shm tmpfs defaults,size=2G,noexec,nosuid,nodev 0 0 # lockd-shm"]
    assert "# lockd-shm:original tmpfs /dev/shm tmpfs defaults,size=2G 0 0" in lineas


def test_hide_procs_conserva_nosuid_nodev_noexec_en_proc(sistema):
    # La línea de fstab lleva esas banderas explícitas: el remontaje y el
    # arranque, que aplican las opciones de fstab, las mantienen en /proc.
    sistema.correr("hide_procs_nonroot", "enable")
    opciones = sistema.estado()["montajes"]["/proc"]
    assert {"nosuid", "nodev", "noexec", "hidepid=invisible"} <= set(opciones)
    linea = [x for x in (sistema.raiz / "etc" / "fstab").read_text().splitlines()
             if x.endswith("# lockd-hide-procs")]
    assert len(linea) == 1 and "defaults" not in linea[0]
    assert linea[0].split()[3].startswith("nosuid,nodev,noexec,hidepid=invisible,gid=")


def test_paquete_instalado_por_lockd_queda_y_se_avisa(sistema):
    sistema.correr("install_fail2ban", "enable")
    r = sistema.correr("install_fail2ban", "disable")
    paquetes = json.loads((sistema.raiz / ".stubs" / "state" / "pkgs.json").read_text())
    assert "fail2ban" in paquetes
    assert "fail2ban sigue instalado (lo instaló Lockd)" in r.stdout
    assert "fail2ban" not in sistema.estado()["unidades"]


def test_fail2ban_previo_sigue_activo_y_se_recarga(sistema):
    _fail2ban_propio(sistema)
    sistema.correr("install_fail2ban", "enable")
    sistema.correr("install_fail2ban", "disable")
    assert sistema.estado()["unidades"]["fail2ban"] == {"enabled": True, "active": True, "masked": False}
    llamadas = sistema.llamadas().splitlines()
    assert llamadas.count("systemctl reload fail2ban") == 2     # tomar la jail y soltarla
    assert "systemctl stop fail2ban" not in llamadas


def test_enable_fail2ban_es_atomico_si_no_arranca(sistema):
    antes = sistema.estado()
    sistema._estado("fallos", {"systemctl": ["fail2ban"]})
    sistema.correr_esperando_fallo("install_fail2ban", "enable")
    _sin_cambios(antes, sistema.estado())
    respaldo = sistema.raiz / "var" / "lib" / "lockd" / "backups" / "install_fail2ban"
    assert not list(respaldo.glob("servicio-*.previo"))


def test_hide_procs_recupera_las_banderas_de_proc_con_la_linea_de_1_0(sistema):
    # activado con 1.0.x: línea con defaults y /proc sin nosuid,nodev,noexec
    sistema.agregar_linea("etc/group", "procview:x:1500:polkitd")
    sistema.agregar_linea("etc/fstab", "proc /proc proc defaults,hidepid=invisible,gid=1500 0 0 # lockd-hide-procs")
    sistema.montar("/proc", "rw,relatime,gid=1500,hidepid=invisible")
    sistema.correr("hide_procs_nonroot", "enable")
    assert {"nosuid", "nodev", "noexec"} <= set(sistema.estado()["montajes"]["/proc"])
    lineas = [x for x in (sistema.raiz / "etc" / "fstab").read_text().splitlines()
              if x.endswith("# lockd-hide-procs")]
    assert len(lineas) == 1 and "defaults" not in lineas[0]


def test_actualizaciones_sin_linea_base_se_apagan_como_en_1_0(sistema):
    # activado con 1.0.x: sin línea base, disable hace lo que hacía esa versión
    sistema.escribir("etc/apt/apt.conf.d/20auto-upgrades",
                     'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n')
    r = sistema.correr("automatic_security_updates", "disable")
    conf = (sistema.raiz / "etc" / "apt" / "apt.conf.d" / "20auto-upgrades").read_text()
    assert 'Unattended-Upgrade "0"' in conf
    assert "No hay línea base" in r.stdout


def test_disable_sin_opciones_guardadas_no_adivina(sistema):
    # activado con una versión anterior de Lockd: no hay opciones previas
    sistema.agregar_linea("etc/fstab", "tmpfs /dev/shm tmpfs defaults,noexec,nosuid,nodev 0 0 # lockd-shm")
    sistema.montar("/dev/shm", "rw,nosuid,nodev,noexec,relatime")
    r = sistema.correr("secure_shared_memory", "disable")
    assert "# lockd-shm" not in (sistema.raiz / "etc" / "fstab").read_text()
    assert "noexec" in sistema.estado()["montajes"]["/dev/shm"]
    assert "No hay opciones previas guardadas" in r.stdout


def test_suid_reaplicar_no_pierde_la_lista(sistema):
    # aplicar un nivel vuelve a ejecutar enable de todos sus módulos
    _binarios_suid(sistema)
    antes = sistema.estado()
    sistema.correr("restrict_suid_binaries", "enable")
    sistema.correr("restrict_suid_binaries", "enable")
    sistema.correr("restrict_suid_binaries", "disable")
    _sin_cambios(antes, sistema.estado())


APPARMOR = "apparmor_enforce_mode"


def _perfil(s: Sistema, nombre: str) -> str:
    return (s.raiz / "etc" / "apparmor.d" / nombre).read_text(encoding="utf-8")


def test_apparmor_pasa_a_enforce_solo_los_de_complain(sistema):
    _perfiles_mixtos(sistema)
    antes = sistema.estado()
    sistema.correr(APPARMOR, "enable")
    despues = sistema.estado()
    assert despues["apparmor"] == {"usr.bin.alfa": "enforce", "usr.bin.beta": "enforce",
                                   "usr.sbin.gama": "enforce", "epsilon": "unconfined"}
    assert "flags=(attach_disconnected) {" in _perfil(sistema, "usr.bin.beta")
    assert "etc/apparmor.d/force-complain/usr.sbin.gama" not in despues["archivos"]
    for intacto in ("usr.bin.alfa", "usr.sbin.delta", "disable/usr.sbin.delta", "epsilon"):
        clave = f"etc/apparmor.d/{intacto}"
        assert despues["archivos"][clave] == antes["archivos"][clave]


def test_apparmor_no_toca_un_unconfined_aunque_tenga_enlace_en_force_complain(sistema):
    # aa-enforce le quitaría unconfined y la aplicación quedaría sin permisos
    _perfiles_mixtos(sistema)
    (sistema.raiz / "etc" / "apparmor.d" / "force-complain" / "epsilon").symlink_to(
        "/etc/apparmor.d/epsilon")
    antes = sistema.estado()
    sistema.correr(APPARMOR, "enable")
    despues = sistema.estado()
    for clave in ("etc/apparmor.d/epsilon", "etc/apparmor.d/force-complain/epsilon"):
        assert despues["archivos"][clave] == antes["archivos"][clave]
    assert despues["apparmor"]["epsilon"] == "unconfined"


def test_apparmor_reaplicar_enable_conserva_lo_guardado(sistema):
    _perfiles_mixtos(sistema)
    antes = sistema.estado()
    sistema.correr(APPARMOR, "enable")
    sistema.correr(APPARMOR, "enable")
    sistema.correr(APPARMOR, "disable")
    _sin_cambios(antes, sistema.estado())


@pytest.mark.parametrize("nombre", ["usr.bin.beta", "usr.sbin.gama"])
def test_apparmor_perfil_editado_conserva_el_cambio_y_vuelve_a_complain(sistema, nombre):
    # beta estaba en complain por bandera y gama por enlace en force-complain/
    _perfiles_mixtos(sistema)
    sistema.correr(APPARMOR, "enable")
    sistema.agregar_linea(f"etc/apparmor.d/{nombre}", "# ajuste del administrador")
    r = sistema.correr(APPARMOR, "disable")
    assert "# ajuste del administrador" in _perfil(sistema, nombre)
    assert sistema.estado()["apparmor"][nombre] == "complain"
    assert f"{nombre} cambió después de activar el módulo" in r.stdout


def test_apparmor_reaplicar_tras_editar_guarda_la_edicion(sistema):
    # el administrador ajusta un perfil que Lockd pasó a enforce y lo vuelve a
    # complain: un nuevo enable lo guarda así y disable vuelve a esa versión
    _perfiles_mixtos(sistema)
    sistema.correr(APPARMOR, "enable")
    sistema.agregar_linea("etc/apparmor.d/usr.bin.beta", "# ajuste del administrador")
    _cmd(sistema, "aa-complain", str(sistema.raiz / "etc" / "apparmor.d" / "usr.bin.beta"))
    editado = _perfil(sistema, "usr.bin.beta")
    sistema.correr(APPARMOR, "enable")
    sistema.correr(APPARMOR, "disable")
    assert _perfil(sistema, "usr.bin.beta") == editado
    assert sistema.estado()["apparmor"]["usr.bin.beta"] == "complain"


def test_apparmor_si_aa_enforce_falla_ese_perfil_vuelve_y_los_demas_siguen(sistema):
    _perfiles_mixtos(sistema)
    antes = sistema.estado()
    sistema._estado("fallos", {"aa-enforce": ["usr.bin.beta"]})
    fallo = sistema.correr_esperando_fallo(APPARMOR, "enable")
    assert "usr.bin.beta" in str(fallo)
    despues = sistema.estado()
    clave = "etc/apparmor.d/usr.bin.beta"
    assert despues["archivos"][clave] == antes["archivos"][clave]
    assert despues["apparmor"]["usr.bin.beta"] == "complain"
    assert despues["apparmor"]["usr.sbin.gama"] == "enforce"
    sistema._estado("fallos", {})
    sistema.correr(APPARMOR, "disable")
    _sin_cambios(antes, sistema.estado())


def test_apparmor_sin_soporte_en_el_kernel_no_toca_nada(sistema):
    _perfiles_mixtos(sistema)
    antes = sistema.estado()
    sistema._estado("fallos", {"aa-enabled": True})
    sistema.correr_esperando_fallo(APPARMOR, "enable")
    _sin_cambios(antes, sistema.estado())
    respaldo = sistema.raiz / "var" / "lib" / "lockd" / "backups" / APPARMOR
    assert not list(respaldo.glob("servicio-*.previo"))
    assert not (respaldo / "apparmor").exists()


def test_apparmor_sin_estado_guardado_deja_los_perfiles_como_estan(sistema):
    # activado con 1.0.x: no hay nada guardado y disable no adivina modos
    _perfiles_mixtos(sistema)
    antes = sistema.estado()
    r = sistema.correr(APPARMOR, "disable")
    _sin_cambios(antes, sistema.estado())
    assert "No hay estado guardado de los perfiles" in r.stdout


def test_apparmor_check_sigue_el_ciclo(sistema):
    _perfiles_mixtos(sistema)
    assert sistema.chequear(APPARMOR) == 1          # beta y gama en complain
    sistema.correr(APPARMOR, "enable")
    assert sistema.chequear(APPARMOR) == 0
    sistema.correr(APPARMOR, "disable")
    assert sistema.chequear(APPARMOR) == 1


def test_apparmor_check_no_cuenta_deshabilitados_ni_unconfined(sistema):
    sistema.unidades({"apparmor": {"enabled": True, "active": True, "masked": False}})
    sistema.apparmor({"usr.bin.alfa": "enforce", "usr.sbin.delta": "deshabilitado",
                      "epsilon": "unconfined"})
    assert sistema.chequear(APPARMOR) == 0
    sistema.unidades({"apparmor": {"enabled": True, "active": False, "masked": False}})
    assert sistema.chequear(APPARMOR) == 1


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
        # como el kernel: exec no se muestra, solo la ausencia de noexec
        assert opciones.split(",") == ["rw", "nosuid", "nodev", "relatime"]

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

    def test_apt_get_instala_y_arranca_el_servicio_como_debian(self, sistema):
        assert _cmd(sistema, "dpkg-query", "-W", "-f=${Status}", "fail2ban").returncode == 1
        _cmd(sistema, "apt-get", "install", "-y", "fail2ban")
        assert _cmd(sistema, "dpkg-query", "-W", "-f=${Status}", "fail2ban").stdout == "install ok installed"
        assert _cmd(sistema, "systemctl", "is-active", "--quiet", "fail2ban").returncode == 0

    def test_reload_de_unidad_inactiva_falla(self, sistema):
        assert _cmd(sistema, "systemctl", "reload", "fail2ban").returncode == 1

    def test_estado_detecta_cambios(self, sistema):
        antes = sistema.estado()
        sistema.escribir("etc/nuevo.conf", "x\n")
        assert sistema.estado() != antes

    def test_aa_enforce_reescribe_la_cabecera_y_borra_los_enlaces(self, sistema):
        sistema.apparmor({"beta": "complain", "gama": "complain-enlace"})
        base = sistema.raiz / "etc" / "apparmor.d"
        assert _cmd(sistema, "aa-enforce", str(base / "beta"), str(base / "gama")).returncode == 0
        assert "profile beta /usr/bin/beta flags=(attach_disconnected) {" in (base / "beta").read_text()
        assert not (base / "force-complain" / "gama").is_symlink()
        assert sistema.estado()["apparmor"] == {"beta": "enforce", "gama": "enforce"}

    def test_aa_complain_no_deja_la_cabecera_igual(self, sistema):
        # como aa.py: banderas separadas por ", " y siempre con "flags="
        sistema.apparmor({"beta": "complain"})
        perfil = sistema.raiz / "etc" / "apparmor.d" / "beta"
        _cmd(sistema, "aa-enforce", str(perfil))
        _cmd(sistema, "aa-complain", str(perfil))
        assert "flags=(attach_disconnected, complain) {" in perfil.read_text()

    def test_aa_enforce_que_falla_deja_el_archivo_reescrito(self, sistema):
        # como el real: reescribe el archivo y después falla la recarga
        sistema.apparmor({"beta": "complain"})
        sistema._estado("fallos", {"aa-enforce": ["beta"]})
        perfil = sistema.raiz / "etc" / "apparmor.d" / "beta"
        assert _cmd(sistema, "aa-enforce", str(perfil)).returncode == 1
        assert "complain" not in perfil.read_text()
        assert sistema.estado()["apparmor"]["beta"] == "complain"

    def test_apparmor_parser_carga_segun_banderas_y_descarga(self, sistema):
        sistema.apparmor({"beta": "complain", "alfa": "enforce", "epsilon": "unconfined"})
        base = sistema.raiz / "etc" / "apparmor.d"
        _cmd(sistema, "apparmor_parser", "-R", str(base / "beta"))
        assert "beta" not in sistema.estado()["apparmor"]
        _cmd(sistema, "apparmor_parser", "-r", str(base / "beta"))
        _cmd(sistema, "apparmor_parser", "-r", "-C", str(base / "alfa"))
        assert sistema.estado()["apparmor"] == {"beta": "complain", "alfa": "complain",
                                                "epsilon": "unconfined"}
        assert _cmd(sistema, "apparmor_parser", "-R", str(base / "sin.cargar")).returncode == 1
