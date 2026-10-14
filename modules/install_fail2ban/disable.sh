#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="install_fail2ban"
CONF="${SYSROOT}/etc/fail2ban/jail.d/lockd-ssh.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Borraría $CONF y recargaría fail2ban si está activo"
    warn "[DRY-RUN] Devolvería fail2ban a su estado previo (habilitado/activo)"
    exit 0
fi
rm -f "$CONF"
# Las demás jails siguen: solo se descarga la de Lockd.
if systemctl is-active --quiet fail2ban; then
    systemctl reload fail2ban || warn "No se pudo recargar fail2ban: la jail de Lockd sale al reiniciarlo."
fi
servicio_restaurar "$MOD" fail2ban
paquetes_avisar "$MOD"
info "Fail2ban en su estado previo."
