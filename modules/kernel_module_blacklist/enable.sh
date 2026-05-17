#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BL="/etc/modprobe.d/lockd-module-blacklist.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Create $BL with filesystem and network module blacklist"
    warn "[DRY-RUN] update-initramfs -u (requiere reinicio)"; exit 0
fi
cat > "$BL" << 'CONF'
# Lockd — Kernel module blacklist
# Filesystems
install cramfs  /bin/false
install freevxfs /bin/false
install jffs2   /bin/false
install hfs     /bin/false
install hfsplus /bin/false
install udf     /bin/false
blacklist cramfs
blacklist freevxfs
blacklist jffs2
blacklist hfs
blacklist hfsplus
blacklist udf
# Network protocols
install dccp /bin/false
install sctp /bin/false
install rds  /bin/false
install tipc /bin/false
blacklist dccp
blacklist sctp
blacklist rds
blacklist tipc
CONF
command -v update-initramfs &>/dev/null && update-initramfs -u
warn "REINICIO REQUERIDO para que la lista negra surta efecto completo."
info "Lista negra de módulos del kernel aplicada."
