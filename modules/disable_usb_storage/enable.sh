#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BL="/etc/modprobe.d/lockd-usb-storage.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Create $BL"; warn "[DRY-RUN] update-initramfs -u"; exit 0
fi
cat > "$BL" << 'CONF'
# Lockd — USB storage blacklist
blacklist usb-storage
blacklist uas
install usb-storage /bin/false
install uas /bin/false
CONF
command -v update-initramfs &>/dev/null && update-initramfs -u
lsmod | grep -q "usb_storage" && modprobe -r usb-storage 2>/dev/null || true
info "Almacenamiento USB bloqueado."
