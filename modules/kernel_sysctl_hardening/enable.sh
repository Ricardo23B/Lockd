#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
CONF="/etc/sysctl.d/99-lockd-hardening.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Create $CONF"; warn "[DRY-RUN] $SYSCTL -p $CONF"; exit 0
fi

# Verificar que sysctl está disponible
[ -z "$SYSCTL" ] && { error "sysctl no encontrado. Instalar: apt install procps"; exit 1; }

cat > "$CONF" << 'CONF'
# Lockd — Kernel sysctl hardening
# Red
net.ipv4.ip_forward = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_source_route = 0
# Kernel
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.yama.ptrace_scope = 1
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
CONF
$SYSCTL -p "$CONF"
info "Parámetros de kernel aplicados."
