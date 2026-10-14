#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Quitaría de /etc/fstab solo la entrada lockd-shm (y reactivaría la previa si la había)"
    warn "[DRY-RUN] Devolvería noexec,nosuid,nodev de /dev/shm a sus valores previos"
    exit 0
fi
revertir_montaje secure_shared_memory lockd-shm /dev/shm noexec nosuid nodev
info "/dev/shm restaurado."
