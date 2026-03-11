"""
gui/profile_view.py — pestaña Perfiles (v0.4)

Cards simples: nombre, descripción, módulos chips, botón Aplicar.
Sin barra de progreso flotante — feedback inline en cada card.
"""
import logging
import threading
from typing import TYPE_CHECKING, List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

if TYPE_CHECKING:
    from src.app.controller import Controller
from src.engine.profile_manager import Profile
from src.engine.executor import ExecResult

log = logging.getLogger("lockd.gui.profile")

_PROFILE_ICONS = {
    "home_desktop":          "user-home-symbolic",
    "developer_workstation": "applications-development-symbolic",
    "server":                "network-server-symbolic",
    "paranoid":              "security-high-symbolic",
    "lab_test":              "applications-science-symbolic",
}


class ProfileView(Gtk.Box):
    def __init__(self, controller: "Controller"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._ctrl = controller
        self._apply_btns: dict = {}
        self._build()

    def _build(self):
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True
        )
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)
        outer.set_margin_start(24)
        outer.set_margin_end(24)

        # descripción
        desc = Gtk.Label(
            label="Un perfil activa los módulos incluidos y desactiva el resto. "
                  "Ideal para configurar el sistema de una sola vez.",
            wrap=True, halign=Gtk.Align.START,
        )
        desc.add_css_class("dim-label")
        desc.set_margin_bottom(16)
        outer.append(desc)

        grp = Adw.PreferencesGroup()

        profiles = self._ctrl.profiles.all()
        if not profiles:
            grp.add(Adw.ActionRow(
                title="No hay perfiles",
                subtitle="Añadí archivos .yaml en la carpeta profiles/",
            ))
        else:
            for p in profiles:
                row = self._make_row(p)
                grp.add(row)

        outer.append(grp)
        scroll.set_child(outer)
        self.append(scroll)

    def _make_row(self, p: Profile) -> Adw.ActionRow:
        row = Adw.ActionRow(title=p.name, subtitle=p.description or "")

        icon = Gtk.Image.new_from_icon_name(_PROFILE_ICONS.get(p.id, p.icon))
        icon.set_pixel_size(32)
        row.add_prefix(icon)

        # chips módulos
        chips = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
        for mid in p.modules[:3]:
            mod  = self._ctrl.get_module(mid)
            chip = Gtk.Label(label=mod.name if mod else mid)
            chip.add_css_class("caption")
            chip.add_css_class("tag")
            chips.append(chip)
        if len(p.modules) > 3:
            more = Gtk.Label(label=f"+{len(p.modules)-3}")
            more.add_css_class("caption")
            more.add_css_class("dim-label")
            chips.append(more)
        row.add_suffix(chips)

        btn = Gtk.Button(label="Aplicar", valign=Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda _, profile=p, b=btn:
                    self._confirm(profile, b))
        row.add_suffix(btn)
        self._apply_btns[p.id] = btn

        return row

    def _confirm(self, profile: Profile, btn: Gtk.Button):
        mods = ", ".join(profile.modules) or "(ninguno)"
        d = Adw.MessageDialog.new(
            self.get_root(),
            f"Aplicar perfil '{profile.name}'",
            f"{profile.description or ''}\n\nMódulos: {mods}",
        )
        d.add_response("cancel", "Cancelar")
        d.add_response("apply",  "Aplicar")
        d.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("apply")
        d.connect("response", lambda _, r, p=profile, b=btn:
                  self._do_apply(p, b) if r == "apply" else None)
        d.present()

    def _do_apply(self, profile: Profile, btn: Gtk.Button):
        btn.set_sensitive(False)
        btn.set_label("Aplicando…")
        results: List[ExecResult] = []

        def on_step(r, n, total):
            results.append(r)

        def on_done(res):
            GLib.idle_add(self._done, res, btn)

        self._ctrl.apply_profile_async(
            profile.id, on_step=on_step, on_done=on_done
        )

    def _done(self, results: list, btn: Gtk.Button):
        ok  = sum(1 for r in results if r.ok or r.dry_run)
        err = sum(1 for r in results if not r.ok and not r.cancelled)
        btn.set_sensitive(True)
        if err == 0:
            btn.set_label("✓ Aplicado")
            btn.remove_css_class("suggested-action")
            btn.add_css_class("success")
        else:
            btn.set_label(f"✗ {err} error(es)")
            btn.add_css_class("error")
        return GLib.SOURCE_REMOVE
