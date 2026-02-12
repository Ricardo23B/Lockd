#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
FSTAB_MARKER="# lockd-hide-procs"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] groupadd procview"
    warn "[DRY-RUN] Add hidepid=invisible to /proc in /etc/fstab"
    warn "[DRY-RUN] mount -o remount,hidepid=invisible /proc"
    exit 0
fi
backup /etc/fstab hide_procs_nonroot
getent group procview &>/dev/null || groupadd procview
GID=$(getent group procview | cut -d: -f3)
for u in polkitd systemd-journal; do
    id "$u" &>/dev/null && usermod -aG procview "$u" 2>/dev/null || true
done
sed -i "/$FSTAB_MARKER/d" /etc/fstab
echo "proc /proc proc defaults,hidepid=invisible,gid=${GID} 0 0 $FSTAB_MARKER" >> /etc/fstab
mount -o remount,hidepid=invisible,gid="$GID" /proc
info "hidepid activado. Grupo 'procview' creado."
