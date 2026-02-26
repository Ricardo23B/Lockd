#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BACKUP_DIR="${BACKUP_BASE}/restrict_compilers"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] groupadd compiler"
    warn "[DRY-RUN] chmod o-x /usr/bin/gcc* /usr/bin/g++* /usr/bin/cc /usr/bin/make"
    exit 0
fi
mkdir -p "$BACKUP_DIR"
getent group compiler &>/dev/null || groupadd compiler
COMPILERS=$(find /usr/bin /usr/local/bin -maxdepth 1     -name "gcc*" -o -name "g++*" -o -name "cc" -o -name "cc-*"     -o -name "make" -o -name "gmake" 2>/dev/null)
echo "$COMPILERS" > "$BACKUP_DIR/compiler_list.txt"
for bin in $COMPILERS; do
    [ -f "$bin" ] && chown root:compiler "$bin" && chmod o-x "$bin" &&         info "Restringido: $bin"
done
info "Compiladores restringidos al grupo 'compiler'."
info "Añadir usuario: sudo usermod -aG compiler <usuario>"
