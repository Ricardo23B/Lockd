#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
DROP_IN="${SYSROOT}/etc/systemd/system/tmp.mount.d/lockd-secure.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Borraría $DROP_IN"
    warn "[DRY-RUN] systemctl daemon-reload"
    warn "[DRY-RUN] Devolvería nosuid,nodev,noexec de /tmp a sus valores previos"
    exit 0
fi
rm -f "$DROP_IN"
rmdir --ignore-fail-on-non-empty "$(dirname "$DROP_IN")" 2>/dev/null || true
systemctl daemon-reload
if findmnt -n /tmp &>/dev/null; then
    montaje_restaurar secure_tmp_partition /tmp noexec nosuid nodev
fi
info "/tmp restaurado."
