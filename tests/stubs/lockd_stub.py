#!/usr/bin/env python3
"""
tests/stubs/lockd_stub.py — Comandos del sistema simulados para el modo test

Un solo programa que se comporta según el nombre con el que lo invocan
(mount, findmnt, systemctl, apt-get, dpkg-query, aa-enforce, aa-complain,
apparmor_parser, aa-enabled, getent, groupadd, groupdel, usermod, gpasswd, id,
fail2ban-client). Los tests lo copian a
$LOCKD_SYSROOT/.stubs/bin/<comando>, junto con el centinela lockd-stubs:
_common.sh lo ejecuta antes de nada (si no responde "ok", aborta) y deja el
PATH solo en ese directorio.

El estado simulado vive en $LOCKD_SYSROOT/.stubs/state/*.json y cada llamada
queda en $LOCKD_SYSROOT/.stubs/calls.log. Los archivos (/etc/group, /etc/fstab,
...) son los del árbol de prueba. La semántica imita lo que importa para
revertir:
  - mount -o remount,OPCIONES PUNTO combina las opciones con las actuales.
    Si el punto figura en fstab, como mount(8) con un solo argumento, aplica
    primero las de fstab y después las de -o;
  - mount -o remount PUNTO, sin opciones, toma las de fstab si el punto figura
    ahí y, si no, conserva las actuales;
  - las opciones se guardan como las muestra el kernel: exec, suid y dev no
    aparecen nunca (solo sus "no"), size= va en k como en tmpfs, y /proc no
    muestra hidepid ni gid con su valor por defecto (0), como
    proc_show_options();
  - state/fallos.json ({"mount": [PUNTO, ...], "systemctl": [UNIDAD, ...]})
    hace fallar el remontaje de esos puntos o el arranque de esas unidades,
    para probar que enable no deja nada a medias;
  - systemctl recuerda enabled, active y masked por unidad;
  - apt-get install anota el paquete en state/pkgs.json y, como hace Debian
    al instalar, habilita y arranca su servicio; dpkg-query lo consulta;
  - aa-enforce y aa-complain hacen lo que apparmor-utils 3.0 y 4.0 con el
    archivo: borran los enlaces del perfil en disable/ (y en force-complain/
    al pasar a enforce), reescriben cada cabecera con sus banderas (siempre
    con "flags=" y separadas por ", ") y recargan el perfil. Con el nombre del
    perfil en state/fallos.json ({"aa-enforce": [NOMBRE, ...]}) la recarga
    falla después de reescribir, como cuando el parser rechaza el perfil;
  - apparmor_parser -r carga el perfil en el modo que dicen sus banderas
    (complain con -C), -R lo descarga. El modo en ejecución de cada perfil
    vive en state/aa.json; un perfil sin cargar no figura;
  - aa-enabled responde que AppArmor está habilitado, salvo con
    {"aa-enabled": true} en state/fallos.json.
"""
import json
import re
import sys
from pathlib import Path

NAME = Path(sys.argv[0]).name
ARGS = sys.argv[1:]
ROOT = Path(__file__).absolute().parent.parent.parent      # <root>/.stubs/bin/<cmd>
STATE = ROOT / ".stubs" / "state"

PARES = {"exec": "noexec", "noexec": "exec", "suid": "nosuid", "nosuid": "suid",
         "dev": "nodev", "nodev": "dev", "rw": "ro", "ro": "rw"}


def _log() -> None:
    with open(ROOT / ".stubs" / "calls.log", "a", encoding="utf-8") as f:
        f.write(" ".join([NAME, *ARGS]) + "\n")


def _cargar(nombre: str, defecto):
    p = STATE / f"{nombre}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def _guardar(nombre: str, dato) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{nombre}.json").write_text(
        json.dumps(dato, indent=1, sort_keys=True), encoding="utf-8")


# ── montajes ────────────────────────────────────────────────────────────────
def _combinar(actuales: list, nuevas: list) -> list:
    res = list(actuales)
    for op in nuevas:
        if op in ("remount", ""):
            continue
        if op == "defaults":
            res = _combinar(res, ["rw", "suid", "dev", "exec"])
            continue
        if "=" in op:
            clave = op.split("=", 1)[0] + "="
            res = [o for o in res if not o.startswith(clave)]
        elif op in PARES:
            res = [o for o in res if o not in (op, PARES[op])]
        elif op in res:
            continue
        res.append(op)
    return res


