#!/bin/bash
# setup.sh — Lockd installer y launcher
#
# Uso:
#   bash setup.sh               → instalación completa + lanza la app
#   bash setup.sh --only-setup  → instala todo pero no lanza
#   bash setup.sh --cli         → fuerza modo CLI tras instalar
#   bash setup.sh --gui         → fuerza modo GUI tras instalar
#   bash setup.sh --uninstall   → elimina aliases y configs de lockd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="$SCRIPT_DIR/lockd.py"

# ── colores ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
NC="\033[0m"

info()    { echo -e "${GREEN}[lockd]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }
title()   { echo -e "\n${CYAN}${BOLD}══ $* ══${NC}"; }
ok()      { echo -e "  ${GREEN}✓${NC} $*"; }
skip()    { echo -e "  ${YELLOW}–${NC} $* (ya instalado)"; }
failed()  { echo -e "  ${RED}✗${NC} $*"; }

# ── verificar que existe lockd.py ─────────────────────────────────────────────
if [ ! -f "$MAIN" ]; then
    error "lockd.py no encontrado en $SCRIPT_DIR"
    error "Ejecutá este script desde la raíz del proyecto."
    exit 1
fi

# ══ modo --uninstall ══════════════════════════════════════════════════════════
if [[ "${1:-}" == "--uninstall" ]]; then
    title "Lockd — Desinstalación"
    RC_FILE="$HOME/.bashrc"
    [ "$(basename "${SHELL:-bash}")" = "zsh" ] && RC_FILE="$HOME/.zshrc"

    if grep -q "# >>> Lockd aliases >>>" "$RC_FILE" 2>/dev/null; then
        python3 -c "
import re
txt = open('$RC_FILE').read()
txt = re.sub(r'\n?# >>> Lockd aliases >>>.*?# <<< Lockd aliases <<<\n?', '', txt, flags=re.DOTALL)
open('$RC_FILE', 'w').write(txt)
"
        ok "Aliases eliminados de $RC_FILE"
    else
        skip "No se encontraron aliases"
    fi
    info "Para eliminar la app por completo: rm -rf $SCRIPT_DIR"
    exit 0
fi

# ══ inicio setup ══════════════════════════════════════════════════════════════
title "Lockd — Setup"
echo ""

# ── paso 1: permisos de ejecución ─────────────────────────────────────────────
info "Paso 1/5 — Permisos de ejecución"
find "$SCRIPT_DIR/modules" -name "*.sh" -exec chmod +x {} \;
chmod +x "$SCRIPT_DIR/setup.sh"
ok "Scripts en modules/ marcados como ejecutables"

# ── paso 2: Python 3 ──────────────────────────────────────────────────────────
echo ""
info "Paso 2/5 — Python 3"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "$PY_VER"
else
    failed "Python3 no encontrado"
    warn "Instalar: sudo apt install python3"
    exit 1
fi

# ── paso 3: dependencias del sistema ─────────────────────────────────────────
echo ""
info "Paso 3/5 — Dependencias"

install_if_missing() {
    local pkg="$1"
    local label="${2:-$1}"
    if dpkg -s "$pkg" &>/dev/null 2>&1; then
        skip "$label"
    else
        warn "$label no encontrado. Instalando..."
        sudo apt-get install -y "$pkg" && ok "$label instalado" || failed "$label — instalación falló"
    fi
}

install_if_missing "python3-yaml"      "PyYAML"
install_if_missing "python3-gi"        "PyGObject (GTK bindings)"
install_if_missing "gir1.2-gtk-4.0"    "GTK 4.0"
install_if_missing "gir1.2-adw-1"      "libadwaita"
install_if_missing "policykit-1"       "Polkit"
install_if_missing "procps"            "procps (sysctl)"
install_if_missing "ufw"               "UFW (firewall)"

# verificar pkexec
if command -v pkexec &>/dev/null; then
    ok "pkexec disponible en $(command -v pkexec)"
else
    warn "pkexec no encontrado — las acciones privilegiadas no funcionarán"
    warn "Instalar: sudo apt install policykit-1"
fi

# ── paso 4: política de Polkit ────────────────────────────────────────────────
echo ""
info "Paso 4/5 — Política Polkit"
POLICY_SRC="$SCRIPT_DIR/packaging/polkit/io.github.lockd.policy"
POLICY_DST="/usr/share/polkit-1/actions/io.github.lockd.policy"

if [ -f "$POLICY_DST" ]; then
    skip "Política Polkit ya instalada"
elif [ -f "$POLICY_SRC" ]; then
    if sudo cp "$POLICY_SRC" "$POLICY_DST" 2>/dev/null; then
        ok "Política Polkit instalada en $POLICY_DST"
    else
        warn "No se pudo instalar la política Polkit (sin permisos sudo)"
        warn "Instalar manualmente: sudo cp $POLICY_SRC $POLICY_DST"
    fi
else
    warn "Archivo de política no encontrado: $POLICY_SRC"
fi

# ── paso 5: aliases en el shell ───────────────────────────────────────────────
echo ""
info "Paso 5/5 — Aliases"

detect_rc() {
    if [ "$(basename "${SHELL:-bash}")" = "zsh" ] || [ -n "${ZSH_VERSION:-}" ]; then
        echo "$HOME/.zshrc"
    else
        echo "$HOME/.bashrc"
    fi
}

RC_FILE="$(detect_rc)"
MARKER_START="# >>> Lockd aliases >>>"
MARKER_END="# <<< Lockd aliases <<<"

# eliminar bloque anterior si ya existía (actualización limpia)
if grep -q "$MARKER_START" "$RC_FILE" 2>/dev/null; then
    python3 -c "
import re
txt = open('$RC_FILE').read()
txt = re.sub(r'\n?# >>> Lockd aliases >>>.*?# <<< Lockd aliases <<<\n?', '', txt, flags=re.DOTALL)
open('$RC_FILE', 'w').write(txt)
"
fi

# escribir bloque nuevo
cat >> "$RC_FILE" << ALIASES

$MARKER_START
# Lockd — Linux hardening tool
# Generado por setup.sh — editar a mano si hace falta
alias lockd='python3 $MAIN'
alias lockd-scan='python3 $MAIN scan'
alias lockd-adv='python3 $MAIN advanced'
alias lockd-tui='python3 $MAIN tui'
alias lockd-status='python3 $MAIN status'
alias lockd-list='python3 $MAIN list'
alias lockd-sim='python3 $MAIN --dry-run'
alias lockd-profiles='python3 $MAIN profiles'
alias lockd-levels='python3 $MAIN levels'
$MARKER_END
ALIASES

ok "Aliases instalados en $RC_FILE"
echo ""
echo "      lockd              → abrir GUI o CLI automáticamente"
echo "      lockd-scan         → escanear el sistema"
echo "      lockd-adv          → modo avanzado TUI (funciona por SSH)"
echo "      lockd-sim          → dry-run global (simula sin aplicar)"
echo "      lockd-status       → estado actual de módulos"
echo "      lockd-list         → listar módulos disponibles"
echo "      lockd-profiles     → ver perfiles"
echo "      lockd-levels       → ver niveles"
echo ""

# ── resumen ───────────────────────────────────────────────────────────────────
title "Setup completo"
echo ""
info "Para activar los aliases ahora mismo (sin reiniciar terminal):"
echo ""
echo "      source $RC_FILE"
echo ""

# ── modo --only-setup → salir aquí ───────────────────────────────────────────
if [[ "${1:-}" == "--only-setup" ]]; then
    info "Modo --only-setup: no se lanza la app."
    echo ""
    echo "  Para lanzar más tarde:"
    echo "      python3 $MAIN        # auto-detecta GUI/CLI"
    echo "      python3 $MAIN scan   # CLI directo"
    echo "      python3 $MAIN tui    # TUI interactiva"
    echo ""
    exit 0
fi

# ── detectar entorno y lanzar ─────────────────────────────────────────────────
HAS_DISPLAY=false
IS_SSH=false
[[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] && HAS_DISPLAY=true
[[ -n "${SSH_CLIENT:-}" || -n "${SSH_TTY:-}" ]]      && IS_SSH=true

MODE="${1:-auto}"
if   [[ "$MODE" == "--gui" ]];  then LAUNCH="gui"
elif [[ "$MODE" == "--cli" ]];  then LAUNCH="cli"
elif $IS_SSH;                   then LAUNCH="cli"
elif $HAS_DISPLAY;              then LAUNCH="gui"
else                                 LAUNCH="cli"
fi

echo ""

if [[ "$LAUNCH" == "gui" ]]; then
    # verificar GTK antes de abrir
    if python3 -c "import gi; gi.require_version('Adw','1'); from gi.repository import Adw" 2>/dev/null; then
        info "Abriendo GUI..."
        python3 "$MAIN"
    else
        warn "GTK4/Adwaita no disponible. Abriendo modo CLI..."
        python3 "$MAIN" --cli
    fi

else
    info "Modo CLI${IS_SSH:+ — conexión SSH detectada}"
    echo ""
    echo "  ¿Qué querés hacer?"
    echo ""
    echo "  1) Escanear el sistema"
    echo "  2) Ver módulos disponibles"
    echo "  3) Aplicar perfil recomendado"
    echo "  4) Modo avanzado TUI  ← interactivo, ideal para SSH"
    echo "  5) Salir"
    echo ""
    read -rp "  Opción [1-5]: " opt

    case "${opt:-5}" in
        1) python3 "$MAIN" scan ;;
        2) python3 "$MAIN" list ;;
        3)
            echo ""
            # mostrar perfil sugerido del último scan si existe
            python3 "$MAIN" scan 2>/dev/null | grep -A2 "Perfil sugerido" || true
            echo ""
            read -rp "  Nombre del perfil [home_desktop / server / paranoid]: " profile
            [[ -n "${profile:-}" ]] && python3 "$MAIN" profile "$profile" --yes
            ;;
        4) python3 "$MAIN" advanced ;;
        5|*) info "Saliendo. Podés lanzar Lockd luego con: lockd"; exit 0 ;;
    esac
fi
