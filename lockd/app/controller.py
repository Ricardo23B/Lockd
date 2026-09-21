"""
app/controller.py — controlador central de lockd

Conecta el engine con las interfaces (GUI y CLI).
Centraliza la lógica de negocio: aplicar perfiles, aplicar niveles,
habilitar/deshabilitar módulos, ejecutar scan.

Tanto la GUI como la CLI delegan en este controlador.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

from lockd.engine.module_loader import ModuleDefinition, ModuleLoader
from lockd.engine.executor import Executor, ExecResult
from lockd.engine.scanner import SecurityReport, run_scan
from lockd.engine.state_runtime import StateManager
from lockd.engine.profile_ctx import ProfileManager, Profile
from lockd.engine.level_manager import LevelManager
from lockd.engine.distro_detector import detect as detect_distro

log = logging.getLogger("lockd.ctrl")

def _data_dirs() -> tuple[Path, Path]:
    """Localiza modules/ y profiles/.

    Dev (checkout): viven en la raíz del repo, junto a este paquete.
    Instalado: ruta FHS root-owned — la misma que valida el helper
    privilegiado (/usr/lib/lockd/modules). LOCKD_DATA_DIR permite reubicar
    en otras distros sin parchear; el helper NO lee esa variable (su
    frontera de seguridad nunca depende del entorno).
    """
    dev_root = Path(__file__).resolve().parent.parent.parent
    if (dev_root / "modules" / "modules.yaml").is_file():
        return dev_root / "modules", dev_root / "profiles"
    root = Path(os.environ.get("LOCKD_DATA_DIR", "/usr/lib/lockd"))
    return root / "modules", root / "profiles"


MODULES_DIR, PROFILES_DIR = _data_dirs()
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
        verify_on_init: bool = True,
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

        # Reconciliar el estado registrado con el sistema REAL al arrancar.
        # state.json es por usuario y puede mentir (otro usuario aplicó
        # módulos, o alguien tocó la config a mano); los check scripts son
        # la fuente de verdad. verify_on_init=False solo para tests.
        if verify_on_init:
            self.refresh_states()

    # ── Módulos individuales ──────────────────────────────────────────────

    def get_module(self, module_id: str) -> Optional[ModuleDefinition]:
        return self._mod_map.get(module_id)

    def module_state(self, module_id: str) -> str:
        return self.state.get(module_id)

    def is_enabled(self, module_id: str) -> bool:
        return self.state.is_enabled(module_id)

    # ── Verificación contra el sistema real ──────────────────────────────

    CHECK_TIMEOUT = 10  # segundos por check script

    def verify(self, module_id: str) -> str:
        """
        Ejecuta el check script del módulo (sin privilegios) y devuelve el
        estado REAL del sistema: 'enabled' | 'disabled' | 'unknown'.
        Contrato de exit codes: 0 = activo, 1 = inactivo, 2 = no determinable.
        Cualquier otra cosa (timeout, script ausente, rc inesperado) = unknown.
        """
        mod = self._mod_map.get(module_id)
        if not mod or not mod.check_script or not mod.check_script.exists():
            return "unknown"
        try:
            r = subprocess.run(
                ["bash", str(mod.check_script)],
                capture_output=True, timeout=self.CHECK_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning(f"check de '{module_id}' falló: {e}")
            return "unknown"
        return {0: "enabled", 1: "disabled"}.get(r.returncode, "unknown")

    def refresh_states(self) -> Dict[str, str]:
        """
        Reconcilia state.json con el sistema real, módulo por módulo.
        Un check determinante (0/1) actualiza el estado registrado; un
        'unknown' (2) conserva lo registrado en lugar de inventar.
        Devuelve el estado efectivo de cada módulo.
        """
        effective: Dict[str, str] = {}
        for mid in self._mod_map:
            real     = self.verify(mid)
            recorded = self.state.get(mid)
            if real == "unknown":
                effective[mid] = recorded
                continue
            if real != recorded:
                log.info(f"reconciliación: {mid} '{recorded}' → '{real}' (sistema real)")
                self.state.set(mid, real)
            effective[mid] = real
        return effective

    def _verified(self, result: Optional[ExecResult]) -> Optional[ExecResult]:
        """
        Tras una operación REAL exitosa, contrasta el resultado con el check
        del módulo. Si el script reportó éxito pero el sistema no lo refleja,
        el estado pasa a 'error' — detecta scripts que mienten o fallan
        silenciosamente.
        """
        if not result or result.dry_run or not result.ok:
            return result
        real     = self.verify(result.module_id)
        expected = "enabled" if result.action == "enable" else "disabled"
        if real not in ("unknown", expected):
            log.warning(
                f"'{result.module_id}': el script terminó OK pero el check "
                f"reporta '{real}' (se esperaba '{expected}') — estado: error"
            )
            self.state.set(result.module_id, "error")
        return result

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
        strict: bool = False,
    ) -> List[ExecResult]:
        """
        Aplica un perfil completo de forma síncrona.

        Default ADITIVO: activa los módulos del perfil y no toca el resto.
        strict=True: además desactiva los módulos fuera del perfil que
        LOCKD activó previamente (estado 'enabled'). Nunca toca módulos
        que Lockd no haya activado.
        on_step(result, step_n, total) — callback de progreso opcional.
        """
        profile = self.profiles.by_id(profile_id)
        if not profile:
            raise ValueError(f"Perfil no encontrado: {profile_id}")

        log.info(f"Aplicando perfil '{profile.name}' ({len(profile.modules)} módulos, "
                 f"strict={strict})")
        queue   = self._build_profile_queue(profile, strict=strict)
        results = []

        for i, (mid, script, enable) in enumerate(queue):
            r = self._verified(self.executor.run(mid, script, enable))
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
        strict: bool = False,
    ) -> None:
        """Aplica un perfil en hilo daemon, ideal para GUI.
        Misma semántica aditivo/strict que apply_profile()."""
        import threading
        profile = self.profiles.by_id(profile_id)
        if not profile:
            raise ValueError(f"Perfil no encontrado: {profile_id}")

        queue = self._build_profile_queue(profile, strict=strict)
        results: List[ExecResult] = []
        total = len(queue)

        def _run():
            for i, (mid, script, enable) in enumerate(queue):
                r = self._verified(self.executor.run(mid, script, enable))
                results.append(r)
                on_step(r, i + 1, total)
                if r.cancelled:
                    break
            on_done(results)

        threading.Thread(target=_run, daemon=True, name="lockd-profile").start()

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
            r = self._verified(self.executor.run(mid, mod.enable_script, enable=True))
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
            self.executor.run_async(
                mod.id, script, enable,
                lambda r: on_complete(self._verified(r)),
            )
            return None
        return self._verified(self.executor.run(mod.id, script, enable))

    def _build_profile_queue(self, profile: Profile, strict: bool = False):
        """
        Construye la cola de tareas para un perfil.

        Modo ADITIVO (default): encola enable para los módulos del perfil,
        en el ORDEN declarado en el YAML. No toca nada fuera del perfil.

        Modo STRICT (opt-in): además, encola disable para los módulos fuera
        del perfil cuyo estado registrado sea 'enabled' — es decir, SOLO los
        que Lockd activó. Nunca ejecuta disable sobre módulos en estado
        unknown/disabled/error: correr disable.sh "por las dudas" puede
        destruir configuración que el usuario hizo por su cuenta (ej. apagar
        un fail2ban que Lockd jamás instaló).
        """
        queue = []

        # 1) Activar lo incluido, respetando el orden del perfil
        for mid in profile.modules:
            mod = self._mod_map.get(mid)
            if not mod:
                log.warning(f"Perfil '{profile.id}': módulo desconocido '{mid}' — omitido")
                continue
            script = mod.enable_script
            if script and script.exists():
                queue.append((mid, script, True))

        # 2) Solo en strict: desactivar lo que Lockd activó y el perfil no incluye
        if strict:
            for mid, mod in self._mod_map.items():
                if mid in profile.modules:
                    continue
                if self.state.get(mid) != "enabled":
                    continue
                script = mod.disable_script
                if script and script.exists():
                    queue.append((mid, script, False))

        skipped = [
            mid for mid in self._mod_map
            if mid not in profile.modules
            and not any(q[0] == mid for q in queue)
        ]
        log.info(
            f"Cola de perfil '{profile.id}' (strict={strict}): "
            f"{sum(1 for q in queue if q[2])} enable, "
            f"{sum(1 for q in queue if not q[2])} disable, "
            f"{len(skipped)} sin tocar"
        )
        return queue