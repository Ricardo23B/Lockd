"""
engine/executor.py — ejecuta scripts de módulos con privilegios root

Usa pkexec (Polkit). Nunca sudo directamente.
Soporta modo dry-run: pasa DRY_RUN=1 al entorno del script.
Modo asíncrono para GUI (hilo daemon + callback).
Modo síncrono para CLI.
"""
import logging
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from lockd.engine.state_runtime import StateManager

log           = logging.getLogger("lockd.executor")
TIMEOUT        = 120    # segundos máximo por script (modo legacy)
# El helper tiene su propio timeout de 600s (módulos que instalan paquetes,
# ej. clamav); acá solo un margen por encima de ese.
HELPER_TIMEOUT = 660
CANCEL_CODE   = 126     # pkexec retorna 126 si usuario cancela
# workaround: polkit behaves differently on Mint and some Ubuntu derivatives
# cancel code is sometimes 127 there — needs investigation

# Rutas donde el .deb / instalación local dejan el helper privilegiado.
# Si existe, TODA operación root pasa por él (script root-owned + journal +
# auth_admin_keep = un solo prompt por sesión). Si no existe (checkout de
# desarrollo), se cae al modo legacy: pkexec sobre el script directo.
HELPER_PATHS = (
    Path("/usr/libexec/lockd/lockd-helper"),
    Path("/usr/local/libexec/lockd/lockd-helper"),
)


def _find_helper() -> Optional[Path]:
    for p in HELPER_PATHS:
        if p.is_file():
            return p
    return None


@dataclass
class ExecResult:
    ok:        bool
    module_id: str
    action:    str          # "enable" | "disable"
    stdout:    str
    stderr:    str
    rc:        int
    cancelled: bool         = False
    dry_run:   bool         = False
    error_msg: Optional[str] = None


def _find_pkexec() -> Optional[str]:
    tool = shutil.which("pkexec")
    if not tool:
        print("[lockd] pkexec not found — privilege escalation will fail")
        log.warning("pkexec no encontrado. Instalar polkit: apt install policykit-1")
    return tool


class Executor:
    """
    Ejecuta scripts de módulos.

    dry_run = True → Variable DRY_RUN=1 en el entorno del script.
                     El script muestra qué haría sin aplicar cambios.
    """

    def __init__(self, state_mgr: StateManager, dry_run: bool = False):
        self._state   = state_mgr
        self._dry_run = dry_run
        self._tool    = _find_pkexec()
        self._helper  = _find_helper()
        if not self._helper:
            log.warning(
                "lockd-helper no instalado — modo legacy: pkexec ejecutará los "
                "scripts directamente (sin journal, un prompt por script). "
                "Instalación recomendada: el paquete .deb, o copiar "
                "helper/lockd-helper a /usr/local/libexec/lockd/ junto con los "
                "módulos en /usr/local/lib/lockd/modules/."
            )
        log.info(
            f"Executor listo (dry_run={dry_run}, tool={self._tool or 'N/A'}, "
            f"helper={self._helper or 'legacy'})"
        )

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        self._dry_run = value
        log.info(f"Dry-run {'ON' if value else 'OFF'}")

    # ── modo síncrono (CLI) ──────────────────────────────────────────────

    def run(self, module_id: str, script: Path, enable: bool) -> ExecResult:
        """Bloquea hasta que el script termina. Ideal para CLI."""
        action = "enable" if enable else "disable"
        result = self._execute(module_id, script, action)
        self._update_state(result, enable)
        return result

    # ── modo asíncrono (GUI) ─────────────────────────────────────────────

    def run_async(
        self,
        module_id: str,
        script: Path,
        enable: bool,
        on_complete: Callable[[ExecResult], None],
    ) -> None:
        """Lanza el script en hilo daemon. on_complete se llama desde ese hilo."""
        t = threading.Thread(
            target=self._thread,
            args=(module_id, script, enable, on_complete),
            daemon=True,
            name=f"lockd-{module_id[:12]}-{'en' if enable else 'dis'}",
        )
        t.start()

    # ── privado ──────────────────────────────────────────────────────────

    def _thread(self, module_id, script, enable, on_complete):
        action = "enable" if enable else "disable"
        result = self._execute(module_id, script, action)
        self._update_state(result, enable)
        on_complete(result)

    def _execute(self, module_id: str, script: Path, action: str) -> ExecResult:
        def fail(msg: str, rc: int = -1) -> ExecResult:
            log.error(f"[{module_id}] {msg}")
            return ExecResult(False, module_id, action, "", msg, rc, error_msg=msg)

        if not self._tool:
            return fail("pkexec no disponible. Instalar: apt install policykit-1")

        if self._helper:
            # Modo helper: el script lo resuelve el lado privilegiado desde
            # una ruta root-owned, según modules.yaml. El path local solo se
            # usó para validaciones de UI; no viaja al helper.
            cmd = [self._tool, str(self._helper), action, module_id]
            if self._dry_run:
                cmd.append("--dry-run")
        else:
            # Modo legacy (checkout de desarrollo, sin helper instalado)
            if not script or not script.exists():
                return fail(f"Script no encontrado: {script}")
            if not os.access(script, os.X_OK):
                return fail(
                    f"Sin permisos de ejecución: {script}\n"
                    f"Corregir con: chmod +x {script}"
                )
            cmd = [self._tool, str(script)]
            if self._dry_run:
                cmd.append("--dry-run")

        # pkexec ejecuta el programa en un entorno mínimo y saneado: las
        # variables del invocante (incluida DRY_RUN) NO llegan al hijo.
        # Por eso el dry-run viaja como ARGUMENTO en ambos modos. La variable
        # de entorno se mantiene solo como redundancia documentada.
        env = {**os.environ, **({"DRY_RUN": "1"} if self._dry_run else {})}

        log.info(f"{'[DRY] ' if self._dry_run else ''}{action}: {module_id}")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=HELPER_TIMEOUT if self._helper else TIMEOUT, env=env,
            )
        except subprocess.TimeoutExpired:
            return fail("Timeout: el script tardó más de "
                        f"{HELPER_TIMEOUT if self._helper else TIMEOUT}s.")
        except FileNotFoundError as e:
            return fail(str(e))

        if proc.returncode == CANCEL_CODE:
            log.info(f"Usuario canceló autenticación para '{module_id}'")
            return ExecResult(
                False, module_id, action,
                proc.stdout, proc.stderr, proc.returncode,
                cancelled=True, dry_run=self._dry_run,
            )

        ok = proc.returncode == 0
        if not ok:
            log.error(f"[{module_id}] Script falló (rc={proc.returncode})")
        return ExecResult(
            ok=ok, module_id=module_id, action=action,
            stdout=proc.stdout, stderr=proc.stderr, rc=proc.returncode,
            dry_run=self._dry_run,
            error_msg=None if ok else (
                f"Código {proc.returncode}\n{proc.stderr or '(sin stderr)'}"
            ),
        )

    def _update_state(self, result: ExecResult, enable: bool) -> None:
        if result.dry_run or result.cancelled:
            return
        if result.ok:
            self._state.set(result.module_id, "enabled" if enable else "disabled")
        else:
            self._state.set(result.module_id, "error")
