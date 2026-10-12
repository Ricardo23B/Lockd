#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
FSTAB_MARKER="# lockd-shm"
FSTAB="${SYSROOT}/etc/fstab"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Add noexec,nosuid to /dev/shm in /etc/fstab"
    warn "[DRY-RUN] mount -o remount,noexec,nosuid /dev/shm"
    exit 0
fi
backup "$FSTAB" secure_shared_memory
sed -i "/$FSTAB_MARKER/d" "$FSTAB"
echo "tmpfs /dev/shm tmpfs defaults,noexec,nosuid,nodev 0 0 $FSTAB_MARKER" >> "$FSTAB"
mount -o remount,noexec,nosuid,nodev /dev/shm 2>/dev/null || warn "Remontaje diferido al reinicio."
info "/dev/shm asegurado."
