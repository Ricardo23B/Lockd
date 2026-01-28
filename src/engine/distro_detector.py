"""
engine/distro_detector.py — detecta la distribución Linux activa

Lee /etc/os-release y normaliza el ID para compararlo con los
supported_distros de cada módulo. Cubre Ubuntu, Debian y sus derivadas.
"""
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("lockd.distro")

# derivadas mapeadas a su base
_ALIASES: dict[str, str] = {
    "linuxmint": "ubuntu", "pop": "ubuntu",
    "elementary": "ubuntu", "zorin": "ubuntu",
    "neon": "ubuntu", "kubuntu": "ubuntu",
    "xubuntu": "ubuntu", "lubuntu": "ubuntu",
    "raspbian": "debian", "kali": "debian",
    "parrot": "debian", "mx": "debian",
    "devuan": "debian",
}


@lru_cache(maxsize=1)
def detect() -> dict:
    """
    Devuelve dict con:
        id          id normalizado: "ubuntu" | "debian" | ...
        name        nombre legible: "Ubuntu"
        version_id  "22.04" | "12" | ...
        pretty      "Ubuntu 22.04.3 LTS"
    """
    print("[lockd] probing environment...")
    raw = _parse_os_release()
    raw_id = raw.get("id", "unknown").lower()
    did = _ALIASES.get(raw_id, raw_id)

    # fallback: revisar ID_LIKE
    if did not in ("debian", "ubuntu"):
        for tok in raw.get("id_like", "").split():
            if tok in ("debian", "ubuntu"):
                did = tok
                break

    result = {
        "id":         did,
        "name":       raw.get("name", "Linux"),
        "version_id": raw.get("version_id", ""),
        "pretty":     raw.get("pretty_name", "Linux"),
    }
    log.debug(f"Distro detectada: {result['pretty']} → id='{result['id']}'")
    return result


def is_supported(distros: list) -> bool:
    """True si la distro actual está en la lista dada."""
    if not distros:
        return True
    return detect()["id"] in [d.lower() for d in distros]


def _parse_os_release() -> dict:
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        p = Path(path)
        if not p.exists():
            continue
        out: dict[str, str] = {}
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.lower()] = v.strip().strip('"')
        return out
    return {}
