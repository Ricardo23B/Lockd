#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
check_cmd ufw
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] ufw --force disable"; exit 0
fi
ufw --force disable
info "Cortafuegos desactivado."
