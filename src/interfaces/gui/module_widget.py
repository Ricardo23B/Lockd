"""
gui/module_widget.py — widget reutilizable para un toggle de módulo

AdwActionRow con:
  - badge de riesgo coloreado
  - badge de nivel de seguridad
  - ícono de reinicio requerido
  - badge "solo servidor" o "solo desktop"
  - botón ⓘ con popover detallado
  - Gtk.Switch controlado externamente
"""
import logging
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango

from src.engine.module_loader import ModuleDefinition

log = logging.getLogger("lockd.gui.widget")

_RISK_CSS   = {"low": "success", "medium": "warning", "high": "error"}
_RISK_LABEL = {"low": "Bajo", "medium": "Medio", "high": "⚠ Alto"}
_LVL_LABEL  = {"basic": "Basic", "advanced": "Adv", "expert": "Expert", "paranoid": "Para"}
_LVL_CSS    = {"basic": "success", "advanced": "accent", "expert": "warning", "paranoid": "error"}


class ModuleWidget(Adw.ActionRow):
    """AdwActionRow lista para insertar en cualquier PreferencesGroup."""

    def __init__(
        self,
        module:        ModuleDefinition,
        initial_state: bool,
        on_toggle:     Callable,   # (module, new_bool, switch) → None
    ):
        super().__init__()
        self._mod      = module
        self._toggle   = on_toggle
        self._updating = False

        self.set_title(module.name)
        self.set_subtitle(self._short_desc())
        self.set_activatable(False)

        # badge riesgo
        self.add_suffix(self._badge(_RISK_LABEL[module.risk_level],
                                    _RISK_CSS[module.risk_level]))

        # badge nivel
        lbl = _LVL_LABEL.get(module.security_level, module.security_level)
        css = _LVL_CSS.get(module.security_level, "")
        self.add_suffix(self._badge(lbl, css))

        # avisos de compatibilidad
        if not module.desktop_safe:
            ico = Gtk.Image.new_from_icon_name("network-server-symbolic")
            ico.set_pixel_size(14)
            ico.set_tooltip_text("Recomendado solo para servidores")
            ico.add_css_class("dim-label")
            self.add_suffix(ico)

        # reinicio requerido
        if module.requires_reboot:
            ico = Gtk.Image.new_from_icon_name("system-reboot-symbolic")
            ico.set_pixel_size(14)
            ico.set_tooltip_text("Requiere reinicio para tomar efecto")
            ico.add_css_class("dim-label")
            self.add_suffix(ico)

        # botón ⓘ
        btn_info = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        btn_info.set_label("ⓘ")
        btn_info.add_css_class("flat")
        btn_info.add_css_class("circular")
        btn_info.set_tooltip_text("Ver detalles")
        btn_info.set_popover(self._build_popover())
        self.add_suffix(btn_info)

        # switch
        self._sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=initial_state)
        if not module.available:
            self._sw.set_sensitive(False)
            reasons = []
            if not module.deps_ok:
                reasons.append(f"Deps faltantes: {', '.join(module.missing_deps)}")
            if not module.distro_ok:
                reasons.append("Distro no soportada")
            self._sw.set_tooltip_text(" | ".join(reasons))
        self._sw.connect("state-set", self._on_sw)
        self.add_suffix(self._sw)

    # ── API pública ────────────────────────────────────────────────────────

    def set_active(self, v: bool) -> None:
        """Mueve el switch sin disparar on_toggle."""
        self._updating = True
        self._sw.set_active(v)
        self._updating = False

    def set_switch_sensitive(self, v: bool) -> None:
        if self._mod.available:
            self._sw.set_sensitive(v)

    @property
    def module(self) -> ModuleDefinition:
        return self._mod

    # ── privado ────────────────────────────────────────────────────────────

    def _on_sw(self, sw, state: bool) -> bool:
        if self._updating:
            return False
        self._toggle(self._mod, state, sw)
        return True  # nosotros controlamos el movimiento visual

    def _short_desc(self) -> str:
        text = " ".join(self._mod.description.split())
        return text[:90] + "…" if len(text) > 90 else text

    def _badge(self, label: str, css: str) -> Gtk.Label:
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("caption")
        lbl.add_css_class("tag")
        if css:
            lbl.add_css_class(css)
        lbl.set_valign(Gtk.Align.CENTER)
        return lbl

    def _build_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover(has_arrow=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_size_request(340, -1)

        def row(label, value, markup=False, css=None):
            h = Gtk.Box(spacing=8)
            k = Gtk.Label(label=f"<b>{label}</b>", use_markup=True,
                          halign=Gtk.Align.START, xalign=0.0)
            k.add_css_class("caption")
            v = Gtk.Label(label=value, use_markup=markup,
                          halign=Gtk.Align.START, xalign=0.0)
            v.set_wrap(True)
            v.set_wrap_mode(Pango.WrapMode.WORD)
            if css:
                v.add_css_class(css)
            h.append(k)
            h.append(v)
            return h

        def lbl(text, markup=False, css=None, wrap=True):
            l = Gtk.Label(label=text, use_markup=markup,
                          halign=Gtk.Align.START, xalign=0.0)
            if wrap:
                l.set_wrap(True)
                l.set_wrap_mode(Pango.WrapMode.WORD)
            if css:
                l.add_css_class(css)
            return l

        m = self._mod
        box.append(lbl(f"<b>{m.name}</b>", markup=True))
        box.append(Gtk.Separator())

        desc_lbl = lbl(m.description.strip(), wrap=True)
        desc_lbl.add_css_class("caption")
        box.append(desc_lbl)

        box.append(Gtk.Separator())

        if m.impact:
            box.append(lbl(f"<b>Impacto:</b> {m.impact}", markup=True, wrap=True))

        meta = (
            f"Riesgo: {_RISK_LABEL[m.risk_level]}  |  "
            f"Nivel: {m.security_level.capitalize()}  |  "
            f"Reinicio: {'Sí' if m.requires_reboot else 'No'}"
        )
        box.append(lbl(f"<small><i>{meta}</i></small>", markup=True, css="dim-label"))

        compat_parts = []
        if m.server_safe:
            compat_parts.append("✓ Servidor")
        if m.desktop_safe:
            compat_parts.append("✓ Desktop")
        if compat_parts:
            box.append(lbl(f"<small>{' · '.join(compat_parts)}</small>",
                           markup=True, css="dim-label"))

        if not m.deps_ok:
            deps = ", ".join(m.missing_deps)
            box.append(lbl(f"<small>⚠ Deps faltantes: {deps}</small>",
                           markup=True, css="error"))

        pop.set_child(box)
        return pop
