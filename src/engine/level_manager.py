"""
engine/level_manager.py — gestiona los niveles de seguridad de hardening

Niveles: basic → advanced → expert → paranoid
Cada nivel incluye todos los módulos de los niveles anteriores (acumulativo).

Los módulos de cada nivel se determinan leyendo el campo security_level
de cada módulo en modules.yaml — no hay lista hardcodeada aquí.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict

from src.engine.module_loader import ModuleDefinition

log = logging.getLogger("lockd.levels")

LEVELS = ["basic", "advanced", "expert", "paranoid"]
LEVEL_LABELS = {
    "basic":    "Básico",
    "advanced": "Avanzado",
    "expert":   "Experto",
    "paranoid": "Paranoico",
}
LEVEL_DESCRIPTIONS = {
    "basic":    "Medidas esenciales para cualquier sistema. Firewall, updates, Fail2ban.",
    "advanced": "Hardening del kernel, SSH estricto, protección de /tmp y /proc.",
    "expert":   "AppArmor, lista negra de módulos kernel, restricción de SUID.",
    "paranoid": "Máxima restricción. USB bloqueado, memoria compartida, compiladores.",
}
LEVEL_ICONS = {
    "basic":    "security-low-symbolic",
    "advanced": "security-medium-symbolic",
    "expert":   "security-high-symbolic",
    "paranoid": "security-high-symbolic",
}


@dataclass
class SecurityLevel:
    id:          str
    label:       str
    description: str
    icon:        str
    modules:     List[str] = field(default_factory=list)      # ids de este nivel
    cumulative:  List[str] = field(default_factory=list)      # + todos los anteriores


class LevelManager:
    """Calcula qué módulos pertenecen a cada nivel de seguridad."""

    def __init__(self, modules: List[ModuleDefinition]):
        self._levels = self._build(modules)

    def all(self) -> List[SecurityLevel]:
        return list(self._levels.values())

    def get(self, level_id: str) -> SecurityLevel | None:
        return self._levels.get(level_id)

    def modules_for_level(self, level_id: str) -> List[str]:
        """Devuelve IDs de módulos acumulativos hasta ese nivel (inclusive)."""
        lvl = self._levels.get(level_id)
        return lvl.cumulative if lvl else []

    def _build(self, modules: List[ModuleDefinition]) -> Dict[str, SecurityLevel]:
        # agrupar módulos por su nivel
        by_level: Dict[str, List[str]] = {lv: [] for lv in LEVELS}
        for mod in modules:
            if mod.security_level in by_level:
                by_level[mod.security_level].append(mod.id)

        result: Dict[str, SecurityLevel] = {}
        cumulative: List[str] = []

        for lv in LEVELS:
            own_modules = by_level[lv]
            cumulative  = cumulative + own_modules
            result[lv]  = SecurityLevel(
                id          = lv,
                label       = LEVEL_LABELS[lv],
                description = LEVEL_DESCRIPTIONS[lv],
                icon        = LEVEL_ICONS[lv],
                modules     = list(own_modules),
                cumulative  = list(cumulative),
            )
            log.debug(f"Nivel '{lv}': {len(own_modules)} módulos propios, "
                      f"{len(cumulative)} acumulados")
        return result
