"""
gui/module_view.py — Modo Avanzado (v0.4) — corazón del sistema

Toggles individuales agrupados por categoría.
highlight_and_enable(module_id) permite activar un módulo
directamente desde sugerencias del scan.
"""
import logging
from typing import TYPE_CHECKING, Dict

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

if TYPE_CHECKING:
    from src.app.controller import Controller
from src.engine.module_loader import ModuleDefinition
from src.engine.executor import ExecResult
from src.interfaces.gui.module_widget import ModuleWidget

log = logging.getLogger("lockd.gui.modules")

_CATEGORY_LABEL = {
    "network":          "🌐 Red",
    "filesystem":       "💾 Sistema de archivos",
    "kernel":           "⚙ Kernel",
    "services":         "🛠 Servicios",
    "access_control":   "🔑 Control de acceso",
    "system_hardening": "🛡 Hardening del sistema",
    "privacy":          "👁 Privacidad",
}

_WARN_MODULES: dict[str, tuple[str, str]] = {
    "hardened_ssh_config": (
        "¿Endurecer configuración SSH?",
        "Esto desactivará el login por contraseña vía SSH.\n\n"
        "Asegurate de tener una clave SSH configurada antes de continuar.",
    ),
    "disable_usb_storage": (
        "¿Bloquear almacenamiento USB?",
        "Los dispositivos USB de almacenamiento conectados serán desconectados.\n"
        "Guardá cualquier archivo abierto desde USB antes de continuar.",
    ),
    "restrict_suid_binaries": (
        "¿Auditar y restringir binarios SUID?",
        "Se eliminará el bit SUID de binarios no esenciales. "
        "Se guarda una lista de cambios para revertirlos si es necesario.",
    ),
    "apparmor_enforce_mode": (
        "¿Activar AppArmor en modo enforce?",
        "Las aplicaciones con perfiles AppArmor quedarán confinadas. "
        "Algunas pueden dejar de funcionar con perfiles muy restrictivos.",
    ),
    "restrict_compilers": (
        "¿Restringir acceso a compiladores?",
        "Los usuarios sin el grupo \'compiler\' no podrán usar gcc/g++/make. "
        "No recomendado en equipos de desarrollo personal.",
    ),
}


