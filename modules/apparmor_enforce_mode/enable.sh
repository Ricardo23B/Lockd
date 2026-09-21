#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would: apt install -y apparmor apparmor-utils apparmor-profiles"
    warn "[DRY-RUN] Would: systemctl enable --now apparmor"
    warn "[DRY-RUN] Would: aa-enforce /etc/apparmor.d/*"
    exit 0
fi

apt-get install -y apparmor apparmor-utils apparmor-profiles 2>/dev/null || true
systemctl enable --now apparmor

if command -v aa-enforce &>/dev/null; then
    find /etc/apparmor.d -maxdepth 1 -type f -exec aa-enforce {} \; 2>/dev/null || true
    info "Perfiles AppArmor en modo enforce."
else
    warn "aa-enforce no disponible. Instalar apparmor-utils."
fi
info "AppArmor activado."
