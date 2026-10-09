#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable. Sin root.
#
# Activo = el .conf de Lockd existe Y cada clave tiene en ejecución el valor
# pedido (antes bastaba con que el archivo existiera). ip_forward no cuenta:
# runtimes de contenedores y VPN lo encienden al arrancar, legítimamente.
# LOCKD_SYSCTL_CONF / LOCKD_PROC_SYS solo existen para los tests.
export LC_ALL=C
CONF="${LOCKD_SYSCTL_CONF:-/etc/sysctl.d/99-lockd-hardening.conf}"
PROC="${LOCKD_PROC_SYS:-/proc/sys}"

[ -f "$CONF" ] || exit 1
[ -r "$CONF" ] || exit 2

rc=0
while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*([a-z0-9_.-]+)[[:space:]]*=[[:space:]]*(.*[^[:space:]]) ]] || continue
    key="${BASH_REMATCH[1]}"; want="${BASH_REMATCH[2]}"
    [ "$key" = "net.ipv4.ip_forward" ] && continue
    path="${PROC}/${key//.//}"
    if [ ! -r "$path" ]; then
        rc=2
        continue
    fi
    read -r cur < "$path" || cur=""
    [ "$cur" = "$want" ] || exit 1
done < "$CONF"
exit "$rc"
