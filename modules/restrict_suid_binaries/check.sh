#!/bin/bash
# Activo si el módulo dejó su lista de cambios (puede estar vacía si ningún
# binario de la denylist existía en el sistema).
SUID_LIST="${LOCKD_BACKUP_BASE:-/var/lib/lockd/backups}/restrict_suid_binaries/suid_removed.txt"
[ -f "$SUID_LIST" ] && exit 0 || exit 1
