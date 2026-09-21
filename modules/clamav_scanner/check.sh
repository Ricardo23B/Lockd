#!/usr/bin/env bash
# clamav_scanner/check.sh — verifica si ClamAV y el timer están activos
set -euo pipefail

CLAMAV_OK=0
TIMER_OK=0

command -v clamscan &>/dev/null && CLAMAV_OK=1
systemctl is-active --quiet lockd-clamav.timer 2>/dev/null && TIMER_OK=1

if [ "$CLAMAV_OK" -eq 1 ] && [ "$TIMER_OK" -eq 1 ]; then
    echo "enabled"
    exit 0
else
    echo "disabled"
    exit 1
fi