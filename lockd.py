#!/usr/bin/env python3
"""
lockd.py — punto de entrada unificado de Lockd v0.4

Modos de arranque:
    python3 lockd.py           → GUI (si hay DISPLAY/WAYLAND_DISPLAY)
    python3 lockd.py --cli     → CLI forzada
    python3 lockd.py scan      → CLI con subcomando
    python3 lockd.py --gui     → GUI forzada
    lockd enable firewall      → CLI directamente

La detección automática de modo usa:
    - $DISPLAY o $WAYLAND_DISPLAY  → GUI disponible
    - sin display / --no-gui       → CLI
    - presencia de subcomandos     → CLI
"""
import os
import sys

APP_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.insert(0, APP_DIR)

APP_VERSION = "0.3.0"
APP_ID      = "io.github.lockd"

# subcomandos CLI conocidos
CLI_COMMANDS = {
    "scan", "list", "status", "enable", "disable",
    "simulate", "profile", "profiles", "level", "levels", "info",
}


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _wants_cli() -> bool:
    args = sys.argv[1:]
    if "--cli" in args or "--no-gui" in args:
        return True
    for arg in args:
        if arg in CLI_COMMANDS:
            return True
    return False


def _wants_gui() -> bool:
    return "--gui" in sys.argv[1:]


def run_gui():
    """Arranca la interfaz gráfica GTK4/Adwaita."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gio
    except (ImportError, ValueError) as e:
        print(
            f"[ERROR] Faltan librerías GTK4/libadwaita.\n"
            f"  Instalar: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
            f"  Detalle: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--dry-run",   action="store_true")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--gui",       action="store_true")
    p.add_argument("--version",   action="version", version=f"Lockd {APP_VERSION}")
    args, _ = p.parse_known_args()

    from src.engine import logger
    logger.setup(args.log_level)

    class LockdApp(Adw.Application):
        def __init__(self):
            super().__init__(
                application_id=APP_ID,
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self._dry_run = args.dry_run

        def do_activate(self):
            if self.props.active_window:
                self.props.active_window.present()
                return
            try:
                from src.app.controller import Controller
                ctrl = Controller(dry_run=self._dry_run)
            except Exception as e:
                self._fatal("Error al cargar módulos", str(e))
                return

            from src.interfaces.gui.main_window import MainWindow
            win = MainWindow(application=self, controller=ctrl)
            win.present()

        def _fatal(self, title, msg):
            import logging
            logging.getLogger("lockd").critical(f"{title}: {msg}")
            d = Adw.MessageDialog.new(None, title, msg)
            d.add_response("ok", "Cerrar")
            d.set_application(self)
            d.connect("response", lambda *_: self.quit())
            d.present()

    sys.exit(LockdApp().run(None))


def run_cli():
    """Arranca la interfaz de línea de comandos."""
    from src.interfaces.cli.main import run
    # quitar --cli / --gui / --no-gui del argv antes de parsear
    argv = [a for a in sys.argv[1:] if a not in ("--cli", "--gui", "--no-gui")]
    run(argv)


def main():
    if "--version" in sys.argv:
        print(f"Lockd {APP_VERSION}")
        return

    if _wants_cli() or not _has_display():
        run_cli()
    elif _wants_gui() or _has_display():
        run_gui()
    else:
        run_cli()


if __name__ == "__main__":
    main()
