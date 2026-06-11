"""
engine/logger.py — logging centralizado para lockd

Escribe a /var/log/lockd.log con fallback a ~/.config/lockd/lockd.log
si no hay permisos de sistema (ejecución sin root).
"""
import logging
import sys
from pathlib import Path

SYSTEM_LOG = Path("/var/log/lockd.log")
USER_LOG   = Path.home() / ".config" / "lockd" / "lockd.log"
FMT        = "[%(levelname)s] %(asctime)s %(name)s: %(message)s"
DATE_FMT   = "%Y-%m-%d %H:%M:%S"
_done      = False


def setup(level: str = "INFO") -> None:
    """Inicializa el sistema de logging. Llama solo una vez al arrancar."""
    global _done
    if _done:
        return
    _done = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt  = logging.Formatter(FMT, DATE_FMT)

    # handler de consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # handler de archivo
    log_path = _pick_log_file()
    if log_path:
        try:
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass

    logging.getLogger("lockd").info(
        f"--- lockd iniciando (log: {log_path or 'solo consola'}) ---"
    )


def _pick_log_file() -> Path | None:
    try:
        SYSTEM_LOG.touch()
        return SYSTEM_LOG
    except (PermissionError, OSError):
        pass
    try:
        USER_LOG.parent.mkdir(parents=True, exist_ok=True)
        return USER_LOG
    except OSError:
        return None


def get(name: str = "lockd") -> logging.Logger:
    """Shortcut para obtener un logger con el prefijo lockd."""
    return logging.getLogger(f"lockd.{name}" if name != "lockd" else name)
