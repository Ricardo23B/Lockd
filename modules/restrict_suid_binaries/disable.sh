#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
SUID_LIST="${BACKUP_BASE}/restrict_suid_binaries/suid_removed.txt"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Restore SUID bit to binaries in $SUID_LIST"; exit 0
fi
if [ ! -f "$SUID_LIST" ]; then
    warn "No hay lista de binarios modificados. Nada que restaurar."
    exit 0
fi
while IFS= read -r bin; do
    [ -f "$bin" ] && chmod u+s "$bin" && info "SUID restaurado: $bin"
done < "$SUID_LIST"
rm -f "$SUID_LIST"
info "Binarios SUID restaurados."
