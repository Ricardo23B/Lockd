#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
MOD="apparmor_enforce_mode"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Instalaría apparmor y apparmor-utils si faltan (quedan instalados al desactivar)"
    warn "[DRY-RUN] Guardaría el estado del servicio apparmor y lo dejaría habilitado y activo"
    mapfile -t perfiles < <(apparmor_en_complain)
    if [ "${#perfiles[@]}" -eq 0 ]; then
        warn "[DRY-RUN] Ningún perfil está en complain: no habría perfiles para pasar a enforce"
    fi
    for p in "${perfiles[@]}"; do
        warn "[DRY-RUN] Guardaría $p y lo pasaría a enforce"
    done
    exit 0
fi
# Si algo falla antes de tocar los perfiles, el servicio y lo guardado quedan
# como estaban (los paquetes instalados quedan instalados).
estado_nuevo=1
if servicio_guardado "$MOD" apparmor; then estado_nuevo=0; fi
# El estado se guarda antes de instalar: el paquete arranca el servicio al
# instalarse, y lo que cuenta es cómo estaba antes de Lockd.
servicio_guardar "$MOD" apparmor
if ! paquete_instalar "$MOD" apparmor apparmor-utils; then
    if [ "$estado_nuevo" = 1 ]; then servicio_olvidar "$MOD" apparmor; fi
    error "No se pudo instalar AppArmor."
    exit 1
fi
if ! aa-enabled --quiet 2>/dev/null; then
    if [ "$estado_nuevo" = 1 ]; then servicio_restaurar "$MOD" apparmor; fi
    error "AppArmor no está habilitado en el kernel: no se cambió ningún perfil."
    exit 1
fi
if ! systemctl enable --now apparmor; then
    if [ "$estado_nuevo" = 1 ]; then servicio_restaurar "$MOD" apparmor; fi
    error "No se pudo habilitar el servicio apparmor: no se cambió ningún perfil."
    exit 1
fi

# Solo los perfiles en complain: los deshabilitados y los unconfined quedan
# como están. Cada perfil se guarda antes de aa-enforce, que reescribe sus
# cabeceras y borra sus enlaces en force-complain/ y disable/. Si aa-enforce
# falla con uno, ese perfil vuelve a como estaba y el resto sigue.
mapfile -t perfiles < <(apparmor_en_complain)
fallidos=()
for p in "${perfiles[@]}"; do
    apparmor_guardar "$MOD" "$p"
    if aa-enforce "$p"; then
        apparmor_anotar "$MOD" "$p"
    else
        apparmor_devolver "$MOD" "$p"
        fallidos+=("$(basename "$p")")
    fi
done
if [ "${#fallidos[@]}" -gt 0 ]; then
    error "Quedaron como estaban porque aa-enforce falló: ${fallidos[*]}. Los demás pasaron a enforce y disable los devuelve."
    exit 1
fi
if [ "${#perfiles[@]}" -eq 0 ]; then
    info "AppArmor activo. Ningún perfil estaba en complain."
else
    info "AppArmor activo: ${#perfiles[@]} perfiles pasaron de complain a enforce."
fi
