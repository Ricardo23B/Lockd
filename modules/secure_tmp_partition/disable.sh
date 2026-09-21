#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
DROP_IN="/etc/systemd/system/tmp.mount.d/lockd-secure.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove $DROP_IN"; warn "[DRY-RUN] mount -o remount /tmp"; exit 0
fi
rm -f "$DROP_IN"
rmdir --ignore-fail-on-non-empty "$(dirname "$DROP_IN")" 2>/dev/null || true
systemctl daemon-reload
findmnt -n /tmp &>/dev/null && mount -o remount /tmp || true
info "/tmp restaurado."