def _tamano_en_k(op: str) -> str:
    valor = op.split("=", 1)[1]
    factor = {"k": 1, "m": 1024, "g": 1024 * 1024}
    if valor[:-1].isdigit() and valor[-1:].lower() in factor:
        return f"size={int(valor[:-1]) * factor[valor[-1].lower()]}k"
    if valor.isdigit():                              # bytes
        return f"size={int(valor) // 1024}k"
    return op                                        # p. ej. size=50%


def _normalizar(punto: str, opciones: list) -> list:
    ocultas = {"exec", "suid", "dev"}
    if punto == "/proc":
        ocultas |= {"hidepid=0", "hidepid=off", "gid=0"}
    return [_tamano_en_k(o) if o.startswith("size=") else o
            for o in opciones if o not in ocultas]


def _fstab_opciones(punto: str):
    fstab = ROOT / "etc" / "fstab"
    if not fstab.exists():
        return None
    encontradas = None
    for linea in fstab.read_text(encoding="utf-8").splitlines():
        campos = linea.split()
        if len(campos) >= 4 and not campos[0].startswith("#") and campos[1] == punto:
            encontradas = campos[3]
    return encontradas


def mount() -> int:
    opciones, posicionales, i = "", [], 0
    while i < len(ARGS):
        if ARGS[i] == "-o":
            opciones, i = ARGS[i + 1], i + 2
        elif ARGS[i].startswith("-"):
            i += 1
        else:
            posicionales.append(ARGS[i])
            i += 1
    lista = opciones.split(",") if opciones else []
    if "remount" not in lista:
        return 0                                     # solo se simula remount
    punto = posicionales[-1]
    montajes = _cargar("mounts", {})
    if punto not in montajes:
        print(f"mount: {punto}: not mounted", file=sys.stderr)
        return 32
    if punto in _cargar("fallos", {}).get("mount", []):
        print(f"mount: {punto}: permission denied (simulado)", file=sys.stderr)
        return 32
    nuevas = [o for o in lista if o != "remount"]
    de_fstab = _fstab_opciones(punto)
    if de_fstab is not None:
        nuevas = de_fstab.split(",") + nuevas        # fstab primero, -o gana
    elif not nuevas:
        return 0                                     # conserva las actuales
    montajes[punto] = _normalizar(punto, _combinar(montajes[punto], nuevas))
    _guardar("mounts", montajes)
    return 0


def findmnt() -> int:
    salida_opciones = "-o" in ARGS and "OPTIONS" in ARGS
    destinos = [a for a in ARGS if a.startswith("/")]
    montajes = _cargar("mounts", {})
    if not destinos or destinos[-1] not in montajes:
        return 1
    punto = destinos[-1]
    opciones = ",".join(montajes[punto])
    print(opciones if salida_opciones else f"{punto} tmpfs tmpfs {opciones}")
    return 0


# ── servicios ───────────────────────────────────────────────────────────────
def systemctl() -> int:
    banderas = [a for a in ARGS if a.startswith("-")]
    resto = [a for a in ARGS if not a.startswith("-")]
    if not resto:
        return 0
    accion = resto[0]
    unidades = [u.removesuffix(".service") for u in resto[1:]]
    estado = _cargar("units", {})

    def u(nombre):
        return estado.setdefault(nombre, {"enabled": False, "active": False, "masked": False})

    ahora = "--now" in banderas
    silencio = "--quiet" in banderas or "-q" in banderas
    fallan = _cargar("fallos", {}).get("systemctl", [])
    if accion in ("enable", "start", "restart", "reload") and any(n in fallan for n in unidades):
        print(f"Job for {unidades[0]}.service failed (simulado).", file=sys.stderr)
        return 1
    if accion == "reload":
        for nombre in unidades:
            if not estado.get(nombre, {}).get("active"):
                print(f"{nombre}.service is not active, cannot reload.", file=sys.stderr)
                return 1
        return 0
    if accion in ("is-active", "is-enabled"):
        nombre = unidades[0] if unidades else ""
        datos = estado.get(nombre, {"enabled": False, "active": False})
        si = datos["active"] if accion == "is-active" else datos["enabled"]
        if not silencio:
            if accion == "is-active":
                print("active" if si else "inactive")
            else:
                print("enabled" if si else "disabled")
        return 0 if si else (3 if accion == "is-active" else 1)
    for nombre in unidades:
        d = u(nombre)
        if accion == "enable":
            d["enabled"] = True
            d["active"] = d["active"] or ahora
        elif accion == "disable":
            d["enabled"] = False
            d["active"] = d["active"] and not ahora
        elif accion in ("start", "restart"):
            d["active"] = True
        elif accion == "stop":
            d["active"] = False
        elif accion == "mask":
            d["masked"] = True
        elif accion == "unmask":
            d["masked"] = False
    _guardar("units", estado)
    return 0


