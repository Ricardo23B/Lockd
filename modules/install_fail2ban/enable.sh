#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="install_fail2ban"
CONF="${SYSROOT}/etc/fail2ban/jail.d/lockd-ssh.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Instalaría fail2ban si falta (queda instalado al desactivar)"
    warn "[DRY-RUN] Crearía $CONF (jail sshd)"
    warn "[DRY-RUN] Guardaría el estado de fail2ban y lo dejaría habilitado y activo"
    exit 0
fi
# Atómico: si fail2ban no arranca o no toma la jail, se deshace lo de esta
# ejecución (el paquete queda instalado).
estado_nuevo=1
if servicio_guardado "$MOD" fail2ban; then estado_nuevo=0; fi
# El estado se guarda antes de instalar: el paquete arranca el servicio al
# instalarse, y lo que cuenta es cómo estaba antes de Lockd.
servicio_guardar "$MOD" fail2ban
if ! paquete_instalar "$MOD" fail2ban; then
    if [ "$estado_nuevo" = 1 ]; then servicio_olvidar "$MOD" fail2ban; fi
    error "No se pudo instalar fail2ban."
    exit 1
fi
activo_antes=0
if systemctl is-active --quiet fail2ban; then activo_antes=1; fi
conf_previa=""
if [ -f "$CONF" ]; then conf_previa="$(cat "$CONF")"; fi

mkdir -p "$(dirname "$CONF")"
write_file "$CONF" 0644 << 'CONF'
[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 5
bantime  = 3600
findtime = 600
CONF

# Si ya corría, se recarga para que tome la jail; si no, la toma al arrancar.
if systemctl enable --now fail2ban \
    && { [ "$activo_antes" = 0 ] || systemctl reload fail2ban; }; then
    info "Fail2ban activo con la jail sshd de Lockd."
    exit 0
fi
if [ -n "$conf_previa" ]; then
    printf '%s\n' "$conf_previa" | write_file "$CONF" 0644
else
    rm -f "$CONF"
fi
if [ "$estado_nuevo" = 1 ]; then servicio_restaurar "$MOD" fail2ban; fi
error "fail2ban no arrancó con la jail de Lockd: esta activación se deshizo."
exit 1
