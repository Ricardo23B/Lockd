#!/bin/bash
# hardened_ssh_config — drop-in de endurecimiento para sshd.
#
# Precedencia: sshd se queda con el PRIMER valor de cada opción, y Debian/
# Ubuntu incluyen sshd_config.d/*.conf al principio de sshd_config, en orden
# léxico. Por eso el drop-in se llama 00-…: como 99-… lo anulaba en silencio
# cualquier otro drop-in (p. ej. 50-cloud-init.conf con
# PasswordAuthentication yes). Tras escribirlo se verifica el valor EFECTIVO
# con `sshd -T`; si no ganó la precedencia, se retira y se informa.
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
export LC_ALL=C

DROP_DIR="/etc/ssh/sshd_config.d"
DROP_IN="${DROP_DIR}/00-lockd-hardening.conf"
LEGACY_DROP_IN="${DROP_DIR}/99-lockd-hardening.conf"

if ! command -v sshd &>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] OpenSSH server no está instalado: la ejecución real fallaría."
        exit 0
    fi
    error "OpenSSH server no está instalado (openssh-server): no hay nada que endurecer."
    exit 1
fi

# sshd -t / -T exigen el directorio de privilege separation. Con activación
# por socket (Ubuntu >= 22.10) no existe hasta la primera conexión y la
# validación fallaba con un falso "configuración inválida". Es un directorio
# de runtime que el propio ssh.service crea; no es configuración persistente.
if [ ! -d /run/sshd ]; then
    apply "Crear /run/sshd (requerido por sshd -t)" install -d -m 0755 /run/sshd
fi

sshd_eff() {
    # sshd_eff <usuario> <opción>: valor efectivo de la opción para ese usuario
    sshd -T -C "user=$1,host=localhost,addr=127.0.0.1" 2>/dev/null \
        | awk -v k="$2" '$1 == k { $1 = ""; sub(/^ /, ""); print; exit }'
}

# ── Guardas anti-lockout ─────────────────────────────────────────────────────
# Con PermitRootLogin no + PasswordAuthentication no solo entra por SSH un
# usuario NO root con una clave que sshd acepte de verdad: archivo listado en
# su AuthorizedKeysFile, con >= 1 clave válida y permisos que StrictModes no
# rechace. (Antes alcanzaba con que CUALQUIER usuario tuviera un
# authorized_keys en ~/.ssh, aunque no fuera quien estaba conectado.)

