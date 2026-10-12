#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
FSTAB="${SYSROOT}/etc/fstab"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Crearía el grupo procview si no existe y sumaría polkitd"
    warn "[DRY-RUN] Guardaría las opciones actuales de /proc"
    warn "[DRY-RUN] Dejaría en /etc/fstab la entrada lockd-hide-procs (hidepid=invisible,gid=procview)"
    warn "[DRY-RUN] mount -o remount,hidepid=invisible,gid=<procview> /proc"
    exit 0
fi
backup "$FSTAB" hide_procs_nonroot
ciclo_previo=0
if grupos_registrados hide_procs_nonroot; then ciclo_previo=1; fi
grupo_asegurar hide_procs_nonroot procview
GID=$(getent group procview | cut -d: -f3)
for u in polkitd systemd-journal; do
    grupo_sumar hide_procs_nonroot procview "$u"
done
if ! endurecer_montaje hide_procs_nonroot lockd-hide-procs proc /proc proc "hidepid=invisible,gid=${GID}"; then
    # deshacer también el grupo, si lo armó esta ejecución
    if [ "$ciclo_previo" = 0 ]; then grupo_revertir hide_procs_nonroot; fi
    exit 1
fi
info "hidepid activado: el grupo procview ve todos los procesos."
