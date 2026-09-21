#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would: ufw --force reset"
    warn "[DRY-RUN] Would: ufw default deny incoming"
    warn "[DRY-RUN] Would: ufw default allow outgoing"
    warn "[DRY-RUN] Would: ufw limit ssh"
    warn "[DRY-RUN] Would: ufw --force enable"
    exit 0
fi

check_cmd ufw
info "Configurando UFW..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw limit ssh comment "SSH rate-limit Lockd"
ufw --force enable
info "Cortafuegos activado."
ufw status verbose
