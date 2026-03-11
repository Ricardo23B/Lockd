"""
interfaces/cli/tui.py — TUI interactiva para el Modo Avanzado

Pantallas:
  1. SELECCIÓN   — lista de módulos con estado actual, navegable con flechas
  2. PREVIEW     — contenido del script enable.sh del módulo seleccionado
  3. CONFIRMACIÓN — resumen de lo que se va a aplicar
  4. EJECUCIÓN   — output en vivo de cada script

Controles:
  ↑ ↓          navegar módulos
  ESPACIO      marcar / desmarcar módulo
  P            preview del script del módulo actual
  A            marcar todos / desmarcar todos
  ENTER        ir a confirmación y aplicar
  Q / ESC      salir
"""

import curses
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from src.app.controller import Controller
    from src.engine.module_loader import ModuleDefinition

# ── paleta de colores (índices) ───────────────────────────────────────────────
C_NORMAL   = 0
C_HEADER   = 1
C_SELECTED = 2   # módulo marcado para aplicar
C_CURSOR   = 3   # fila bajo el cursor
C_ON       = 4   # estado ON
C_OFF      = 5   # estado OFF / desconocido
C_LOW      = 6   # riesgo bajo
C_MED      = 7   # riesgo medio
C_HIGH     = 8   # riesgo alto
C_DIM      = 9   # texto secundario
C_ERR      = 10  # error
C_TITLE    = 11  # título ventana

_RISK_LABEL  = {"low": "LOW", "medium": "MED", "high": "HGH"}
_LEVEL_LABEL = {"basic": "BSC", "advanced": "ADV", "expert": "EXP", "paranoid": "PAR"}

_CAT_EMOJI = {
    "network":          "NET",
    "filesystem":       "FS ",
    "kernel":           "KRN",
    "services":         "SVC",
    "access_control":   "ACC",
    "system_hardening": "SYS",
    "privacy":          "PRV",
}


# ── helpers curses ─────────────────────────────────────────────────────────────

def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    bg = -1
    curses.init_pair(C_HEADER,   curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK,  curses.COLOR_GREEN)
    curses.init_pair(C_CURSOR,   curses.COLOR_BLACK,  curses.COLOR_WHITE)
    curses.init_pair(C_ON,       curses.COLOR_GREEN,  bg)
    curses.init_pair(C_OFF,      curses.COLOR_WHITE,  bg)
    curses.init_pair(C_LOW,      curses.COLOR_GREEN,  bg)
    curses.init_pair(C_MED,      curses.COLOR_YELLOW, bg)
    curses.init_pair(C_HIGH,     curses.COLOR_RED,    bg)
    curses.init_pair(C_DIM,      curses.COLOR_WHITE,  bg)
    curses.init_pair(C_ERR,      curses.COLOR_RED,    bg)
    curses.init_pair(C_TITLE,    curses.COLOR_CYAN,   bg)


