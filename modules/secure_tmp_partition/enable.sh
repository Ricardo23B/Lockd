#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
DROP_IN="/etc/systemd/system/tmp.mount.d/lockd-secure.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Create $DROP_IN"
    warn "[DRY-RUN] systemctl daemon-reload"
    warn "[DRY-RUN] mount -o remount,nosuid,nodev,noexec /tmp"
    exit 0
fi
mkdir -p "$(dirname "$DROP_IN")"
backup /etc/fstab secure_tmp_partition
cat > "$DROP_IN" << 'CONF'
[Mount]
Options=mode=1777,strictatime,nosuid,nodev,noexec
CONF
systemctl daemon-reload
if findmnt -n /tmp &>/dev/null; then
    mount -o remount,nosuid,nodev,noexec /tmp && info "/tmp remontado con noexec."
else
    warn "/tmp no es un punto de montaje separado. Cambios al reiniciar."
fi
