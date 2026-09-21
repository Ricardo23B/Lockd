#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root

DROP_IN="/etc/ssh/sshd_config.d/99-lockd-hardening.conf"
BACKUP_DIR="${BACKUP_BASE}/hardened_ssh_config"

# DRY-RUN antes de cualquier check de dependencias
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would check for authorized_keys in user homes"
    warn "[DRY-RUN] Would create: $DROP_IN"
    warn "[DRY-RUN] Would run: sshd -t && systemctl reload sshd"
    exit 0
fi

check_cmd sshd

# Seguridad crítica: verificar que haya authorized_keys antes de deshabilitar contraseña
AUTH_KEYS=0
while IFS= read -r -d "" home; do
    [ -f "${home}/.ssh/authorized_keys" ] && AUTH_KEYS=1 && break
done < <(awk -F: '$3>=1000&&$3<65534{printf "%s\0",$6}' /etc/passwd)

if [ "$AUTH_KEYS" -eq 0 ]; then
    error "No se encontró ningún authorized_keys en homes de usuarios."
    error "Configura tu clave SSH antes de deshabilitar la autenticación por contraseña."
    error "Comando: ssh-copy-id usuario@servidor"
    exit 1
fi

mkdir -p "$(dirname "$DROP_IN")" "$BACKUP_DIR"
cp /etc/ssh/sshd_config "$BACKUP_DIR/sshd_config.bak" 2>/dev/null || true

cat > "$DROP_IN" << 'CONF'
# Lockd — SSH hardening drop-in
PasswordAuthentication no
PermitRootLogin no
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowAgentForwarding no
PermitEmptyPasswords no
ClientAliveInterval 300
ClientAliveCountMax 2
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org
Ciphers aes256-gcm@openssh.com,chacha20-poly1305@openssh.com
MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com
CONF

if sshd -t 2>/tmp/sshd_err; then
    systemctl reload sshd
    info "SSH endurecido y recargado correctamente."
else
    error "Configuración SSH inválida. Revirtiendo."
    rm -f "$DROP_IN"
    cat /tmp/sshd_err >&2
    exit 1
fi
