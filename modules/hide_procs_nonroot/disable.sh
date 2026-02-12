#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Restore /etc/fstab"; warn "[DRY-RUN] mount -o remount,hidepid=0 /proc"; exit 0
fi
restore /etc/fstab hide_procs_nonroot
mount -o remount,hidepid=0 /proc
info "hidepid desactivado."
