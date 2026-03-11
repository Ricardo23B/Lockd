"""
gui/scan_view.py — panel de detalle del scan (opcional, expandible)

En v0.4 el scan vive en el status bar de main_window.
Esta clase renderiza el detalle completo cuando el usuario
quiere ver todos los checks individuales.
"""
import logging
from typing import TYPE_CHECKING

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

if TYPE_CHECKING:
    from src.app.controller import Controller
    from src.engine.scanner import SecurityReport

log = logging.getLogger("lockd.gui.scan")

_STATUS_ICON = {
    "secure":   ("emblem-ok-symbolic",     "success"),
    "insecure": ("dialog-warning-symbolic", "error"),
    "unknown":  ("dialog-question-symbolic","dim-label"),
}
_CATEGORY_LABEL = {
    "network":         "🌐 Red",
    "filesystem":      "💾 Sistema de archivos",
    "kernel":          "⚙ Kernel",
    "services":        "🛠 Servicios",
    "access_control":  "🔑 Control de acceso",
    "system_hardening":"🛡 Hardening del sistema",
}


class ScanDetailDialog:
    """
    Diálogo modal con el detalle completo del último scan.
    Se abre desde main_window cuando el usuario hace click en el score.
    """

    @staticmethod
    def show(parent, report: "SecurityReport", controller: "Controller"):
        if not report:
            return

        dlg = Adw.MessageDialog.new(parent, "Detalle del Security Scan", "")
        dlg.set_default_size(600, -1)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_size_request(-1, 400)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        cats: dict = {}
        for c in report.checks:
            cats.setdefault(c.category or "general", []).append(c)

        for cat, checks in sorted(cats.items()):
            label = _CATEGORY_LABEL.get(cat, cat.replace("_", " ").title())
            grp   = Adw.PreferencesGroup(title=label)
            for c in checks:
                icon_name, css = _STATUS_ICON.get(c.status, _STATUS_ICON["unknown"])
                row = Adw.ActionRow(title=c.name, subtitle=c.detail or "")
                ico = Gtk.Image.new_from_icon_name(icon_name)
                ico.set_pixel_size(18)
                ico.add_css_class(css)
                row.add_prefix(ico)
                grp.add(row)
            outer.append(grp)

        scroll.set_child(outer)
        dlg.set_extra_child(scroll)
        dlg.add_response("ok", "Cerrar")
        dlg.present()
