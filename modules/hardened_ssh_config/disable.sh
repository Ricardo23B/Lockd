#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
DROP_IN="/etc/ssh/sshd_config.d/99-lockd-hardening.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove $DROP_IN"; warn "[DRY-RUN] systemctl reload sshd"; exit 0
fi
rm -f "$DROP_IN"
sshd -t && systemctl reload sshd && info "SSH revertido." || { error "Config inválida"; exit 1; }
