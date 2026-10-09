#!/bin/bash
# enable_firewall — UFW con entrante denegado por defecto.
#
# Invariantes (antes se violaban las tres):
#   1. No borra reglas del usuario: nada de `ufw reset`. Las reglas existentes
#      se conservan y la línea base previa queda respaldada para el rollback.
#   2. Abre el puerto REAL de sshd (sshd -T / socket en escucha), no el 22 de
#      /etc/services: con SSH en otro puerto, `ufw limit ssh` dejaba afuera.
#   3. Orden sin ventana de corte: primero las reglas SSH, después la política
#      por defecto, al final la activación.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
export LC_ALL=C

MOD="enable_firewall"
# Archivos que UFW reescribe con los comandos de este módulo.
UFW_FILES=(/etc/default/ufw /etc/ufw/ufw.conf /etc/ufw/user.rules /etc/ufw/user6.rules)

if ! command -v ufw &>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] UFW no está instalado: la ejecución real fallaría (apt install ufw)."
        exit 0
    fi
    check_cmd ufw
fi

ssh_ports() {
    # Puertos TCP donde se aceptan conexiones SSH, uno por línea.
    if command -v sshd &>/dev/null && [ -d /run/sshd ]; then
        sshd -T 2>/dev/null | awk '$1 == "port" { print $2 }'
    fi
    if command -v ss &>/dev/null; then
        # sshd escuchando por sí mismo, o systemd por él (activación por socket)
        ss -Htlnp 2>/dev/null \
            | awk '/"sshd"|"sshd-session"/ { n = split($4, a, ":"); print a[n] }'
    fi
    if command -v systemctl &>/dev/null \
        && systemctl is-active --quiet ssh.socket 2>/dev/null; then
        systemctl show -p Listen --value ssh.socket 2>/dev/null \
            | grep -oE ':[0-9]+ ' | tr -d ': '
    fi
}

mapfile -t PORTS < <(ssh_ports | grep -E '^[0-9]+$' | sort -un)
if [ "${#PORTS[@]}" -eq 0 ] && command -v sshd &>/dev/null; then
    warn "sshd instalado pero su puerto no se pudo determinar: se asume 22/tcp."
    PORTS=(22)
fi

baseline_begin "$MOD" "${UFW_FILES[@]}"

if [ "${#PORTS[@]}" -eq 0 ]; then
    info "Sin servidor SSH: no se abre ningún puerto entrante."
fi
for port in "${PORTS[@]}"; do
    apply "Permitir SSH con rate-limit en ${port}/tcp" \
        ufw limit "${port}/tcp" comment "Lockd: SSH rate-limit"
done
apply "Política por defecto: denegar entrante" ufw default deny incoming
apply "Política por defecto: permitir saliente" ufw default allow outgoing
apply "Activar UFW (las reglas existentes se conservan)" ufw --force enable

[ "$DRY_RUN" = "1" ] || ufw status verbose
