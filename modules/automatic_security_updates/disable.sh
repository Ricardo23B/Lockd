#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
AUTO_CONF="${SYSROOT}/etc/apt/apt.conf.d/20auto-upgrades"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove auto-upgrades config"; exit 0
fi
cat > "$AUTO_CONF" << 'CONF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
CONF
info "Actualizaciones automáticas desactivadas."
