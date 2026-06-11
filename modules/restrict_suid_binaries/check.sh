#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable.
# Activo si el módulo dejó su lista de cambios (puede estar vacía si ningún
# binario de la denylist existía). Si el directorio de backups existe pero
# no es legible (corre sin root y el dir es 0750), no se inventa un
# resultado: exit 2 y el estado registrado se conserva.
BASE="${LOCKD_BACKUP_BASE:-/var/lib/lockd/backups}"
[ ! -e "$BASE" ] && exit 1                       # Lockd nunca hizo backups: inactivo
[ ! -r "$BASE" ] || [ ! -x "$BASE" ] && exit 2   # sin permisos: no determinable
SUID_LIST="$BASE/restrict_suid_binaries/suid_removed.txt"
[ -f "$SUID_LIST" ] && exit 0 || exit 1
