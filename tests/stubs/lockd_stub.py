#!/usr/bin/env python3
"""
tests/stubs/lockd_stub.py — Comandos del sistema simulados para el modo test

Un solo programa que se comporta según el nombre con el que lo invocan
(mount, findmnt, systemctl, apt-get, aa-enforce, aa-complain, getent,
groupadd, usermod, id, fail2ban-client). Los tests lo copian a
$LOCKD_SYSROOT/.stubs/bin/<comando>, junto con el centinela lockd-stubs:
_common.sh lo ejecuta antes de nada (si no responde "ok", aborta) y deja el
PATH solo en ese directorio.

El estado simulado vive en $LOCKD_SYSROOT/.stubs/state/*.json y cada llamada
queda en $LOCKD_SYSROOT/.stubs/calls.log. Los archivos (/etc/group, /etc/fstab,
...) son los del árbol de prueba. La semántica imita lo que importa para
revertir:
  - mount -o remount,OPCIONES PUNTO combina las opciones con las actuales;
  - mount -o remount PUNTO, sin opciones, toma las de fstab si el punto figura
    ahí y, si no, conserva las actuales, como mount(8);
  - systemctl recuerda enabled, active y masked por unidad.
"""
import json
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
    nuevas = [o for o in lista if o != "remount"]
    if not nuevas:
        de_fstab = _fstab_opciones(punto)
        if de_fstab is None:
            return 0                                 # conserva las actuales
        nuevas = de_fstab.split(",")
    montajes[punto] = _combinar(montajes[punto], nuevas)
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


def apt_get() -> int:
    if "install" in ARGS:
        paquetes = _cargar("pkgs", [])
        idx = ARGS.index("install")
        for p in ARGS[idx + 1:]:
            if not p.startswith("-") and p not in paquetes:
                paquetes.append(p)
        _guardar("pkgs", paquetes)
    return 0


def aa_modo(modo: str) -> int:
    perfiles = _cargar("aa", {})
    for archivo in ARGS:
        perfiles[Path(archivo).name] = modo
    _guardar("aa", perfiles)
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
    "apt-get": apt_get, "aa-enforce": lambda: aa_modo("enforce"),
    "aa-complain": lambda: aa_modo("complain"), "getent": getent,
    "groupadd": groupadd, "usermod": usermod, "id": id_,
    "fail2ban-client": lambda: 0, "lockd-stubs": centinela,
}

if __name__ == "__main__":
    _log()
    sys.exit(COMANDOS[NAME]())
