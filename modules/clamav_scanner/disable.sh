#!/usr/bin/env bash
# clamav_scanner/disable.sh — desactiva los escaneos programados de ClamAV
set -euo pipefail
. "$(dirname "$0")/../_common.sh"
check_root

TIMER_FILE="/etc/systemd/system/lockd-clamav.timer"
SERVICE_FILE="/etc/systemd/system/lockd-clamav.service"

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would: systemctl disable --now lockd-clamav.timer"
    warn "[DRY-RUN] Would: rm $TIMER_FILE $SERVICE_FILE && systemctl daemon-reload"
    exit 0
fi

info "Desactivando escaneos programados de ClamAV..."

if systemctl is-active --quiet lockd-clamav.timer 2>/dev/null; then
    systemctl disable --now lockd-clamav.timer
    info "Timer desactivado."
else
    warn "El timer no estaba activo."
fi

# Eliminar archivos de systemd
rm -f "$TIMER_FILE" "$SERVICE_FILE"
systemctl daemon-reload

info "Escaneos programados de ClamAV desactivados."
info "ClamAV sigue instalado. Los logs y cuarentena se conservan en /var/log/lockd/ y /var/quarantine/lockd/"
