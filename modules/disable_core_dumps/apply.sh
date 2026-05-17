#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
LIMITS="/etc/security/limits.d/lockd-coredumps.conf"
SYSCTL_CONF="/etc/sysctl.d/99-lockd-coredumps.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Create $LIMITS and $SYSCTL_CONF"; exit 0
fi

[ -z "$SYSCTL" ] && { error "sysctl no encontrado. Instalar: apt install procps"; exit 1; }

echo "* hard core 0" > "$LIMITS"
echo "* soft core 0" >> "$LIMITS"
cat > "$SYSCTL_CONF" << 'CONF'
kernel.core_pattern = |/bin/false
fs.suid_dumpable = 0
CONF
$SYSCTL -p "$SYSCTL_CONF" &>/dev/null
info "Core dumps deshabilitados."