def _safe_addstr(win, y, x, text, attr=0):
    """addstr sin explotar si el texto sale del borde."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    max_len = w - x - 1
    if max_len <= 0:
        return
    try:
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def _box_title(win, title: str):
    """Dibuja un recuadro con título centrado."""
    h, w = win.getmaxyx()
    win.box()
    t = f" {title} "
    x = max(0, (w - len(t)) // 2)
    _safe_addstr(win, 0, x, t, curses.color_pair(C_TITLE) | curses.A_BOLD)


def _risk_color(risk: str) -> int:
    return curses.color_pair({
        "low": C_LOW, "medium": C_MED, "high": C_HIGH
    }.get(risk, C_DIM))


# ── estructura de filas ────────────────────────────────────────────────────────

class Row:
    """Una fila en la lista — puede ser categoría o módulo."""
    def __init__(self, is_cat: bool, cat_label: str = "",
                 mod=None, state: str = "unknown"):
        self.is_cat    = is_cat
        self.cat_label = cat_label
        self.mod       = mod       # ModuleDefinition | None
        self.state     = state     # enabled|disabled|error|unknown
        self.selected  = False     # marcado para aplicar


# ── pantalla 1: selección ──────────────────────────────────────────────────────

class SelectionScreen:
    def __init__(self, stdscr, controller: "Controller"):
        self._scr  = stdscr
        self._ctrl = controller
        self._rows: List[Row] = []
        self._cursor   = 0      # fila actual (incluyendo categorías)
        self._offset   = 0      # scroll vertical
        self._mod_rows: List[int] = []   # índices de filas que son módulos

        self._build_rows()

    def _build_rows(self):
        self._rows    = []
        self._mod_rows = []
        cats = self._ctrl.modules_by_category()
        cat_labels = {
            "network": "NETWORK", "filesystem": "FILESYSTEM",
            "kernel": "KERNEL", "services": "SERVICES",
            "access_control": "ACCESS CONTROL",
            "system_hardening": "SYSTEM HARDENING",
            "privacy": "PRIVACY",
        }
        for cat, mods in sorted(cats.items()):
            self._rows.append(Row(is_cat=True, cat_label=cat_labels.get(cat, cat.upper())))
            for mod in mods:
                state = self._ctrl.module_state(mod.id)
                r = Row(is_cat=False, mod=mod, state=state)
                self._mod_rows.append(len(self._rows))
                self._rows.append(r)

        # posicionar cursor en primer módulo
        if self._mod_rows:
            self._cursor = self._mod_rows[0]

    def _selected_modules(self) -> List[Row]:
        return [r for r in self._rows if not r.is_cat and r.selected]

    def _current_mod_row(self) -> Row | None:
        if 0 <= self._cursor < len(self._rows):
            r = self._rows[self._cursor]
            if not r.is_cat:
                return r
        return None

    def _move_cursor(self, delta: int):
        target = self._cursor + delta
        # buscar el próximo módulo en la dirección indicada
        step = 1 if delta > 0 else -1
        pos  = self._cursor + step
        while 0 <= pos < len(self._rows):
            if not self._rows[pos].is_cat:
                self._cursor = pos
                return
            pos += step

    def _toggle_current(self):
        r = self._current_mod_row()
        if r and r.mod and r.mod.available:
            r.selected = not r.selected

    def _toggle_all(self):
        available = [r for r in self._rows if not r.is_cat and r.mod and r.mod.available]
        # si todos están seleccionados → deseleccionar todos, si no → seleccionar todos
        all_sel = all(r.selected for r in available)
        for r in available:
            r.selected = not all_sel

    def _refresh_states(self):
        for r in self._rows:
            if not r.is_cat and r.mod:
                r.state = self._ctrl.module_state(r.mod.id)

    def draw(self):
        self._scr.erase()
        h, w = self._scr.getmaxyx()

        # ── header ──
        header = " lockd — Modo Avanzado "
        self._scr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
        self._scr.addstr(0, 0, header.ljust(w - 1))
        self._scr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

        sel_count = len(self._selected_modules())
        info = f" {sel_count} seleccionado(s) "
        _safe_addstr(self._scr, 0, w - len(info) - 1, info,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)

        # ── footer ──
        footer = "  ↑↓=mover  SPC=marcar  A=todos  P=preview  ENTER=aplicar  Q=salir"
        self._scr.attron(curses.color_pair(C_HEADER))
        self._scr.addstr(h - 1, 0, footer[:w - 1].ljust(w - 1))
        self._scr.attroff(curses.color_pair(C_HEADER))

        # ── columnas header ──
        col_hdr = f"  {'MÓDULO':<36} {'EST':>3}  {'RIESGO':>6}  {'NIV':>3}  {'APP':>3}"
        _safe_addstr(self._scr, 1, 0, col_hdr[:w - 1],
                     curses.A_BOLD | curses.A_UNDERLINE)

        # ── lista ──
        list_h  = h - 3   # filas disponibles para lista
        visible = self._rows[self._offset: self._offset + list_h]

        # ajustar scroll
        if self._cursor < self._offset:
            self._offset = self._cursor
        elif self._cursor >= self._offset + list_h:
            self._offset = self._cursor - list_h + 1

        visible = self._rows[self._offset: self._offset + list_h]

        for i, row in enumerate(visible):
            screen_y  = i + 2
            abs_idx   = i + self._offset
            is_cursor = (abs_idx == self._cursor)

            if row.is_cat:
                cat_icon = _CAT_EMOJI.get(row.cat_label.lower().replace(" ", "_"), "───")
                label    = f"  [{cat_icon}] {row.cat_label} "
                attr     = curses.color_pair(C_TITLE) | curses.A_BOLD
                _safe_addstr(self._scr, screen_y, 0, label, attr)
                # línea horizontal
                line_x = len(label)
                _safe_addstr(self._scr, screen_y, line_x,
                             "─" * max(0, w - line_x - 1),
                             curses.color_pair(C_DIM))
            else:
                mod   = row.mod
                state = row.state
                avail = mod.available if mod else False

                # checkbox
                chk = "[✓]" if row.selected else "[ ]"

                # nombre
                name = mod.id if mod else "?"
                name = (name[:33] + "…") if len(name) > 34 else name

                # estado actual
                if state == "enabled":
                    st_str  = " ON"
                    st_attr = curses.color_pair(C_ON) | curses.A_BOLD
                elif state == "disabled":
                    st_str  = "OFF"
                    st_attr = curses.color_pair(C_OFF)
                elif state == "error":
                    st_str  = "ERR"
                    st_attr = curses.color_pair(C_ERR) | curses.A_BOLD
                else:
                    st_str  = " ─ "
                    st_attr = curses.color_pair(C_DIM)

                risk  = mod.risk_level if mod else ""
                level = mod.security_level if mod else ""
                app   = "OK" if avail else "N/A"

                line = f"  {chk} {name:<34} "

                # atributo base de la fila
                if is_cursor and row.selected:
                    base_attr = curses.color_pair(C_SELECTED) | curses.A_REVERSE
                elif is_cursor:
                    base_attr = curses.color_pair(C_CURSOR)
                elif row.selected:
                    base_attr = curses.color_pair(C_SELECTED)
                elif not avail:
                    base_attr = curses.color_pair(C_DIM)
                else:
                    base_attr = curses.color_pair(C_NORMAL)

                _safe_addstr(self._scr, screen_y, 0, line, base_attr)

                # estado coloreado
                col_state = len(line)
                _safe_addstr(self._scr, screen_y, col_state, st_str, st_attr)

                # riesgo coloreado
                risk_str  = f"  [{_RISK_LABEL.get(risk, '---')}]"
                col_risk  = col_state + 3
                _safe_addstr(self._scr, screen_y, col_risk, risk_str,
                             _risk_color(risk) if not is_cursor else base_attr)

                # nivel
                lvl_str = f"  [{_LEVEL_LABEL.get(level, '---')}]"
                col_lvl = col_risk + len(risk_str)
                _safe_addstr(self._scr, screen_y, col_lvl, lvl_str, base_attr)

                # disponible
                col_app = col_lvl + len(lvl_str)
                app_attr = (curses.color_pair(C_OFF) | curses.A_DIM) if not avail else base_attr
                _safe_addstr(self._scr, screen_y, col_app, f"  {app}", app_attr)

        self._scr.refresh()

    def run(self) -> str:
        """
        Devuelve:
          'apply'   → el usuario pulsó ENTER con módulos seleccionados
          'quit'    → el usuario salió
        Rellena self._rows con .selected = True para los elegidos.
        """
        while True:
            self.draw()
            try:
                key = self._scr.getch()
            except KeyboardInterrupt:
                return "quit"

            if key in (ord("q"), ord("Q"), 27):   # Q o ESC
                return "quit"
            elif key == curses.KEY_UP:
                self._move_cursor(-1)
            elif key == curses.KEY_DOWN:
                self._move_cursor(1)
            elif key == ord(" "):
                self._toggle_current()
            elif key in (ord("a"), ord("A")):
                self._toggle_all()
            elif key in (ord("p"), ord("P")):
                r = self._current_mod_row()
                if r and r.mod:
                    PreviewScreen(self._scr, r.mod).run()
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                if self._selected_modules():
                    return "apply"
            elif key == curses.KEY_RESIZE:
                pass   # re-draw en el próximo ciclo


# ── pantalla 2: preview del script ────────────────────────────────────────────

class PreviewScreen:
    def __init__(self, stdscr, mod):
        self._scr = stdscr
        self._mod = mod

    def _load_script(self) -> List[str]:
        script = self._mod.enable_script
        if not script or not Path(script).exists():
            return [f"Script no encontrado: {script}"]
        try:
            lines = Path(script).read_text().splitlines()
            return lines or ["(vacío)"]
        except OSError as e:
            return [f"Error al leer: {e}"]

    def run(self):
        lines  = self._load_script()
        offset = 0

        while True:
            self._scr.erase()
            h, w = self._scr.getmaxyx()

            # header
            title = f" Preview: {self._mod.id}/enable.sh "
            self._scr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
            self._scr.addstr(0, 0, title.ljust(w - 1))
            self._scr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

            # contenido
            list_h   = h - 2
            visible  = lines[offset: offset + list_h]
            for i, line in enumerate(visible):
                attr = curses.color_pair(C_DIM)
                # resaltar comentarios y keywords
                stripped = line.strip()
                if stripped.startswith("#"):
                    attr = curses.color_pair(C_MED)
                elif any(stripped.startswith(k) for k in ("if ", "fi", "function", "check_root", "DRY_RUN")):
                    attr = curses.color_pair(C_ON)
                _safe_addstr(self._scr, i + 1, 2, line, attr)

            # footer
            footer = f"  ↑↓=scroll  Q/ESC=volver  [{offset+1}-{min(offset+list_h, len(lines))}/{len(lines)} líneas]"
            self._scr.attron(curses.color_pair(C_HEADER))
            self._scr.addstr(h - 1, 0, footer[:w - 1].ljust(w - 1))
            self._scr.attroff(curses.color_pair(C_HEADER))

            self._scr.refresh()

            key = self._scr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break
            elif key == curses.KEY_UP:
                offset = max(0, offset - 1)
            elif key == curses.KEY_DOWN:
                offset = min(max(0, len(lines) - list_h), offset + 1)
            elif key == curses.KEY_NPAGE:
                offset = min(max(0, len(lines) - list_h), offset + list_h)
            elif key == curses.KEY_PPAGE:
                offset = max(0, offset - list_h)


# ── pantalla 3: confirmación ───────────────────────────────────────────────────

class ConfirmScreen:
    def __init__(self, stdscr, selected: List[Row]):
        self._scr      = stdscr
        self._selected = selected

    def run(self) -> bool:
        """Devuelve True si el usuario confirma."""
        while True:
            self._scr.erase()
            h, w = self._scr.getmaxyx()

            self._scr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
            self._scr.addstr(0, 0, " Confirmación — Módulos a aplicar ".ljust(w - 1))
            self._scr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

            _safe_addstr(self._scr, 2, 2,
                         f"Se van a aplicar {len(self._selected)} módulos:",
                         curses.A_BOLD)

            for i, row in enumerate(self._selected[:h - 8]):
                mod      = row.mod
                risk_c   = _risk_color(mod.risk_level)
                reboot   = " ⚠ REQUIERE REINICIO" if mod.requires_reboot else ""
                line     = f"  {'→':>2}  {mod.id:<36} [{_RISK_LABEL.get(mod.risk_level,'---')}]{reboot}"
                _safe_addstr(self._scr, 4 + i, 0, line, risk_c)

            warn_y = h - 5
            if any(r.mod.risk_level == "high" for r in self._selected):
                _safe_addstr(self._scr, warn_y, 2,
                             "⚠  Hay módulos de riesgo ALTO. Asegurate de tener acceso SSH configurado.",
                             curses.color_pair(C_HIGH) | curses.A_BOLD)

            _safe_addstr(self._scr, h - 3, 2,
                         "¿Continuar? pkexec pedirá tu contraseña de administrador.",
                         curses.color_pair(C_DIM))

            self._scr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
            self._scr.addstr(h - 1, 0,
                             "  ENTER=aplicar ahora   Q/ESC=cancelar".ljust(w - 1))
            self._scr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

            self._scr.refresh()

            key = self._scr.getch()
            if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                return True
            elif key in (ord("q"), ord("Q"), 27):
                return False


# ── pantalla 4: ejecución en vivo ─────────────────────────────────────────────

class ExecutionScreen:
    def __init__(self, stdscr, selected: List[Row], controller: "Controller"):
        self._scr      = stdscr
        self._selected = selected
        self._ctrl     = controller
        self._log: List[Tuple[str, int]] = []  # (texto, attr)

    def _append(self, text: str, attr: int = 0):
        self._log.append((text, attr))

    def _draw(self, running: bool = True):
        self._scr.erase()
        h, w = self._scr.getmaxyx()

        title = " Aplicando módulos… " if running else " Aplicación completada "
        self._scr.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
        self._scr.addstr(0, 0, title.ljust(w - 1))
        self._scr.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)

        list_h = h - 2
        visible = self._log[max(0, len(self._log) - list_h):]
        for i, (text, attr) in enumerate(visible):
            _safe_addstr(self._scr, i + 1, 0, text, attr)

        footer = "  Ejecutando…" if running else "  ENTER / Q — volver al menú"
        self._scr.attron(curses.color_pair(C_HEADER))
        self._scr.addstr(h - 1, 0, footer[:w - 1].ljust(w - 1))
        self._scr.attroff(curses.color_pair(C_HEADER))

        self._scr.refresh()

    def run(self):
        total = len(self._selected)

        for i, row in enumerate(self._selected):
            mod = row.mod
            self._append(
                f"[{i+1}/{total}] Aplicando: {mod.id}",
                curses.color_pair(C_TITLE) | curses.A_BOLD,
            )
            self._draw(running=True)

            result = self._ctrl.enable(mod.id)

            if result is None:
                self._append("  ✗ Error: no se pudo ejecutar", curses.color_pair(C_HIGH))
            elif result.cancelled:
                self._append("  ↩ Cancelado por el usuario", curses.color_pair(C_MED))
            elif result.ok or result.dry_run:
                verb = "(simulado)" if result.dry_run else "OK"
                self._append(f"  ✓ {verb}", curses.color_pair(C_ON) | curses.A_BOLD)
                if result.stdout:
                    for line in result.stdout.strip().splitlines()[:6]:
                        self._append(f"    {line}", curses.color_pair(C_DIM))
            else:
                self._append(f"  ✗ Error (rc={result.rc})", curses.color_pair(C_HIGH))
                for line in (result.stderr or "").strip().splitlines()[:4]:
                    self._append(f"    {line}", curses.color_pair(C_ERR))

            self._append("", 0)

        # resumen
        ok  = sum(1 for r in self._selected
                  if self._ctrl.module_state(r.mod.id) == "enabled")
        err = total - ok
        self._append(
            f"── Finalizado: {ok} OK  {err} errores ──",
            curses.color_pair(C_ON) | curses.A_BOLD if not err
            else curses.color_pair(C_HIGH) | curses.A_BOLD,
        )
        self._draw(running=False)

        # esperar tecla para volver
        while True:
            key = self._scr.getch()
            if key in (curses.KEY_ENTER, ord("\n"), ord("\r"),
                       ord("q"), ord("Q"), 27):
                break


# ── punto de entrada ───────────────────────────────────────────────────────────

def _main(stdscr, controller: "Controller"):
    curses.curs_set(0)
    stdscr.keypad(True)
    _init_colors()

    sel_screen = SelectionScreen(stdscr, controller)

    while True:
        action = sel_screen.run()

        if action == "quit":
            break

        selected = sel_screen._selected_modules()
        if not selected:
            continue

        confirmed = ConfirmScreen(stdscr, selected).run()
        if not confirmed:
            continue

        ExecutionScreen(stdscr, selected, controller).run()

        # refrescar estados tras aplicar
        sel_screen._refresh_states()
        # deseleccionar los que se aplicaron correctamente
        for r in selected:
            if controller.module_state(r.mod.id) == "enabled":
                r.selected = False


def run_tui(controller: "Controller"):
    """Punto de entrada desde CLI."""
    try:
        curses.wrapper(_main, controller)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # curses a veces deja la terminal rota — resetear
        curses.endwin()
        print(f"\n[lockd] TUI error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # asegurarse de restaurar la terminal
        try:
            curses.endwin()
        except Exception:
            pass
