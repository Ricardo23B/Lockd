#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BACKUP_DIR="${BACKUP_BASE}/restrict_compilers"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Restore compiler permissions"; exit 0
fi
LIST="$BACKUP_DIR/compiler_list.txt"
if [ -f "$LIST" ]; then
    while IFS= read -r bin; do
        [ -f "$bin" ] && chown root:root "$bin" && chmod o+x "$bin" &&             info "Restaurado: $bin"
    done < "$LIST"
fi
info "Permisos de compiladores restaurados."
