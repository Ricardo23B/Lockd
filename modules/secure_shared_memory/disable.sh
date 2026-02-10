#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove lockd-shm from /etc/fstab"; exit 0
fi
restore /etc/fstab secure_shared_memory
mount -o remount /dev/shm 2>/dev/null || true
info "/dev/shm restaurado."
