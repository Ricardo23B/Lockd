# NOTA: los aliases ahora se instalan automáticamente con setup.sh
# Este archivo queda como alternativa standalone.

#!/bin/bash
# install_aliases.sh — instala alias de Lockd en tu shell
#
# Uso:
#   bash install_aliases.sh          # detecta shell automáticamente
#   bash install_aliases.sh --remove # elimina los alias
#
# Alias instalados:
#   lockd               → python3 <ruta>/lockd.py
#   lockd-scan          → lockd scan
#   lockd-adv           → lockd advanced  (TUI interactiva)
#   lockd-status        → lockd status
#   lockd-list          → lockd list
#   lockd-sim           → lockd --dry-run
#
#   ClamAV:
#   lockd-clamav-on     → activar ClamAV + escaneos programados
#   lockd-clamav-off    → desactivar escaneos programados
#   lockd-clamav-status → ver estado del módulo ClamAV
#   lockd-clamav-info   → información detallada del módulo
#   lockd-clamav-scan   → ejecutar escaneo manual ahora mismo

set -euo pipefail

# ── detectar ruta del proyecto ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="$SCRIPT_DIR/lockd.py"

if [ ! -f "$MAIN" ]; then
    echo "[error] No se encontró lockd.py en $SCRIPT_DIR"
    echo "        Ejecutá este script desde la carpeta del proyecto."
    exit 1
fi

# ── detectar archivo de configuración del shell ──────────────────────────────
detect_rc() {
    if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
        echo "$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [ "$(basename "$SHELL")" = "bash" ]; then
        echo "$HOME/.bashrc"
    elif [ -f "$HOME/.config/fish/config.fish" ]; then
        echo "$HOME/.config/fish/config.fish"
    else
        echo "$HOME/.bashrc"
    fi
}

RC_FILE="$(detect_rc)"

# ── bloque de alias ──────────────────────────────────────────────────────────
MARKER_START="# >>> Lockd aliases >>>"
MARKER_END="# <<< Lockd aliases <<<"

ALIAS_BLOCK="$MARKER_START
# ── Lockd general ────────────────────────────────────────────────────────────
alias lockd='python3 $MAIN'
alias lockd-gui='python3 $MAIN --gui'
alias lockd-tui='python3 $MAIN advanced'
alias lockd-scan='python3 $MAIN scan'
alias lockd-adv='python3 $MAIN advanced'
alias lockd-status='python3 $MAIN status'
alias lockd-list='python3 $MAIN list'
alias lockd-sim='python3 $MAIN --dry-run'

# ── ClamAV ───────────────────────────────────────────────────────────────────
alias lockd-clamav-on='sudo python3 $MAIN enable clamav_scanner'
alias lockd-clamav-off='sudo python3 $MAIN disable clamav_scanner'
alias lockd-clamav-status='python3 $MAIN status | grep clamav'
alias lockd-clamav-info='python3 $MAIN info clamav_scanner'
alias lockd-clamav-scan='sudo clamscan --recursive --infected /home /tmp /var/tmp'
$MARKER_END"

# ── modo remove ──────────────────────────────────────────────────────────────
if [ "${1:-}" = "--remove" ]; then
    if grep -q "$MARKER_START" "$RC_FILE" 2>/dev/null; then
        python3 -c "
import re, sys
txt = open('$RC_FILE').read()
txt = re.sub(r'\n?# >>> Lockd aliases >>>.*?# <<< Lockd aliases <<<\n?',
             '', txt, flags=re.DOTALL)
open('$RC_FILE', 'w').write(txt)
print('Alias eliminados de $RC_FILE')
"
    else
        echo "No se encontraron alias de Lockd en $RC_FILE"
    fi
    exit 0
fi

# ── instalar ─────────────────────────────────────────────────────────────────
# eliminar bloque anterior si existe (upgrade limpio)
if grep -q "$MARKER_START" "$RC_FILE" 2>/dev/null; then
    python3 -c "
import re
txt = open('$RC_FILE').read()
txt = re.sub(r'\n?# >>> Lockd aliases >>>.*?# <<< Lockd aliases <<<\n?',
             '', txt, flags=re.DOTALL)
open('$RC_FILE', 'w').write(txt)
"
fi

# añadir bloque nuevo
echo "" >> "$RC_FILE"
echo "$ALIAS_BLOCK" >> "$RC_FILE"

echo ""
echo "✓ Alias instalados en: $RC_FILE"
echo ""
echo "  ── Lanzador ──────────────────────────────────────────────"
echo "    lockd              → GUI si hay display, TUI si no"
echo "    lockd-gui          → forzar GUI GTK4 (requiere display)"
echo "    lockd-tui          → forzar TUI interactiva en terminal"
echo "    lockd-adv          → igual que lockd-tui"
echo ""
echo "  ── General ───────────────────────────────────────────────"
echo "    lockd-scan         → auditoría del sistema"
echo "    lockd-status       → estado de todos los módulos"
echo "    lockd-list         → listar módulos disponibles"
echo "    lockd-sim          → modo simulación (dry-run)"
echo ""
echo "  ── ClamAV ───────────────────────────────────────────────"
echo "    lockd-clamav-on    → activar ClamAV + escaneos programados"
echo "    lockd-clamav-off   → desactivar escaneos programados"
echo "    lockd-clamav-status → ver estado del módulo ClamAV"
echo "    lockd-clamav-info  → información detallada del módulo"
echo "    lockd-clamav-scan  → escaneo manual inmediato"
echo ""
echo "  Para activarlos ahora sin reiniciar la terminal:"
echo "    source $RC_FILE"
echo ""
echo "  Para desinstalar:"
echo "    bash $SCRIPT_DIR/install_aliases.sh --remove"