class ModuleView(Gtk.Box):
    def __init__(self, controller: "Controller"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._ctrl    = controller
        self._widgets: Dict[str, ModuleWidget] = {}
        self._scroll: Gtk.ScrolledWindow | None = None
        self._build()

    # ── construcción ─────────────────────────────────────────────────────────

    def _build(self):
        # filtro rápido
        filter_bar = Gtk.Box(spacing=10)
        filter_bar.set_margin_top(10)
        filter_bar.set_margin_bottom(6)
        filter_bar.set_margin_start(18)
        filter_bar.set_margin_end(18)

        filter_lbl = Gtk.Label(label="Mostrar:")
        filter_lbl.add_css_class("caption")
        filter_lbl.add_css_class("dim-label")
        filter_bar.append(filter_lbl)

        self._server_filter = Gtk.CheckButton(label="Solo seguros para servidor")
        self._server_filter.add_css_class("caption")
        self._server_filter.connect("toggled", lambda _: self._rebuild_groups())
        filter_bar.append(self._server_filter)

        self.append(filter_bar)
        self.append(Gtk.Separator())

        # scroll
        self._scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vexpand=True,
        )
        self._content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )
        self._content.set_margin_top(16)
        self._content.set_margin_bottom(20)
        self._content.set_margin_start(24)
        self._content.set_margin_end(24)

        # inicializar status label ANTES de _rebuild_groups (que lo usa)
        self._status_lbl = Gtk.Label(
            label="Activá o desactivá módulos individualmente.",
            halign=Gtk.Align.START,
        )
        self._status_lbl.add_css_class("caption")
        self._status_lbl.add_css_class("dim-label")
        self._status_lbl.set_margin_top(4)

        self._rebuild_groups()

        self._scroll.set_child(self._content)
        self.append(self._scroll)

    def _rebuild_groups(self, server_only: bool | None = None):
        if server_only is None:
            server_only = self._server_filter.get_active()

        # limpiar contenido (excepto el status label que se añade al final)
        child = self._content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._content.remove(child)
            child = nxt
        self._widgets.clear()

        cats = self._ctrl.modules_by_category()
        for cat, mods in sorted(cats.items()):
            visible = [m for m in mods if not server_only or m.server_safe]
            if not visible:
                continue
            label = _CATEGORY_LABEL.get(cat, cat.replace("_", " ").title())
            grp   = Adw.PreferencesGroup(title=label)
            for mod in visible:
                state  = self._ctrl.module_state(mod.id)
                widget = ModuleWidget(
                    module        = mod,
                    initial_state = (state == "enabled"),
                    on_toggle     = self._on_toggle,
                )
                self._widgets[mod.id] = widget
                grp.add(widget)
            self._content.append(grp)

        # status label al final
        self._content.append(self._status_lbl)

    # ── API pública ───────────────────────────────────────────────────────────

    def highlight_and_enable(self, module_id: str):
        """
        Llamado desde main_window cuando el usuario hace click en una sugerencia.
        Hace scroll hasta el módulo y lo activa con confirmación si aplica.
        """
        w = self._widgets.get(module_id)
        if not w:
            # módulo no visible — quitar filtro y reconstruir
            self._server_filter.set_active(False)
            self._rebuild_groups(server_only=False)
            w = self._widgets.get(module_id)

        if w:
            # scroll hasta el widget
            GLib.idle_add(self._scroll_to_widget, w)
            # activar
            mod = self._ctrl.get_module(module_id)
            if mod:
                self._on_toggle(mod, True, None)

    def _scroll_to_widget(self, widget: Gtk.Widget):
        adj = self._scroll.get_vadjustment() if self._scroll else None
        if adj:
            # aproximación: scroll hacia abajo progresivamente
            # GTK4 no tiene scroll_to directo sin allocation
            alloc = widget.get_allocation()
            if alloc.y > 0:
                adj.set_value(max(0, alloc.y - 60))
        return GLib.SOURCE_REMOVE

    # ── toggle logic ──────────────────────────────────────────────────────────

    def _on_toggle(self, mod: ModuleDefinition, new_state: bool, sw):
        heading, body = _WARN_MODULES.get(mod.id, (None, None))
        needs_warn = (heading and new_state) or (not mod.desktop_safe and new_state)

        if needs_warn:
            self._show_warning(
                heading or f"¿Activar '{mod.name}'?",
                body or f"Este módulo está pensado para servidores.\n\nImpacto: {mod.impact}",
                on_ok     = lambda: self._run_toggle(mod, new_state),
                on_cancel = lambda: (
                    self._widgets[mod.id].set_active(not new_state)
                    if mod.id in self._widgets else None
                ),
            )
        else:
            self._run_toggle(mod, new_state)

    def _run_toggle(self, mod: ModuleDefinition, enable: bool):
        w = self._widgets.get(mod.id)
        if w:
            w.set_switch_sensitive(False)
        verb = "Activando" if enable else "Desactivando"
        self._set_status(f"{verb} '{mod.name}'…")

        if enable:
            self._ctrl.enable(
                mod.id,
                on_complete=lambda r: GLib.idle_add(self._done, r, enable),
            )
        else:
            self._ctrl.disable(
                mod.id,
                on_complete=lambda r: GLib.idle_add(self._done, r, enable),
            )

    def _done(self, r: ExecResult, enable: bool):
        w = self._widgets.get(r.module_id)
        if w:
            w.set_switch_sensitive(True)

        if r.cancelled:
            if w:
                w.set_active(not enable)
            self._set_status("Cancelado.")
            return GLib.SOURCE_REMOVE

        if r.ok or r.dry_run:
            if w:
                w.set_active(enable)
            verb   = "activado" if enable else "desactivado"
            suffix = " (simulación)" if r.dry_run else ""
            self._set_status(f"✓ '{r.module_id}' {verb}{suffix}.")
            mod = self._ctrl.get_module(r.module_id)
            if mod and mod.requires_reboot and enable:
                self._show_reboot_notice(r.module_id)
        else:
            if w:
                w.set_active(not enable)
            self._set_status(f"✗ Error al procesar '{r.module_id}'.")
            self._show_error("Error al ejecutar módulo",
                             r.error_msg or "", r.stderr)

        return GLib.SOURCE_REMOVE

    # ── helpers UI ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_lbl.set_text(msg)

    def _show_warning(self, heading, body, on_ok, on_cancel):
        d = Adw.MessageDialog.new(self.get_root(), heading, body)
        d.add_response("cancel", "Cancelar")
        d.add_response("ok",     "Continuar")
        d.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel")
        d.connect("response", lambda _, r: on_ok() if r == "ok" else on_cancel())
        d.present()

    def _show_error(self, title, msg, details=""):
        from gi.repository import GLib as GL
        body = msg
        if details:
            body += f"\n\n<tt><small>{GL.markup_escape_text(details[:400])}</small></tt>"
        d = Adw.MessageDialog.new(self.get_root(), title, body)
        d.set_body_use_markup(True)
        d.add_response("ok", "Cerrar")
        d.present()

    def _show_reboot_notice(self, module_id: str):
        d = Adw.MessageDialog.new(
            self.get_root(),
            "Reinicio recomendado",
            f"'{module_id}' requiere reiniciar el sistema para tomar efecto completo.",
        )
        d.add_response("ok", "Entendido")
        d.present()
