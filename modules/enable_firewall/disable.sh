#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] ufw --force disable"; exit 0
fi
check_cmd ufw
ufw --force disable
info "Cortafuegos desactivado."
