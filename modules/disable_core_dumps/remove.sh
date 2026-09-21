#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove core dump configs"; exit 0
fi
rm -f /etc/security/limits.d/lockd-coredumps.conf
rm -f /etc/sysctl.d/99-lockd-coredumps.conf
$SYSCTL -w kernel.core_pattern="core" &>/dev/null || true
info "Core dumps restaurados."
