#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="automatic_security_updates"
AUTO_CONF="${SYSROOT}/etc/apt/apt.conf.d/20auto-upgrades"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Devolvería $AUTO_CONF y unattended-upgrades a su estado previo a Lockd"
    exit 0
fi
if baseline_active "$MOD"; then
    baseline_restore "$MOD" "$AUTO_CONF"
    baseline_end "$MOD"
else
    # Activado con una versión anterior de Lockd: sin línea base, se apagan
    # las actualizaciones periódicas como hacía esa versión.
    warn "No hay línea base de $AUTO_CONF: se desactivan las actualizaciones periódicas."
    write_file "$AUTO_CONF" 0644 << 'CONF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
CONF
fi
servicio_restaurar "$MOD" unattended-upgrades
paquetes_avisar "$MOD"
info "Actualizaciones automáticas en su estado previo."
