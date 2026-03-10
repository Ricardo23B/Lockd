"""
app/controller.py — controlador central de lockd

Conecta el engine con las interfaces (GUI y CLI).
Centraliza la lógica de negocio: aplicar perfiles, aplicar niveles,
habilitar/deshabilitar módulos, ejecutar scan.

Tanto la GUI como la CLI delegan en este controlador.
"""
import logging
from pathlib import Path
from typing import Callable, List, Optional

from src.engine.module_loader import ModuleDefinition, ModuleLoader
from src.engine.executor import Executor, ExecResult
from src.engine.scanner import SecurityReport, run_scan
from src.engine.state_runtime import StateManager
from src.engine.profile_ctx import ProfileManager, Profile
from src.engine.level_manager import LevelManager, SecurityLevel
from src.engine.distro_detector import detect as detect_distro

log = logging.getLogger("lockd.ctrl")

APP_DIR      = Path(__file__).resolve().parent.parent.parent
MODULES_DIR  = APP_DIR / "modules"
PROFILES_DIR = APP_DIR / "profiles"
STATE_FILE   = Path.home() / ".config" / "lockd" / "state.json"


class Controller:
    """
    API pública de lockd.

    Ambas interfaces (GUI y CLI) usan este mismo controlador para
    garantizar comportamiento consistente y no duplicar lógica.
    """

    def __init__(
        self,
        modules_dir:  Path = MODULES_DIR,
        profiles_dir: Path = PROFILES_DIR,
        state_file:   Path = STATE_FILE,
        dry_run:      bool = False,
    ):
        self.dry_run = dry_run

        # engine
        loader       = ModuleLoader(modules_dir / "modules.yaml", modules_dir)
        self.modules: List[ModuleDefinition] = loader.load()
        self._mod_map = {m.id: m for m in self.modules}

        self.state    = StateManager(state_file)
        self.executor = Executor(self.state, dry_run=dry_run)
        self.profiles = ProfileManager(profiles_dir)
        self.levels   = LevelManager(self.modules)

        distro = detect_distro()
        log.info(
            f"Controller listo — {len(self.modules)} módulos, "
            f"distro={distro['pretty']}, dry_run={dry_run}"
        )

    # ── Módulos individuales ──────────────────────────────────────────────

    def get_module(self, module_id: str) -> Optional[ModuleDefinition]:
        return self._mod_map.get(module_id)

    def module_state(self, module_id: str) -> str:
        return self.state.get(module_id)

    def is_enabled(self, module_id: str) -> bool:
        return self.state.is_enabled(module_id)

    def enable(
        self,
        module_id: str,
        on_complete: Optional[Callable[[ExecResult], None]] = None,
    ) -> Optional[ExecResult]:
        """
        Activa un módulo.
        - on_complete=None  → modo síncrono (CLI): bloquea y devuelve ExecResult
        - on_complete=fn    → modo asíncrono (GUI): llama fn al terminar
        """
        if not self._is_valid_id(module_id):
            log.error(f"ID inválido: '{module_id}'")
            return None
        mod = self._get_or_fail(module_id)
        if not mod:
            return None
        self._warn_if_desktop_unsafe(mod)
        return self._run(mod, enable=True, on_complete=on_complete)

    def disable(
        self,
        module_id: str,
        on_complete: Optional[Callable[[ExecResult], None]] = None,
    ) -> Optional[ExecResult]:
        mod = self._get_or_fail(module_id)
        if not mod:
            return None
        return self._run(mod, enable=False, on_complete=on_complete)

    def simulate(self, module_id: str, enable: bool = True) -> ExecResult:
        """Ejecuta en modo dry-run independientemente de la configuración global."""
        mod = self._get_or_fail(module_id)
        if not mod:
            raise ValueError(f"Módulo no encontrado: {module_id}")
        script = mod.enable_script if enable else mod.disable_script
        # guardar y restaurar dry_run temporal
        orig = self.executor.dry_run
        self.executor.dry_run = True
        result = self.executor.run(module_id, script, enable)
        self.executor.dry_run = orig
        return result

    # ── Perfiles ─────────────────────────────────────────────────────────

    def apply_profile(
        self,
        profile_id: str,
        on_step: Optional[Callable[[ExecResult, int, int], None]] = None,
    ) -> List[ExecResult]:
        """
        Aplica un perfil completo de forma síncrona.
        Activa los módulos incluidos, desactiva los que no estén.
        on_step(result, step_n, total) — callback de progreso opcional.
        """
        profile = self.profiles.by_id(profile_id)
        if not profile:
            raise ValueError(f"Perfil no encontrado: {profile_id}")

        log.info(f"Aplicando perfil '{profile.name}' ({len(profile.modules)} módulos)")
        queue   = self._build_profile_queue(profile)
        results = []

        for i, (mid, script, enable) in enumerate(queue):
            r = self.executor.run(mid, script, enable)
            results.append(r)
            if on_step:
                on_step(r, i + 1, len(queue))
            if r.cancelled:
                log.warning("Perfil cancelado por el usuario.")
                break
        return results

    def apply_profile_async(
        self,
        profile_id: str,
        on_step: Callable[[ExecResult, int, int], None],
        on_done: Callable[[List[ExecResult]], None],
    ) -> None:
        """Aplica un perfil en hilo daemon, ideal para GUI."""
        import threading
        profile = self.profiles.by_id(profile_id)
        if not profile:
            raise ValueError(f"Perfil no encontrado: {profile_id}")

        queue = self._build_profile_queue(profile)
        results: List[ExecResult] = []
        total = len(queue)

        def _run():
            for i, (mid, script, enable) in enumerate(queue):
                r = self.executor.run(mid, script, enable)
                results.append(r)
                on_step(r, i + 1, total)
                if r.cancelled:
                    break
            on_done(results)

        threading.Thread(target=_run, daemon=True, name="lt-profile").start()

    # ── Niveles de seguridad ──────────────────────────────────────────────

    def apply_level(
        self,
        level_id: str,
        on_step: Optional[Callable[[ExecResult, int, int], None]] = None,
    ) -> List[ExecResult]:
        """Aplica todos los módulos hasta el nivel dado (acumulativo)."""
        mod_ids = self.levels.modules_for_level(level_id)
        if not mod_ids:
            raise ValueError(f"Nivel no encontrado: {level_id}")

        log.info(f"Aplicando nivel '{level_id}' ({len(mod_ids)} módulos)")
        results = []
        for i, mid in enumerate(mod_ids):
            mod = self._mod_map.get(mid)
            if not mod or not mod.enable_script:
                continue
            r = self.executor.run(mid, mod.enable_script, enable=True)
            results.append(r)
            if on_step:
                on_step(r, i + 1, len(mod_ids))
            if r.cancelled:
                break
        return results

    # ── Scan ─────────────────────────────────────────────────────────────

    def scan(self) -> SecurityReport:
        """Ejecuta el Security Scan y devuelve el reporte."""
        log.info("Iniciando Security Scan...")
        return run_scan()

    # ── Info ─────────────────────────────────────────────────────────────

    def modules_by_category(self) -> dict[str, List[ModuleDefinition]]:
        cats: dict[str, List[ModuleDefinition]] = {}
        for m in self.modules:
            cats.setdefault(m.category, []).append(m)
        return cats

    def modules_by_level(self, level_id: str) -> List[ModuleDefinition]:
        return [m for m in self.modules if m.security_level == level_id]

    # ── Privado ───────────────────────────────────────────────────────────

    # --- pequeña validación que debería estar en module_loader pero acabó aquí ---
    def _is_valid_id(self, module_id: str) -> bool:
        """Sanity check básico de formato de ID. Duplica parte de lo que hace el loader."""
        return bool(module_id) and module_id.replace("_", "").isalnum()

    def _warn_if_desktop_unsafe(self, mod: ModuleDefinition) -> None:
        """Aviso rápido si se activa un módulo no recomendado en desktop."""
        if not mod.desktop_safe:
            log.warning(f"'{mod.id}' marcado como no seguro para desktop — aplicando igual")

    def _get_or_fail(self, module_id: str) -> Optional[ModuleDefinition]:
        mod = self._mod_map.get(module_id)
        if not mod:
            log.error(f"Módulo no encontrado: '{module_id}'")
        return mod

    def _run(self, mod: ModuleDefinition, enable: bool,
             on_complete: Optional[Callable]) -> Optional[ExecResult]:
        script = mod.enable_script if enable else mod.disable_script
        if on_complete:
            self.executor.run_async(mod.id, script, enable, on_complete)
            return None
        return self.executor.run(mod.id, script, enable)

    def _build_profile_queue(self, profile: Profile):
        """Construye la cola de tareas para un perfil: activa los incluidos, desactiva los demás."""
        queue = []
        for mid, mod in self._mod_map.items():
            enable = mid in profile.modules
            script = mod.enable_script if enable else mod.disable_script
            if script and script.exists():
                queue.append((mid, script, enable))
        return queue
