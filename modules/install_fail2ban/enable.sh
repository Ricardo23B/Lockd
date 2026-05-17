#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

CONF="/etc/fail2ban/jail.d/lockd-ssh.conf"

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would: apt install -y fail2ban"
    warn "[DRY-RUN] Would create: $CONF"
    warn "[DRY-RUN] Would: systemctl enable --now fail2ban"
    exit 0
fi

if ! command -v fail2ban-client &>/dev/null; then
    apt-get install -y fail2ban
fi

mkdir -p "$(dirname "$CONF")"
cat > "$CONF" << 'CONF'
[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 5
bantime  = 3600
findtime = 600
CONF

systemctl enable --now fail2ban
info "Fail2ban instalado y configurado."