SERVICIO_DEL_PAQUETE = {"fail2ban": "fail2ban", "unattended-upgrades": "unattended-upgrades",
                        "apparmor": "apparmor"}


def apt_get() -> int:
    if "install" in ARGS:
        paquetes = _cargar("pkgs", [])
        unidades = _cargar("units", {})
        idx = ARGS.index("install")
        for p in ARGS[idx + 1:]:
            if not p.startswith("-") and p not in paquetes:
                paquetes.append(p)
                if p in SERVICIO_DEL_PAQUETE:
                    unidades[SERVICIO_DEL_PAQUETE[p]] = {"enabled": True, "active": True, "masked": False}
        _guardar("pkgs", paquetes)
        _guardar("units", unidades)
    return 0


def dpkg_query() -> int:
    nombre = ARGS[-1] if ARGS else ""
    if nombre in _cargar("pkgs", []):
        if any(a.startswith("-f") or a.startswith("--showformat") for a in ARGS):
            print("install ok installed", end="")
        else:
            print(f"{nombre}\t1.0")
        return 0
    print(f"dpkg-query: no packages found matching {nombre}", file=sys.stderr)
    return 1


# ── AppArmor (sobre <root>/etc/apparmor.d) ──────────────────────────────────
AA_DIR = ROOT / "etc" / "apparmor.d"
CABECERA = re.compile(r"^(?P<ind>\s*)(?P<cab>[^#\s][^#]*?)"
                      r"(?:\s+(?:flags\s*=\s*)?\((?P<banderas>[^)]*)\))?\s*\{(?P<resto>\s*(?:#.*)?)$")
# las banderas de modo que quita cada herramienta (aa.py: set_enforce, set_complain)
QUITA = {"enforce": {"complain", "kill", "unconfined", "prompt", "default_allow"},
         "complain": {"enforce", "kill", "unconfined", "prompt", "default_allow"}}


def _banderas(archivo: Path) -> set:
    res = set()
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        m = CABECERA.match(linea)
        if m and m["banderas"]:
            res |= {b.strip() for b in m["banderas"].split(",") if b.strip()}
    return res


def _reescribir_cabeceras(archivo: Path, modo: str) -> None:
    salida = []
    for linea in archivo.read_text(encoding="utf-8").splitlines(keepends=True):
        m = CABECERA.match(linea.rstrip("\n"))
        if m:
            banderas = [b.strip() for b in (m["banderas"] or "").split(",") if b.strip()]
            banderas = [b for b in banderas if b not in QUITA[modo]]
            if modo == "complain" and "complain" not in banderas:
                banderas.append("complain")
            linea = m["ind"] + m["cab"].rstrip()
            if banderas:
                linea += " flags=(" + ", ".join(banderas) + ")"
            linea += " {" + m["resto"] + "\n"
        salida.append(linea)
    archivo.write_text("".join(salida), encoding="utf-8")


def _modo_al_cargar(archivo: Path, forzar_complain: bool) -> str:
    banderas = _banderas(archivo)
    if forzar_complain or "complain" in banderas:
        return "complain"
    if "unconfined" in banderas:
        return "unconfined"
    return "enforce"


def aa_modo(modo: str) -> int:
    perfiles = _cargar("aa", {})
    fallan = _cargar("fallos", {}).get(f"aa-{modo}", [])
    for arg in [a for a in ARGS if not a.startswith("-")]:
        archivo = Path(arg)
        for sub in ("disable", "force-complain") if modo == "enforce" else ("disable",):
            enlace = AA_DIR / sub / archivo.name
            if enlace.is_symlink():
                enlace.unlink()
        _reescribir_cabeceras(archivo, modo)
        if archivo.name in fallan:
            _guardar("aa", perfiles)
            print(f"apparmor_parser: no se pudo recargar {arg} (simulado)", file=sys.stderr)
            return 1
        perfiles[archivo.name] = _modo_al_cargar(archivo, False)
    _guardar("aa", perfiles)
    return 0


def apparmor_parser() -> int:
    perfiles = _cargar("aa", {})
    descargar = "-R" in ARGS or "--remove" in ARGS
    complain = "-C" in ARGS or "--Complain" in ARGS
    for arg in [a for a in ARGS if not a.startswith("-")]:
        archivo = Path(arg)
        if descargar:
            if archivo.name not in perfiles:
                print(f"apparmor_parser: {archivo.name} no está cargado", file=sys.stderr)
                return 1
            del perfiles[archivo.name]
        else:
            perfiles[archivo.name] = _modo_al_cargar(archivo, complain)
    _guardar("aa", perfiles)
    return 0


