"""
gui/main_window.py — lockd v0.4 — rediseño

Layout:
  ┌─────────────────────────────────────────────────────┐
  │ HeaderBar: título + dry-run toggle + menú           │
  ├─────────────────────────────────────────────────────┤
  │ StatusBar: Score · Nivel · Perfil · Sugerencias     │
  │            clicables                [Escanear]      │
  ├─────────────────────────────────────────────────────┤
  │ Tabs: Perfiles | Niveles | Avanzado                 │
  └─────────────────────────────────────────────────────┘
"""
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

if TYPE_CHECKING:
    from src.app.controller import Controller

from src.interfaces.gui.profile_view import ProfileView
from src.interfaces.gui.level_view   import LevelView
from src.interfaces.gui.module_view  import ModuleView

log = logging.getLogger("lockd.gui.window")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application, controller: "Controller"):
        super().__init__(application=application)
        self._ctrl   = controller
        self._report = None
        self.set_title("lockd")
        self.set_default_size(860, 680)
        self.set_resizable(True)  # allow resize but constrain min
        self._build()

    def _build(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # ── HeaderBar ─────────────────────────────────────────────────────
        header = Adw.HeaderBar()
        header.set_show_title(False)

        self._dry_btn = Gtk.ToggleButton(label="⟳ Simular")
        self._dry_btn.add_css_class("flat")
        self._dry_btn.set_tooltip_text("Dry-run: muestra qué haría sin aplicar cambios reales")
        self._dry_btn.connect("toggled", self._on_dry_toggle)
        header.pack_start(self._dry_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.add_css_class("flat")
        menu_btn.set_popover(self._build_menu())
        header.pack_end(menu_btn)

        toolbar_view.add_top_bar(header)

        # banner dry-run
        self._dry_banner = Adw.Banner(
            title="Modo simulación activo — los cambios NO se aplican al sistema."
        )
        toolbar_view.add_top_bar(self._dry_banner)

        # ── layout raíz ───────────────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # status bar siempre visible
        root.append(self._build_status_bar())
        root.append(Gtk.Separator())

        # ── ViewStack 3 tabs ───────────────────────────────────────────────
        self._stack = Adw.ViewStack()

        self._profile_view = ProfileView(self._ctrl)
        self._level_view   = LevelView(self._ctrl)
        self._module_view  = ModuleView(self._ctrl)

        self._stack.add_titled_with_icon(
            self._profile_view, "profiles", "Perfiles",
            "application-x-addon-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._level_view, "levels", "Niveles",
            "view-list-ordered-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._module_view, "advanced", "Avanzado",
            "preferences-system-symbolic"
        )
        self._stack.set_vexpand(True)

        # switcher en header
        top_sw = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(top_sw)

        # switcher en footer (mobile/narrow)
        bot_bar = Adw.ViewSwitcherBar(stack=self._stack, reveal=True)

        root.append(self._stack)
        root.append(bot_bar)
        toolbar_view.set_content(root)

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> Gtk.Box:
        """
        Dos filas:
          Fila 1: [score] | [NIVEL] | [PERFIL]       [Escanear]
          Fila 2: chips de sugerencias (overflow con FlowBox)
        """
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(10)
        outer.set_margin_bottom(6)
        outer.set_margin_start(20)
        outer.set_margin_end(20)

        # ── fila 1: métricas + botón ──────────────────────────────────────
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row1.set_margin_bottom(6)

        # score
        score_box = Gtk.Box(spacing=4)
        self._score_label = Gtk.Label(label="—")
        self._score_label.add_css_class("title-2")
        score_box.append(self._score_label)
        score_box.append(_dim_label("/ 100"))
        row1.append(score_box)
        row1.append(_vsep())

        # nivel
        row1.append(_stat_column("NIVEL", "_level_label", self))
        row1.append(_vsep())

        # perfil
        row1.append(_stat_column("PERFIL", "_profile_label", self))

        # spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        row1.append(spacer)

        # botón escanear — ancho fijo para que no baile
        self._scan_btn = Gtk.Button(label="Escanear")
        self._scan_btn.add_css_class("suggested-action")
        self._scan_btn.set_size_request(110, -1)
        self._scan_btn.set_valign(Gtk.Align.CENTER)
        self._scan_btn.connect("clicked", self._start_scan)
        row1.append(self._scan_btn)

        outer.append(row1)

        # ── fila 2: sugerencias con FlowBox (wrap automático) ─────────────
        # FlowBox distribuye chips en múltiples líneas si no caben en una
        self._sug_flow = Gtk.FlowBox()
        self._sug_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._sug_flow.set_max_children_per_line(6)
        self._sug_flow.set_min_children_per_line(1)
        self._sug_flow.set_row_spacing(4)
        self._sug_flow.set_column_spacing(6)
        self._sug_flow.set_homogeneous(False)

        # placeholder inicial
        self._sug_placeholder = _dim_label("Ejecutá un escaneo para ver sugerencias")
        self._sug_flow.insert(self._sug_placeholder, -1)

        outer.append(self._sug_flow)
        outer.append(Gtk.Box())   # pequeño padding inferior

        return outer

    # ── scan ──────────────────────────────────────────────────────────────────

    def _start_scan(self, _):
        self._scan_btn.set_sensitive(False)
        self._scan_btn.set_label("Escaneando…")
        self._score_label.set_text("…")
        self._level_label.set_text("…")
        _clear_flowbox(self._sug_flow)
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            report = self._ctrl.scan()
        except Exception as e:
            log.error(f"Scan: {e}")
            report = None
        GLib.idle_add(self._show_results, report)

    def _show_results(self, report):
        self._scan_btn.set_sensitive(True)
        self._scan_btn.set_label("Re-escanear")

        if not report:
            self._score_label.set_text("ERR")
            return GLib.SOURCE_REMOVE

        self._report = report
        s = report.score

        # score + color
        for css in ("success", "warning", "error"):
            self._score_label.remove_css_class(css)
        self._score_label.add_css_class(
            "success" if s >= 80 else "warning" if s >= 50 else "error"
        )
        self._score_label.set_text(str(s))

        # nivel
        if report.suggested_profile:
            p = self._ctrl.profiles.by_id(report.suggested_profile)
            self._level_label.set_text(p.name if p else report.suggested_profile)
        else:
            self._level_label.set_text(
                "Muy seguro" if s >= 80 else "Mejorable" if s >= 50 else "Vulnerable"
            )

        # perfil activo
        self._refresh_active_profile()

        # chips sugerencias — usando FlowBox para que hagan wrap
        _clear_flowbox(self._sug_flow)
        fixes = report.recommended_fixes[:5]  # máx 5 chips

        if fixes:
            lbl = _dim_label("Aplicar:")
            self._sug_flow.insert(lbl, -1)
            for fix_id in fixes:
                mod = self._ctrl.get_module(fix_id)
                if not mod:
                    continue
                # nombre corto para que los chips no sean enormes
                short = mod.name if len(mod.name) <= 22 else mod.name[:20] + "…"
                chip = Gtk.Button(label=short)
                chip.add_css_class("pill")
                chip.add_css_class("caption")
                chip.add_css_class(
                    {"low": "success", "medium": "warning", "high": "error"}
                    .get(mod.risk_level, "")
                )
                chip.set_tooltip_text(f"{mod.id}\n{mod.impact}")
                chip.connect("clicked", lambda _, m=mod: self._on_suggestion(m))
                self._sug_flow.insert(chip, -1)
        else:
            ok = Gtk.Label(label="✓ Sin correcciones pendientes")
            ok.add_css_class("caption")
            ok.add_css_class("success")
            self._sug_flow.insert(ok, -1)

        return GLib.SOURCE_REMOVE

    def _on_suggestion(self, mod):
        """Chip clicado → ir a Avanzado y activar el módulo."""
        self._stack.set_visible_child_name("advanced")
        self._module_view.highlight_and_enable(mod.id)

    def _refresh_active_profile(self):
        enabled = {
            m.id for m in self._ctrl.modules
            if self._ctrl.module_state(m.id) == "enabled"
        }
        for p in self._ctrl.profiles.all():
            if set(p.modules) == enabled:
                self._profile_label.set_text(p.name)
                return
        self._profile_label.set_text("personalizado" if enabled else "ninguno")

    # ── toggle dry-run ────────────────────────────────────────────────────────

    def _on_dry_toggle(self, btn):
        active = btn.get_active()
        self._ctrl.executor.dry_run = active
        self._dry_banner.set_revealed(active)
        if active:
            btn.add_css_class("accent")
        else:
            btn.remove_css_class("accent")

    # ── menú hamburguesa ──────────────────────────────────────────────────────

    def _build_menu(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)

        def item(label, cb):
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.set_halign(Gtk.Align.FILL)
            b.connect("clicked", lambda _: (pop.popdown(), cb()))
            box.append(b)

        item("Ver archivo de log",   self._open_log)
        item("Acerca de lockd", self._show_about)
        pop.set_child(box)
        return pop

    def _open_log(self):
        import shutil, subprocess
        for p in ("/var/log/lockd.log",
                  str(Path.home() / ".config/lockd/lockd.log")):
            if Path(p).exists():
                for viewer in ("gedit", "mousepad", "kate", "xdg-open"):
                    if shutil.which(viewer):
                        subprocess.Popen([viewer, p])
                        return
        d = Adw.MessageDialog.new(self, "Log no encontrado", "Ejecutá primero una acción.")
        d.add_response("ok", "Cerrar")
        d.present()

    def _show_about(self):
        w = Adw.AboutWindow.new()
        w.set_transient_for(self)
        w.set_application_name("lockd")
        w.set_version("0.4.0")
        w.set_developer_name("Contribuidores de lockd")
        w.set_license_type(Gtk.License.GPL_3_0)
        w.set_comments(
            "Hardening de Linux sin tocar la terminal.\n"
            "Security Scan · Perfiles · Niveles · Modo Avanzado · CLI"
        )
        w.set_website("https://github.com/Ricardo23B/lockd")
        w.present()


# ── helpers de layout ─────────────────────────────────────────────────────────

def _dim_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.add_css_class("dim-label")
    lbl.add_css_class("caption")
    lbl.set_valign(Gtk.Align.CENTER)
    return lbl


def _vsep() -> Gtk.Separator:
    return Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)


def _stat_column(caption: str, attr: str, obj) -> Gtk.Box:
    """Columna de 2 líneas: etiqueta pequeña + valor."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    cap = Gtk.Label(label=caption)
    cap.add_css_class("caption")
    cap.add_css_class("dim-label")
    cap.set_halign(Gtk.Align.START)
    val = Gtk.Label(label="—")
    val.set_halign(Gtk.Align.START)
    val.add_css_class("heading")
    setattr(obj, attr, val)
    box.append(cap)
    box.append(val)
    return box


def _clear_box(box: Gtk.Box):
    child = box.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


def _clear_flowbox(fb: Gtk.FlowBox):
    """Limpia todos los hijos de un FlowBox."""
    while True:
        child = fb.get_child_at_index(0)
        if child is None:
            break
        fb.remove(child)
