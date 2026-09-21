#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
BL="/etc/modprobe.d/lockd-module-blacklist.conf"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Remove $BL"; warn "[DRY-RUN] update-initramfs -u"; exit 0
fi
rm -f "$BL"
command -v update-initramfs &>/dev/null && update-initramfs -u
warn "Reinicia para cargar los módulos."
info "Lista negra de módulos eliminada."
