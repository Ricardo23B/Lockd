#!/bin/bash
# enable_firewall (disable) — devuelve UFW al estado previo a Lockd: reglas,
# políticas y encendido/apagado. Si UFW ya estaba activo antes, queda activo.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
export LC_ALL=C

MOD="enable_firewall"
UFW_FILES=(/etc/default/ufw /etc/ufw/ufw.conf /etc/ufw/user.rules /etc/ufw/user6.rules)

if ! command -v ufw &>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] UFW no está instalado: nada que revertir."
        exit 0
    fi
    check_cmd ufw
fi

if baseline_active "$MOD"; then
    # ¿UFW estaba encendido antes de Lockd? Se lee del respaldo (no del archivo
    # actual) para que el dry-run informe lo mismo que haría la ejecución real.
    prev_enabled=no
    bak="$(ls -1t "${BACKUP_BASE}/${MOD}"/ufw.conf.bak.* 2>/dev/null | head -1 || true)"
    if [ -n "$bak" ] && grep -q '^ENABLED=yes' "$bak"; then
        prev_enabled=yes
    fi

    baseline_restore "$MOD" "${UFW_FILES[@]}"
    if [ "$prev_enabled" = "yes" ]; then
        apply "Recargar UFW con las reglas previas a Lockd" ufw --force enable
    else
        apply "Desactivar UFW (estaba inactivo antes de Lockd)" ufw --force disable
    fi
    baseline_end "$MOD"
else
    warn "Sin línea base (módulo activado con una versión anterior de Lockd)."
    warn "Solo se desactiva UFW. Esa versión hacía 'ufw reset': UFW guardó"
    warn "copias con fecha de tus reglas en /etc/ufw/*.rules.<fecha>."
    apply "Desactivar UFW" ufw --force disable
fi
[ "$DRY_RUN" = "1" ] || info "Cortafuegos revertido."
