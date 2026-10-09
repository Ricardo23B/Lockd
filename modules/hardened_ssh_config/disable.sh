#!/bin/bash
# hardened_ssh_config (disable) — retira el drop-in (y el de versiones
# anteriores), valida la configuración restante y recarga sshd.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
export LC_ALL=C

DROP_DIR="/etc/ssh/sshd_config.d"
for f in "${DROP_DIR}/00-lockd-hardening.conf" "${DROP_DIR}/99-lockd-hardening.conf"; do
    if [ -e "$f" ]; then
        apply "Eliminar $f" rm -f "$f"
    fi
done

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would validate (sshd -t) y recargar sshd"
    exit 0
fi
if ! command -v sshd &>/dev/null; then
    info "OpenSSH server no instalado: nada que recargar."
    exit 0
fi

[ -d /run/sshd ] || install -d -m 0755 /run/sshd
ERR="$(mktemp)"
trap 'rm -f "$ERR"' EXIT
if ! sshd -t 2>"$ERR"; then
    error "La configuración restante de sshd es inválida (ajena a Lockd); no se recarga:"
    cat "$ERR" >&2
    exit 1
fi
reload_sshd
info "SSH revertido."
