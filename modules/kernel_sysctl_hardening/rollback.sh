#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
CONF="/etc/sysctl.d/99-lockd-hardening.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove $CONF"; exit 0
fi

[ -z "$SYSCTL" ] && { error "sysctl no encontrado. Instalar: apt install procps"; exit 1; }

rm -f "$CONF"
$SYSCTL --system &>/dev/null
info "Parámetros de kernel revertidos."
