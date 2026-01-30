#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
CONF="/etc/fail2ban/jail.d/lockd-ssh.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] remove $CONF"; warn "[DRY-RUN] systemctl stop fail2ban"; exit 0
fi
rm -f "$CONF"
systemctl stop fail2ban 2>/dev/null || true
systemctl disable fail2ban 2>/dev/null || true
info "Fail2ban desactivado."
