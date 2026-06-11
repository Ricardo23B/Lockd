#!/bin/bash
# restrict_suid_binaries/enable.sh
#
# DISEÑO (invertido respecto a la versión original):
#   - Se quita el bit SUID SOLO a binarios de una DENYLIST explícita de
#     riesgo conocido y bajo impacto. Lo que no entendemos, NO se toca:
#     se audita y reporta. Una herramienta que no reconoce un binario no
#     debe modificarlo.
#   - NEVER_TOUCH es una red de seguridad inmutable: binarios de los que
#     depende la autenticación y el funcionamiento básico del sistema
#     (polkit, sudo, dbus, PAM, mount). Aunque alguien edite la denylist,
#     estos jamás se tocan. La versión anterior de este módulo podía
#     quitarle el SUID a polkit-agent-helper-1 y romper la autenticación
#     de polkit — dejando a Lockd sin poder deshacerse a sí mismo.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

BACKUP_DIR="${BACKUP_BASE}/restrict_suid_binaries"
SUID_LIST="$BACKUP_DIR/suid_removed.txt"
AUDIT_LIST="$BACKUP_DIR/suid_audit.txt"

# Rutas a escanear (override solo para tests; el helper pasa entorno mínimo)
SEARCH_PATHS="${LOCKD_SUID_SEARCH_PATHS:-/usr /bin /sbin}"

# DENYLIST: binarios SUID de riesgo conocido cuya pérdida de SUID tiene
# impacto acotado y documentado (los usuarios no-root pierden esa función;
# root no se ve afectado):
#   chfn chsh        — cambiar GECOS/shell propio (historial de CVEs en util-linux)
#   newgrp sg        — cambio de grupo en sesión, raramente usado
#   mount.cifs       — montajes CIFS por usuario (fuente recurrente de CVEs)
#   mount.nfs        — montajes NFS por usuario
#   mount.ecryptfs_private — eCryptfs por usuario
#   ntfs-3g          — montajes NTFS por usuario (CVE-2022-30783 y relacionados)
#   pppd             — PPP iniciado por usuario (CVE-2020-8597)
#   clockdiff traceroute6.iputils — utilidades iputils legacy
DENYLIST="${LOCKD_SUID_DENYLIST:-chfn chsh newgrp sg mount.cifs mount.nfs mount.ecryptfs_private ntfs-3g pppd clockdiff traceroute6.iputils}"

# NEVER_TOUCH: inmutable, sin override posible. Autenticación e
# infraestructura: tocarlos puede dejar el sistema sin forma de autenticar
# o de revertir este mismo módulo.
NEVER_TOUCH="sudo su passwd pkexec polkit-agent-helper-1 dbus-daemon-launch-helper unix_chkpwd mount umount fusermount fusermount3 ssh-keysign newuidmap newgidmap ping ping6 ssh-agent gpasswd"

in_list() {  # in_list <name> <lista separada por espacios>
    local name="$1" list="$2" item
    for item in $list; do
        [ "$item" = "$name" ] && return 0
    done
    return 1
}

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Escanearía SUID en: $SEARCH_PATHS"
    warn "[DRY-RUN] Quitaría SUID SOLO a (si existen): $DENYLIST"
    warn "[DRY-RUN] El resto se auditaría en $AUDIT_LIST sin modificarse"
    warn "[DRY-RUN] Nunca se tocan: $NEVER_TOUCH"
    exit 0
fi

mkdir -p "$BACKUP_DIR"
: > "$SUID_LIST"
: > "$AUDIT_LIST"

removed=0
audited=0
# shellcheck disable=SC2086  # SEARCH_PATHS debe expandirse en palabras
while IFS= read -r -d "" bin; do
    name=$(basename "$bin")
    if in_list "$name" "$NEVER_TOUCH"; then
        continue
    fi
    if in_list "$name" "$DENYLIST"; then
        info "Removiendo SUID: $bin"
        echo "$bin" >> "$SUID_LIST"
        chmod u-s "$bin"
        removed=$((removed + 1))
        if [ -n "${LOCKD_MANIFEST:-}" ]; then
            printf '%s|restrict_suid_binaries|suid:%s|%s\n' \
                "${LOCKD_OP_ID:-manual}" "$bin" "$SUID_LIST" \
                >> "$LOCKD_MANIFEST" 2>/dev/null || true
        fi
    else
        echo "$bin" >> "$AUDIT_LIST"
        audited=$((audited + 1))
    fi
done < <(find $SEARCH_PATHS -perm -4000 -type f -print0 2>/dev/null)

info "SUID removido de $removed binarios de la denylist (lista: $SUID_LIST)."
info "$audited binarios SUID adicionales detectados y auditados SIN modificar."
info "Revisión manual recomendada: $AUDIT_LIST"
