#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

BACKUP_DIR="${BACKUP_BASE}/restrict_suid_binaries"
SUID_LIST="$BACKUP_DIR/suid_removed.txt"
AUDIT_LIST="$BACKUP_DIR/suid_audit.txt"

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Restauraría el bit SUID a los binarios de $SUID_LIST"
    exit 0
fi

if [ ! -f "$SUID_LIST" ]; then
    warn "No hay lista de binarios modificados. Nada que restaurar."
    exit 0
fi

restored=0
while IFS= read -r bin; do
    [ -n "$bin" ] || continue
    if [ -f "$bin" ]; then
        chmod u+s "$bin" && info "SUID restaurado: $bin"
        restored=$((restored + 1))
    else
        warn "Ya no existe (omitido): $bin"
    fi
done < "$SUID_LIST"

rm -f "$SUID_LIST" "$AUDIT_LIST"
info "SUID restaurado en $restored binarios."