def aa_enabled() -> int:
    if _cargar("fallos", {}).get("aa-enabled"):
        if "--quiet" not in ARGS and "-q" not in ARGS:
            print("No - disabled at boot.")
        return 1
    if "--quiet" not in ARGS and "-q" not in ARGS:
        print("Yes")
    return 0


# ── usuarios y grupos (sobre <root>/etc/passwd y <root>/etc/group) ──────────
def _lineas(nombre: str) -> list:
    p = ROOT / "etc" / nombre
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def getent() -> int:
    if len(ARGS) < 2 or ARGS[0] not in ("group", "passwd"):
        return 2
    for linea in _lineas(ARGS[0]):
        if linea.split(":")[0] == ARGS[1]:
            print(linea)
            return 0
    return 2


def groupadd() -> int:
    nombre = ARGS[-1]
    grupos = _lineas("group")
    if any(g.split(":")[0] == nombre for g in grupos):
        return 9
    gid = max([int(g.split(":")[2]) for g in grupos] + [999]) + 1
    grupos.append(f"{nombre}:x:{gid}:")
    (ROOT / "etc" / "group").write_text("\n".join(grupos) + "\n", encoding="utf-8")
    return 0


def _escribir_grupos(grupos: list) -> None:
    (ROOT / "etc" / "group").write_text("\n".join(grupos) + "\n", encoding="utf-8")


def groupdel() -> int:
    nombre = ARGS[-1]
    grupos = _lineas("group")
    linea = next((g for g in grupos if g.split(":")[0] == nombre), None)
    if linea is None:
        print(f"groupdel: group '{nombre}' does not exist", file=sys.stderr)
        return 6
    gid = linea.split(":")[2]
    if any(u.split(":")[3] == gid for u in _lineas("passwd")):
        print("groupdel: cannot remove the primary group of a user", file=sys.stderr)
        return 8
    _escribir_grupos([g for g in grupos if g != linea])
    return 0


def gpasswd() -> int:
    # solo gpasswd -d USUARIO GRUPO, lo que usa Lockd
    if len(ARGS) != 3 or ARGS[0] != "-d":
        return 2
    usuario, grupo = ARGS[1], ARGS[2]
    grupos = _lineas("group")
    for i, g in enumerate(grupos):
        campos = g.split(":")
        if campos[0] == grupo:
            miembros = [m for m in campos[3].split(",") if m]
            if usuario not in miembros:
                print(f"gpasswd: user '{usuario}' is not a member of '{grupo}'", file=sys.stderr)
                return 3
            campos[3] = ",".join(m for m in miembros if m != usuario)
            grupos[i] = ":".join(campos)
            _escribir_grupos(grupos)
            return 0
    print(f"gpasswd: group '{grupo}' does not exist", file=sys.stderr)
    return 3


def usermod() -> int:
    grupo = None
    for i, a in enumerate(ARGS):
        if a in ("-aG", "-G") and i + 1 < len(ARGS):
            grupo = ARGS[i + 1]
    usuario = ARGS[-1]
    grupos = _lineas("group")
    for i, g in enumerate(grupos):
        campos = g.split(":")
        if campos[0] == grupo:
            miembros = [m for m in campos[3].split(",") if m]
            if usuario not in miembros:
                miembros.append(usuario)
            campos[3] = ",".join(miembros)
            grupos[i] = ":".join(campos)
            (ROOT / "etc" / "group").write_text("\n".join(grupos) + "\n", encoding="utf-8")
            return 0
    return 6


def id_() -> int:
    usuario = ARGS[-1] if ARGS else ""
    if any(linea.split(":")[0] == usuario for linea in _lineas("passwd")):
        print(f"uid=1(x) gid=1({usuario})")
        return 0
    print(f"id: '{usuario}': no such user", file=sys.stderr)
    return 1


def centinela() -> int:
    print("ok")
    return 0


COMANDOS = {
    "mount": mount, "findmnt": findmnt, "systemctl": systemctl,
    "apt-get": apt_get, "dpkg-query": dpkg_query, "aa-enforce": lambda: aa_modo("enforce"),
    "aa-complain": lambda: aa_modo("complain"), "apparmor_parser": apparmor_parser,
    "aa-enabled": aa_enabled, "getent": getent,
    "groupadd": groupadd, "groupdel": groupdel, "usermod": usermod,
    "gpasswd": gpasswd, "id": id_,
    "fail2ban-client": lambda: 0, "lockd-stubs": centinela,
}

if __name__ == "__main__":
    _log()
    sys.exit(COMANDOS[NAME]())
