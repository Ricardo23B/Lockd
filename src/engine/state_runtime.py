"""
engine/state_runtime.py  (was: state_manager.py) — persistencia del estado de módulos

Archivo: ~/.config/lockd/state.json
Estados por módulo: enabled | disabled | error | unknown

Thread-safe via Lock. Escritura atómica: tmp → rename.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Literal

log     = logging.getLogger("lockd.state")
State   = Literal["enabled", "disabled", "error", "unknown"]
VALID   = {"enabled", "disabled", "error", "unknown"}
VERSION = 2


class StateManager:
    def __init__(self, state_file: Path):
        self._file   = state_file
        self._lock   = threading.Lock()
        self._states: Dict[str, State] = {}
        self._load()

    # -- API pública ----------------------------------------------------------

    def get(self, module_id: str) -> State:
        with self._lock:
            return self._states.get(module_id, "unknown")

    def set(self, module_id: str, state: State) -> None:
        with self._lock:
            self._states[module_id] = state
            self._save()
        log.debug(f"{module_id} → {state}")

    def all(self) -> Dict[str, State]:
        with self._lock:
            return dict(self._states)

    def is_enabled(self, module_id: str) -> bool:
        return self.get(module_id) == "enabled"

    def reset(self, module_id: str) -> None:
        """Vuelve un módulo a 'unknown' (elimina su entrada)."""
        with self._lock:
            self._states.pop(module_id, None)
            self._save()

    # -- privado --------------------------------------------------------------

    def _load(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._states = {
                k: v for k, v in data.get("states", {}).items()
                if isinstance(k, str) and v in VALID
            }
            log.info(f"Estado cargado: {len(self._states)} módulo(s)")
        except (json.JSONDecodeError, TypeError) as e:
            log.error(f"Estado corrupto ({e}), reseteando")
            self._states = {}

    def _save(self) -> None:
        tmp = self._file.with_suffix(".tmp")
        try:
            payload = json.dumps(
                {"version": VERSION, "states": self._states},
                indent=2, ensure_ascii=False,
            ) + "\n"
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._file)
        except OSError as e:
            log.error(f"Error guardando estado: {e}")
            tmp.unlink(missing_ok=True)
