#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="apparmor_enforce_mode"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Devolvería a complain los perfiles que pasó a enforce, con sus archivos y enlaces como estaban"
    warn "[DRY-RUN] Devolvería el servicio apparmor a su estado previo (habilitado/activo)"
    exit 0
fi
if apparmor_guardados "$MOD"; then
    apparmor_restaurar "$MOD"
elif servicio_guardado "$MOD" apparmor; then
    info "Este ciclo no pasó ningún perfil a enforce: los perfiles quedan como están."
else
    # Activado con una versión anterior de Lockd: no hay nada guardado y no se
    # adivina el modo previo de cada perfil.
    warn "No hay estado guardado de los perfiles: quedan como están (revisalos con sudo aa-status)."
fi
servicio_restaurar "$MOD" apparmor
paquetes_avisar "$MOD"
info "AppArmor en su estado previo."
