#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="automatic_security_updates"
AUTO_CONF="${SYSROOT}/etc/apt/apt.conf.d/20auto-upgrades"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Instalaría unattended-upgrades si falta (queda instalado al desactivar)"
    warn "[DRY-RUN] Guardaría $AUTO_CONF y el estado de unattended-upgrades"
    warn "[DRY-RUN] Configuraría $AUTO_CONF"
    exit 0
fi
# Lo previo se guarda antes de instalar: el paquete trae su propio
# 20auto-upgrades y arranca su servicio al instalarse.
baseline_begin "$MOD" "$AUTO_CONF"
servicio_guardar "$MOD" unattended-upgrades
paquete_instalar "$MOD" unattended-upgrades
write_file "$AUTO_CONF" 0644 << 'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
systemctl enable --now unattended-upgrades 2>/dev/null \
    || warn "No se pudo habilitar unattended-upgrades.service: las actualizaciones periódicas siguen por los timers de apt."
info "Actualizaciones automáticas configuradas."
