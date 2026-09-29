#!/bin/bash
# kernel_sysctl_hardening (disable) — elimina el .conf y devuelve cada clave
# a su valor en ejecución previo a Lockd (runtime.snapshot). Solo revierte lo
# que Lockd dejó: si una clave cambió después (otro servicio, el usuario), se
# respeta y se informa.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
export LC_ALL=C

MOD="kernel_sysctl_hardening"
CONF="/etc/sysctl.d/99-lockd-hardening.conf"
SNAPSHOT="${BACKUP_BASE}/${MOD}/runtime.snapshot"

if [ -z "$SYSCTL" ]; then
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] sysctl no encontrado: la ejecución real fallaría (apt install procps)."
        exit 0
    fi
    error "sysctl no encontrado. Instalar: apt install procps"
    exit 1
fi

sysctl_system_quiet() { "$SYSCTL" --system >/dev/null; }

if [ ! -f "$SNAPSHOT" ]; then
    warn "Sin snapshot de valores previos (módulo activado con una versión anterior)."
    warn "Se elimina la config; las claves sin otro .conf conservan su valor actual hasta reiniciar."
    apply "Eliminar $CONF" rm -f "$CONF"
    apply "Reaplicar sysctl.d del sistema" sysctl_system_quiet
    baseline_end "$MOD"
    exit 0
fi

# Lo que Lockd dejó configurado: solo se revierte una clave si todavía vale eso.
declare -A LOCKD_SET=()
if [ -r "$CONF" ]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*([a-z0-9_.-]+)[[:space:]]*=[[:space:]]*(.*[^[:space:]]) ]] || continue
        LOCKD_SET["${BASH_REMATCH[1]}"]="${BASH_REMATCH[2]}"
    done < "$CONF"
fi

apply "Eliminar $CONF" rm -f "$CONF"
while IFS='=' read -r key prev; do
    [ -n "$key" ] && [ -n "$prev" ] || continue
    cur="$("$SYSCTL" -n "$key" 2>/dev/null || true)"
    if [ -n "${LOCKD_SET[$key]+x}" ] && [ "$cur" != "${LOCKD_SET[$key]}" ]; then
        warn "$key cambió después de Lockd (ahora $cur): se respeta."
        continue
    fi
    [ "$cur" = "$prev" ] && continue
    apply "Restaurar $key=$prev (Lockd: $cur)" "$SYSCTL" -q -w "${key}=${prev}"
done < "$SNAPSHOT"

apply "Eliminar snapshot" rm -f "$SNAPSHOT"
baseline_end "$MOD"
[ "$DRY_RUN" = "1" ] || info "Parámetros de kernel revertidos a sus valores previos."
