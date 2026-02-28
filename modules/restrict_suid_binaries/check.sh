#!/bin/bash
SUID_LIST="${BACKUP_BASE:-/var/lib/lockd/backups}/restrict_suid_binaries/suid_removed.txt"
[ -f "$SUID_LIST" ] && [ -s "$SUID_LIST" ] && exit 0 || exit 1
