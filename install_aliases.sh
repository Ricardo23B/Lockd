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
#   lockd / lt     → python3 <ruta>/lockd.py
#   lt-scan             → lockd scan
#   lt-adv              → lockd advanced  (TUI interactiva)
#   lt-status           → lockd status
#   lt-list             → lockd list

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
alias lockd='python3 $MAIN'
alias lt='python3 $MAIN'
alias lt-scan='python3 $MAIN scan'
alias lt-adv='python3 $MAIN advanced'
alias lt-status='python3 $MAIN status'
alias lt-list='python3 $MAIN list'
alias lt-sim='python3 $MAIN --dry-run'
$MARKER_END"

# ── modo remove ──────────────────────────────────────────────────────────────
if [ "${1:-}" = "--remove" ]; then
    if grep -q "$MARKER_START" "$RC_FILE" 2>/dev/null; then
        # eliminar el bloque entre marcadores
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
echo "  Alias disponibles:"
echo "    lockd / lt    → abrir Lockd"
echo "    lt-scan            → escanear el sistema"
echo "    lt-adv             → modo avanzado TUI (interactivo)"
echo "    lt-status          → estado de módulos"
echo "    lt-list            → listar módulos"
echo "    lt-sim             → modo simulación (dry-run)"
echo ""
echo "  Para activarlos ahora sin reiniciar la terminal:"
echo "    source $RC_FILE"
echo ""
echo "  Para desinstalar:"
echo "    bash $SCRIPT_DIR/install_aliases.sh --remove"