keyfile_perms_ok() {
    # StrictModes: el archivo y cada directorio hasta el home deben pertenecer
    # al usuario o a root y no ser escribibles por grupo ni otros.
    local path="$1" uid="$2" home="$3" owner mode
    while :; do
        read -r owner mode < <(stat -c '%u %a' "$path" 2>/dev/null) || return 1
        [ "$owner" = "$uid" ] || [ "$owner" = "0" ] || return 1
        (( (8#$mode & 8#022) == 0 )) || return 1
        if [ "$path" = "$home" ] || [ "$path" = "/" ]; then
            return 0
        fi
        path="$(dirname "$path")"
    done
}

user_has_usable_key() {
    local user="$1" uid home akc strict f
    local -a akf
    uid="$(id -u "$user" 2>/dev/null)" || return 1
    home="$(getent passwd "$user" | cut -d: -f6)"
    if [ -z "$home" ] || [ ! -d "$home" ]; then
        return 1
    fi
    akc="$(sshd_eff "$user" authorizedkeyscommand)"
    if [ -n "$akc" ] && [ "$akc" != "none" ]; then
        warn "$user: claves vía AuthorizedKeysCommand ($akc); Lockd no puede verificarlas."
        return 0
    fi
    strict="$(sshd_eff "$user" strictmodes)"
    read -ra akf <<< "$(sshd_eff "$user" authorizedkeysfile)"
    [ "${#akf[@]}" -gt 0 ] || akf=(.ssh/authorized_keys .ssh/authorized_keys2)
    for f in "${akf[@]}"; do
        f="${f//%%/$'\x01'}"; f="${f//%h/$home}"; f="${f//%u/$user}"
        f="${f//%U/$uid}";    f="${f//$'\x01'/%}"
        [[ "$f" = /* ]] || f="${home}/${f}"
        [ -f "$f" ] || continue
        if [ "$strict" != "no" ] && ! keyfile_perms_ok "$f" "$uid" "$home"; then
            warn "$user: $f existe pero StrictModes lo rechaza (dueño o permisos)."
            continue
        fi
        ssh-keygen -l -f "$f" &>/dev/null && return 0
    done
    return 1
}

has_ssh_session() {
    # ¿Tiene <usuario> una sesión SSH abierta ahora? (proceso "sshd: user@…")
    ps -eo args= 2>/dev/null | awk -v u="$1" '
        index($0, "sshd: " u "@") == 1 || index($0, "sshd-session: " u "@") == 1 ||
        $0 == "sshd: " u " [priv]"     || $0 == "sshd-session: " u " [priv]" { f = 1 }
        END { exit !f }'
}

admin_users() {
    getent group sudo admin wheel 2>/dev/null | cut -d: -f4 | tr ',' '\n' \
        | grep -vx -e '' -e root | sort -u
}

any_admin_with_key() {
    local u
    while IFS= read -r u; do
        if user_has_usable_key "$u"; then
            printf '%s\n' "$u"
            return 0
        fi
    done < <(admin_users)
    return 1
}

resolve_caller() {
    # Quién pidió la operación: helper (LOCKD_CALLER_UID), pkexec directo
    # (PKEXEC_UID, modo legacy) o sudo (SUDO_UID, ejecución manual).
    local uid="${LOCKD_CALLER_UID:-${PKEXEC_UID:-${SUDO_UID:-}}}"
    [[ "$uid" =~ ^[0-9]+$ ]] || return 0
    getent passwd "$uid" | cut -d: -f1
}

lockout_guard() {
    local caller who
    caller="$(resolve_caller)"
    if [ -n "$caller" ] && has_ssh_session "$caller"; then
        if [ "$caller" = "root" ]; then
            if who="$(any_admin_with_key)"; then
                warn "Estás conectado como root por SSH: después de esto entrá como '$who'."
                return 0
            fi
            error "Estás conectado como root por SSH y ningún administrador no-root tiene"
            error "una clave utilizable: PermitRootLogin no te dejaría afuera."
            error "Creá primero un usuario sudo con clave (ssh-copy-id) y probalo."
            return 1
        fi
        user_has_usable_key "$caller" && return 0
        error "Estás conectado por SSH como '$caller' sin una clave pública utilizable:"
        error "con PasswordAuthentication no perderías el acceso en la próxima conexión."
        error "Desde tu equipo: ssh-copy-id $caller@<servidor>, y probá entrar con la clave."
        return 1
    fi
    if [ -n "$caller" ]; then
        # Sesión local (consola o escritorio): este cambio no te corta ahora.
        if ! any_admin_with_key >/dev/null; then
            warn "Ningún administrador tiene clave SSH: desde ahora nadie entra por SSH con contraseña."
            warn "Si vas a necesitar acceso remoto, configurá una clave antes (ssh-copy-id)."
        fi
        return 0
    fi
    # Invocador desconocido: se exige al menos un administrador con clave.
    any_admin_with_key >/dev/null && return 0
    error "No se pudo determinar quién ejecuta Lockd y ningún administrador"
    error "(sudo/admin/wheel) tiene una clave SSH utilizable."
    return 1
}

if [ ! -d /run/sshd ]; then
    # Solo en dry-run (en ejecución real se creó arriba).
    warn "[DRY-RUN] sshd no está corriendo: las guardas anti-lockout se evalúan en la ejecución real."
elif ! lockout_guard; then
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] La ejecución real se rechazaría por el motivo anterior."
        exit 0
    fi
    exit 1
fi

# El nombre de la opción cambió en OpenSSH 8.7; el viejo sigue como alias.
KBD_KW="ChallengeResponseAuthentication"
if [ -d /run/sshd ] && sshd -T 2>/dev/null | grep -q '^kbdinteractiveauthentication '; then
    KBD_KW="KbdInteractiveAuthentication"
fi

write_file "$DROP_IN" 0644 << CONF
# Lockd — endurecimiento de sshd. Generado: se elimina al desactivar el módulo.
# Prefijo 00-: sshd usa el PRIMER valor que encuentra de cada opción.
PasswordAuthentication no
# Sin esto, con UsePAM yes la contraseña sigue entrando por keyboard-interactive.
${KBD_KW} no
PermitEmptyPasswords no
PermitRootLogin no
# 4 (CIS): con 3, un agente con varias claves agota los intentos antes de
# llegar a la correcta.
MaxAuthTries 4
LoginGraceTime 20
X11Forwarding no
AllowAgentForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
# KEX: se RESTAN del set por defecto los grupos DH clásicos y ECDH NIST, en
# lugar de fijar una lista cerrada: así se conservan los híbridos
# post-cuánticos (sntrup761x25519, mlkem768x25519) que trae cada versión.
KexAlgorithms -diffie-hellman-*,ecdh-sha2-*
Ciphers aes256-gcm@openssh.com,chacha20-poly1305@openssh.com
MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com
CONF

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would validate (sshd -t) y verificar valores efectivos (sshd -T)"
    if [ -f "$LEGACY_DROP_IN" ]; then
        warn "[DRY-RUN] Would remove: $LEGACY_DROP_IN"
    fi
    warn "[DRY-RUN] Would reload sshd"
    exit 0
fi

ERR="$(mktemp)"
trap 'rm -f "$ERR"' EXIT
if ! sshd -t 2>"$ERR"; then
    rm -f "$DROP_IN"
    error "sshd rechaza la configuración con el drop-in; se retira. Detalle:"
    cat "$ERR" >&2
    exit 1
fi

# Verificación del valor EFECTIVO: el drop-in pudo quedar anulado por una
# opción anterior al Include de sshd_config.
EFF="$(sshd -T 2>/dev/null)"
MISMATCH=()
expect() {
    grep -qx "$1 $2" <<< "$EFF" \
        || MISMATCH+=("$1 (efectivo: $(awk -v k="$1" '$1 == k { print $2 }' <<< "$EFF"))")
}
expect passwordauthentication no
expect permitrootlogin no
if grep -q '^kbdinteractiveauthentication ' <<< "$EFF"; then
    expect kbdinteractiveauthentication no
fi
if awk '$1 == "kexalgorithms" { print $2 }' <<< "$EFF" | tr ',' '\n' \
        | grep -qE '^(diffie-hellman-|ecdh-sha2-)'; then
    MISMATCH+=("kexalgorithms (siguen habilitados DH/ECDH clásicos)")
fi
if [ "${#MISMATCH[@]}" -gt 0 ]; then
    rm -f "$DROP_IN"
    error "El drop-in no gana la precedencia de sshd; se retira sin aplicar. Opciones pisadas:"
    for m in "${MISMATCH[@]}"; do error "  - $m"; done
    error "Buscalas en /etc/ssh/sshd_config ANTES de la línea Include, o en bloques Match."
    exit 1
fi

if [ -f "$LEGACY_DROP_IN" ]; then
    apply "Retirar el drop-in de versiones anteriores ($LEGACY_DROP_IN)" rm -f "$LEGACY_DROP_IN"
fi

reload_sshd
info "SSH endurecido."
warn "Antes de cerrar esta sesión, probá entrar desde OTRA terminal con tu clave."
