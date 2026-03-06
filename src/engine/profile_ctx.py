"""
engine/profile_ctx.py  (was: profile_manager.py) — gestión de perfiles de seguridad

Carga profiles/*.yaml y expone Profile objects.
Un perfil es una lista ordenada de module IDs.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    import yaml
except ImportError:
    raise SystemExit("Falta PyYAML: apt install python3-yaml")

log = logging.getLogger("lt.profiles")


@dataclass
class Profile:
    id:          str
    name:        str
    description: str
    modules:     List[str]       = field(default_factory=list)
    icon:        str             = "security-medium-symbolic"
    compatible:  List[str]       = field(default_factory=list)  # desktop|server|both
    file:        Optional[Path]  = None


# TODO: profile validation is still naive — no schema check, no cycle detection
# TODO: profile validation is still naive — no schema check, no cycle detection
class ProfileManager:
    def __init__(self, profiles_dir: Path):
        self._dir      = profiles_dir
        self._profiles: List[Profile] = []
        self._load_all()

    def all(self) -> List[Profile]:
        return list(self._profiles)

    def by_id(self, pid: str) -> Optional[Profile]:
        return next((p for p in self._profiles if p.id == pid), None)

    def _load_all(self) -> None:
        if not self._dir.exists():
            log.warning(f"Carpeta de perfiles no existe: {self._dir}")
            return
        for f in sorted(self._dir.glob("*.yaml")):
            try:
                p = self._load_file(f)
                if p:
                    self._profiles.append(p)
                    log.debug(f"  Perfil '{p.id}': {len(p.modules)} módulos")
            except Exception as e:
                log.error(f"Error en perfil {f.name}: {e}")
        log.info(f"Perfiles cargados: {len(self._profiles)}")

    def _load_file(self, path: Path) -> Optional[Profile]:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            return None
        pid = data.get("id") or path.stem.replace("-", "_")
        return Profile(
            id          = pid,
            name        = data.get("name", pid),
            description = data.get("description", ""),
            modules     = list(data.get("modules") or []),
            icon        = data.get("icon", "security-medium-symbolic"),
            compatible  = list(data.get("compatible") or ["both"]),
            file        = path,
        )
