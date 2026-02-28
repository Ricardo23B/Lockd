#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BACKUP_DIR="${BACKUP_BASE}/restrict_suid_binaries"
SAFE_SUID="sudo su mount umount passwd newgrp chfn chsh gpasswd pkexec ping ping6 ssh-agent"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] find / -perm -4000 -type f"
    warn "[DRY-RUN] chmod u-s on non-essential SUID binaries"
    exit 0
fi
mkdir -p "$BACKUP_DIR"
SUID_LIST="$BACKUP_DIR/suid_removed.txt"
> "$SUID_LIST"
while IFS= read -r -d "" bin; do
    name=$(basename "$bin")
    if echo "$SAFE_SUID" | grep -qw "$name"; then
        continue
    fi
    info "Removiendo SUID: $bin"
    echo "$bin" >> "$SUID_LIST"
    chmod u-s "$bin"
done < <(find /usr /bin /sbin -perm -4000 -type f -print0 2>/dev/null)
REMOVED=$(wc -l < "$SUID_LIST")
info "SUID removido de $REMOVED binarios no esenciales."
info "Lista guardada en: $SUID_LIST"
