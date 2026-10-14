#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Quitaría de /etc/fstab solo la entrada lockd-hide-procs (y reactivaría la previa si la había)"
    warn "[DRY-RUN] Devolvería hidepid y gid de /proc a sus valores previos"
    warn "[DRY-RUN] Quitaría de procview los miembros que agregó Lockd y el grupo si lo creó y quedó vacío"
    exit 0
fi
revertir_montaje hide_procs_nonroot lockd-hide-procs /proc hidepid gid
grupo_revertir hide_procs_nonroot
info "hidepid desactivado."
