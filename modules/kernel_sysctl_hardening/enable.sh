#!/bin/bash
# kernel_sysctl_hardening — parámetros de kernel vía sysctl.d.
#
# Rollback real: antes de aplicar se guarda el valor EN EJECUCIÓN de cada
# clave (runtime.snapshot). Borrar el .conf y correr `sysctl --system` no
# alcanza: solo reaplica claves configuradas en otros archivos, y el resto
# quedaba con el valor de Lockd hasta reiniciar.
#
# ip_forward: no se fuerza a 0 si ya está en 1 o hay un runtime que lo
# necesita (Docker, Podman, libvirt, LXD/Incus, WireGuard, Kubernetes):
# aplicarlo con esos servicios corriendo les cortaba la red al instante.
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

SETTINGS=(
    # Red
    "net.ipv4.conf.all.accept_redirects=0"
    "net.ipv4.conf.default.accept_redirects=0"
    "net.ipv4.conf.all.secure_redirects=0"
    "net.ipv4.conf.all.send_redirects=0"
    "net.ipv4.conf.all.accept_source_route=0"
    "net.ipv4.conf.all.log_martians=1"
    "net.ipv4.conf.all.rp_filter=1"
    "net.ipv4.conf.default.rp_filter=1"
    "net.ipv4.tcp_syncookies=1"
    "net.ipv4.icmp_echo_ignore_broadcasts=1"
    "net.ipv4.icmp_ignore_bogus_error_responses=1"
    "net.ipv6.conf.all.accept_redirects=0"
    "net.ipv6.conf.all.accept_source_route=0"
    # Kernel
    "kernel.randomize_va_space=2"
    "kernel.dmesg_restrict=1"
    "kernel.kptr_restrict=2"
    "kernel.yama.ptrace_scope=1"
    "fs.protected_hardlinks=1"
    "fs.protected_symlinks=1"
)

forwarding_needed() {
    local bin
    [ "$("$SYSCTL" -n net.ipv4.ip_forward 2>/dev/null)" = "1" ] && return 0
    for bin in dockerd podman libvirtd lxd incusd wg kubelet containerd; do
        command -v "$bin" &>/dev/null && return 0
    done
    return 1
}
if forwarding_needed; then
    warn "IP forwarding en uso o requerido (contenedores/VMs/VPN): no se fuerza ip_forward=0."
else
    SETTINGS=("net.ipv4.ip_forward=0" "${SETTINGS[@]}")
fi

# Solo claves que este kernel expone (sin Yama o sin IPv6 no existen, y
# `sysctl -p` abortaba el módulo entero a mitad de camino).
APPLY=()
for s in "${SETTINGS[@]}"; do
    key="${s%%=*}"
    if [ -e "/proc/sys/${key//.//}" ]; then
        APPLY+=("$s")
    else
        warn "$key no existe en este kernel: se omite."
    fi
done

# Línea base: valores en ejecución ANTES de Lockd (una vez por ciclo).
if ! baseline_active "$MOD"; then
    if [ -f "$CONF" ]; then
        warn "Existe $CONF de una versión anterior sin línea base: el snapshot"
        warn "refleja los valores actuales, no los previos a Lockd."
    fi
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] Would snapshot ${#APPLY[@]} valores en ejecución → $SNAPSHOT"
    else
        mkdir -p "$(dirname "$SNAPSHOT")"
        for s in "${APPLY[@]}"; do
            key="${s%%=*}"
            printf '%s=%s\n' "$key" "$("$SYSCTL" -n "$key")"
        done > "${SNAPSHOT}.tmp"
        mv -f "${SNAPSHOT}.tmp" "$SNAPSHOT"
    fi
fi
baseline_begin "$MOD"

{
    echo "# Lockd — hardening de kernel (sysctl). Generado: se elimina al desactivar."
    for s in "${APPLY[@]}"; do
        printf '%s = %s\n' "${s%%=*}" "${s#*=}"
    done
} | write_file "$CONF" 0644

apply "Aplicar $CONF" "$SYSCTL" -q -p "$CONF"
[ "$DRY_RUN" = "1" ] || info "Parámetros de kernel aplicados."
