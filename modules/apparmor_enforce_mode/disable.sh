#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] aa-complain all profiles"; exit 0
fi
command -v aa-complain &>/dev/null &&     find /etc/apparmor.d -maxdepth 1 -type f -exec aa-complain {} \; 2>/dev/null || true
info "Perfiles AppArmor en modo complain (no enforce)."
