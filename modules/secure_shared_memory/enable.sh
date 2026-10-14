#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
FSTAB="${SYSROOT}/etc/fstab"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Guardaría las opciones actuales de /dev/shm"
    warn "[DRY-RUN] Dejaría en /etc/fstab la entrada lockd-shm para /dev/shm (noexec,nosuid,nodev)"
    warn "[DRY-RUN] mount -o remount,noexec,nosuid,nodev /dev/shm"
    exit 0
fi
backup "$FSTAB" secure_shared_memory
endurecer_montaje secure_shared_memory lockd-shm tmpfs /dev/shm tmpfs noexec,nosuid,nodev || exit 1
info "/dev/shm asegurado (noexec,nosuid,nodev)."
