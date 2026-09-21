#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] systemctl mask ctrl-alt-del.target"; exit 0
fi
systemctl mask ctrl-alt-del.target
systemctl daemon-reload
info "Ctrl+Alt+Del deshabilitado."
