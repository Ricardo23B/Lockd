#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] apt install -y unattended-upgrades"
    warn "[DRY-RUN] Configure /etc/apt/apt.conf.d/20auto-upgrades"
    exit 0
fi
apt-get install -y unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
systemctl enable --now unattended-upgrades 2>/dev/null || true
info "Actualizaciones automáticas configuradas."
