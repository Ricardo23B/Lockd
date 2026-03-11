"""
gui/level_view.py — pestaña Niveles (v0.4)

Cards por nivel, acumulativo, feedback inline en botón.
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
from src.engine.executor import ExecResult

log = logging.getLogger("lockd.gui.levels")

_LEVEL_CSS = {
    "basic":    "success",
    "advanced": "accent",
    "expert":   "warning",
    "paranoid": "error",
}
_LEVEL_EMOJI = {
    "basic": "🟢", "advanced": "🔵", "expert": "🟠", "paranoid": "🔴"
}


class LevelView(Gtk.Box):
    def __init__(self, controller: "Controller"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._ctrl    = controller
        self._results: List[ExecResult] = []
        self._pulse_timer = None
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

        desc = Gtk.Label(
            label="Los niveles son acumulativos: Expert activa todo lo de Basic y Advanced también.",
            wrap=True, halign=Gtk.Align.START,
        )
        desc.add_css_class("dim-label")
        desc.set_margin_bottom(16)
        outer.append(desc)

        grp = Adw.PreferencesGroup()
        for lvl in self._ctrl.levels.all():
            grp.add(self._make_row(lvl))
        outer.append(grp)

        self._progress = Gtk.ProgressBar(visible=False)
        self._progress.set_margin_top(12)
        outer.append(self._progress)

        self._status_lbl = Gtk.Label(label="", halign=Gtk.Align.START)
        self._status_lbl.add_css_class("caption")
        self._status_lbl.add_css_class("dim-label")
        outer.append(self._status_lbl)

        scroll.set_child(outer)
        self.append(scroll)

    def _make_row(self, lvl) -> Adw.ActionRow:
        emoji = _LEVEL_EMOJI.get(lvl.id, "●")
        row   = Adw.ActionRow(
            title    = f"{emoji} {lvl.label}",
            subtitle = f"{lvl.description}  ·  {len(lvl.cumulative)} módulos acumulativos",
        )

        chips = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
        for mid in lvl.modules[:3]:
            mod  = self._ctrl.get_module(mid)
            chip = Gtk.Label(label=mod.name if mod else mid)
            chip.add_css_class("caption")
            chip.add_css_class("tag")
            chip.add_css_class(_LEVEL_CSS.get(lvl.id, ""))
            chips.append(chip)
        if len(lvl.modules) > 3:
            more = Gtk.Label(label=f"+{len(lvl.modules)-3}")
            more.add_css_class("caption")
            more.add_css_class("dim-label")
            chips.append(more)
        row.add_suffix(chips)

        btn = Gtk.Button(label="Aplicar", valign=Gtk.Align.CENTER)
        btn.add_css_class(_LEVEL_CSS.get(lvl.id, ""))
        btn.connect("clicked", lambda _, l=lvl, b=btn: self._confirm(l, b))
        row.add_suffix(btn)
        return row

    def _confirm(self, lvl, btn: Gtk.Button):
        mods = ", ".join(lvl.cumulative) or "(ninguno)"
        d = Adw.MessageDialog.new(
            self.get_root(),
            f"Aplicar nivel '{lvl.label}'",
            f"{lvl.description}\n\nMódulos: {mods}",
        )
        d.add_response("cancel", "Cancelar")
        d.add_response("apply",  "Aplicar nivel")
        d.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("apply")
        d.connect("response", lambda _, r, l=lvl, b=btn:
                  self._do_apply(l, b) if r == "apply" else None)
        d.present()

    def _do_apply(self, lvl, btn: Gtk.Button):
        btn.set_sensitive(False)
        btn.set_label("Aplicando…")
        self._results = []
        self._progress.set_visible(True)
        self._progress.set_fraction(0.0)
        self._start_pulse()

        def on_step(r: ExecResult, n: int, total: int):
            GLib.idle_add(self._update_step, r, n, total)

        def run():
            self._ctrl.apply_level(lvl.id, on_step=on_step)
            GLib.idle_add(self._done, btn)

        threading.Thread(target=run, daemon=True, name=f"lt-level-{lvl.id}").start()

    def _update_step(self, r: ExecResult, n: int, total: int):
        self._results.append(r)
        self._progress.set_fraction(n / total)
        icon = "✓" if (r.ok or r.dry_run) else "✗"
        self._status_lbl.set_text(f"{icon} [{n}/{total}] {r.module_id}")
        return GLib.SOURCE_REMOVE

    def _done(self, btn: Gtk.Button):
        self._stop_pulse()
        self._progress.set_visible(False)
        ok  = sum(1 for r in self._results if r.ok or r.dry_run)
        err = len(self._results) - ok
        btn.set_sensitive(True)
        if err == 0:
            btn.set_label("✓ Aplicado")
        else:
            btn.set_label(f"✗ {err} error(es)")
        self._status_lbl.set_text(
            f"Nivel aplicado: {ok} OK, {err} errores de {len(self._results)} módulos."
        )
        return GLib.SOURCE_REMOVE

    def _start_pulse(self):
        def pulse():
            if self._pulse_timer is None:
                return GLib.SOURCE_REMOVE
            self._progress.pulse()
            return GLib.SOURCE_CONTINUE
        self._pulse_timer = GLib.timeout_add(200, pulse)

    def _stop_pulse(self):
        if self._pulse_timer is not None:
            GLib.source_remove(self._pulse_timer)
            self._pulse_timer = None
