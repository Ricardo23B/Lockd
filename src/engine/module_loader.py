"""
engine/module_loader.py — carga y valida modules.yaml

Devuelve List[ModuleDefinition] con rutas absolutas y metadatos completos.
Verifica dependencias del sistema y compatibilidad con la distro activa.
"""
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    import yaml
except ImportError:
    raise SystemExit("Falta PyYAML: sudo apt install python3-yaml")

log = logging.getLogger("lt.loader")  # legacy name kept

KNOWN_RISK_LEVELS      = {"low", "medium", "high"}
SUPPORTED_SECURITY_LEVELS  = {"basic", "advanced", "expert", "paranoid"}
MODULE_MODULE_CATEGORIES       = {
    "network", "filesystem", "kernel",
    "services", "access_control", "system_hardening", "privacy",
}


# NOTE: loader grew too much, should probably split this later
# NOTE: loader grew too much, should probably split this later
class LoaderError(Exception):
    """Error al cargar o validar modules.yaml."""


@dataclass
class ModuleDefinition:
    # campos del YAML
    id:               str
    name:             str
    description:      str
    category:         str
    security_level:   str
    risk_level:       str
    requires_reboot:  bool
    impact:           str
    server_safe:      bool
    desktop_safe:     bool
    enable_script:    Optional[Path]
    disable_script:   Optional[Path]
    check_script:     Optional[Path]
    dependencies:     List[str] = field(default_factory=list)
    supported_distros: List[str] = field(default_factory=list)

    # calculados en tiempo de carga
    deps_ok:      bool       = True
    missing_deps: List[str]  = field(default_factory=list)
    distro_ok:    bool       = True

    def __post_init__(self):
        if self.risk_level not in KNOWN_RISK_LEVELS:
            raise LoaderError(
                f"'{self.id}': risk_level '{self.risk_level}' inválido. "
                f"Valores: {KNOWN_RISK_LEVELS}"
            )
        if self.security_level not in SUPPORTED_SECURITY_LEVELS:
            raise LoaderError(
                f"'{self.id}': security_level '{self.security_level}' inválido. "
                f"Valores: {SUPPORTED_SECURITY_LEVELS}"
            )

    @property
    def available(self) -> bool:
        return self.deps_ok and self.distro_ok

    @property
    def risk_color(self) -> str:
        """Color CSS para la UI según el nivel de riesgo."""
        return {"low": "success", "medium": "warning", "high": "error"}.get(
            self.risk_level, "dim-label"
        )

    @property
    def level_order(self) -> int:
        """Orden numérico del nivel de seguridad (para ordenar y filtrar)."""
        return {"basic": 1, "advanced": 2, "expert": 3, "paranoid": 4}.get(
            self.security_level, 0
        )


class ModuleLoader:
    """Lee modules.yaml y devuelve módulos validados."""

    def __init__(self, yaml_path: Path, base_dir: Path):
        self.yaml_path = yaml_path
        self.base_dir  = base_dir.resolve()

    def load(self) -> List[ModuleDefinition]:
        raw     = self._read_yaml()
        entries = raw.get("modules", [])
        if not isinstance(entries, list):
            raise LoaderError("modules.yaml debe tener una lista 'modules:'")

        result: List[ModuleDefinition] = []
        seen:   set[str] = set()

        for i, entry in enumerate(entries):
            try:
                mod = self._parse_entry(entry)
            except LoaderError as e:
                raise LoaderError(f"Entrada #{i}: {e}") from e

            if mod.id in seen:
                raise LoaderError(f"ID duplicado: '{mod.id}'")
            seen.add(mod.id)

            self._check_deps(mod)
            self._check_distro(mod)
            result.append(mod)
            log.debug(f"  ✓ {mod.id} (cat={mod.category} level={mod.security_level})")

        log.info(f"Módulos cargados: {len(result)}")
        return result

    # -- parseo ---------------------------------------------------------------

    def _read_yaml(self) -> dict:
        if not self.yaml_path.exists():
            raise LoaderError(f"No existe: {self.yaml_path}")
        try:
            with open(self.yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise LoaderError(f"Error YAML: {e}")

    def _parse_entry(self, e: dict) -> ModuleDefinition:
        if not isinstance(e, dict):
            raise LoaderError("Entrada debe ser un mapping YAML")

        def req(k: str) -> str:
            v = e.get(k)
            if v is None:
                raise LoaderError(f"Campo obligatorio faltante: '{k}'")
            return str(v).strip()

        def opt(k: str, default="") -> str:
            return str(e.get(k, default)).strip()

        def path(k: str) -> Optional[Path]:
            v = e.get(k)
            if not v:
                return None
            p = (self.base_dir / str(v)).resolve()
            if not p.exists():
                log.warning(f"Script no encontrado: {p}")
            return p

        mod_id = req("id")
        if not mod_id.replace("_", "").isalnum():
            raise LoaderError(f"id '{mod_id}' inválido (solo a-z, 0-9, _)")

        return ModuleDefinition(
            id               = mod_id,
            name             = req("name"),
            description      = opt("description"),
            category         = opt("category", "system_hardening"),
            security_level   = opt("security_level", "advanced"),
            risk_level       = opt("risk_level", "medium"),
            requires_reboot  = bool(e.get("requires_reboot", False)),
            impact           = opt("impact"),
            server_safe      = bool(e.get("server_safe", True)),
            desktop_safe     = bool(e.get("desktop_safe", True)),
            enable_script    = path("enable_script"),
            disable_script   = path("disable_script"),
            check_script     = path("check_script"),
            dependencies     = list(e.get("dependencies") or []),
            supported_distros = list(e.get("supported_distros") or []),
        )

    # -- validaciones ---------------------------------------------------------

    def _check_deps(self, mod: ModuleDefinition) -> None:
        missing = []
        for dep in mod.dependencies:
            if shutil.which(dep):
                continue
            r = subprocess.run(
                ["dpkg", "-s", dep], capture_output=True, text=True
            )
            if r.returncode != 0:
                missing.append(dep)
        if missing:
            mod.deps_ok      = False
            mod.missing_deps = missing
            log.warning(f"'{mod.id}': dependencias faltantes: {missing}")

    def _check_distro(self, mod: ModuleDefinition) -> None:
        if not mod.supported_distros:
            return
        from src.engine.distro_detector import is_supported
        if not is_supported(mod.supported_distros):
            mod.distro_ok = False
            log.warning(f"'{mod.id}': no soportado en esta distro")
