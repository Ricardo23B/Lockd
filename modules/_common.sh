# shellcheck shell=bash
# _common.sh — funciones comunes para todos los scripts de Lockd
# Source: source "$(dirname "$0")/../_common.sh"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
# DRY_RUN se acepta por dos canales:
#   1. Argumento --dry-run (canal PRINCIPAL — pkexec ejecuta los scripts en un
#      entorno saneado y descarta las variables del invocante, así que el
#      executor pasa el flag como argumento, que sí sobrevive).
#   2. Variable de entorno DRY_RUN=1 (fallback para ejecución manual:
#      sudo DRY_RUN=1 bash enable.sh).
DRY_RUN="${DRY_RUN:-0}"
for __lockd_arg in "$@"; do
    [ "$__lockd_arg" = "--dry-run" ] && DRY_RUN=1
done
unset __lockd_arg
BACKUP_BASE="${LOCKD_BACKUP_BASE:-/var/lib/lockd/backups}"

check_root() { [ "$EUID" -eq 0 ] || { error "Requiere root."; exit 1; }; }
check_cmd()  { command -v "$1" &>/dev/null || { error "Falta: $1 (apt install $1)"; exit 1; }; }

backup() {
    # backup <archivo> <module_id>
    # Generacional: <nombre>.bak.<timestamp>. Conserva las últimas
    # LOCKD_BACKUP_KEEP generaciones (default 5). Si el helper exportó
    # LOCKD_MANIFEST, registra el backup en el manifiesto de la operación
    # (insumo del rollback).
    local src="$1" mod="$2"
    local dir="${BACKUP_BASE}/${mod}"
    local keep="${LOCKD_BACKUP_KEEP:-5}"
    [ -f "$src" ] || return 0
    mkdir -p "$dir"
    local dest
    dest="${dir}/$(basename "$src").bak.$(date +%Y%m%dT%H%M%S)"
    cp -p "$src" "$dest" && info "Backup: $src → $dest"
    if [ -n "${LOCKD_MANIFEST:-}" ]; then
        printf '%s|%s|%s|%s\n' "${LOCKD_OP_ID:-manual}" "$mod" "$src" "$dest" \
            >> "$LOCKD_MANIFEST" 2>/dev/null || true
    fi
    # poda: conservar solo las últimas $keep generaciones de este archivo
    ls -1t "${dir}/$(basename "$src")".bak.* 2>/dev/null | tail -n "+$((keep + 1))" \
        | while IFS= read -r old; do rm -f "$old"; done
}

restore() {
    # restore <archivo_destino> <module_id>
    # Restaura la generación MÁS RECIENTE. Acepta también el formato
    # legacy <nombre>.bak (backups creados antes del esquema generacional).
    local dest="$1" mod="$2"
    local dir="${BACKUP_BASE}/${mod}"
    local bak
    bak=$(ls -1t "${dir}/$(basename "$dest")".bak.* "${dir}/$(basename "$dest").bak" \
          2>/dev/null | head -1 || true)
    if [ -n "$bak" ] && [ -f "$bak" ]; then
        cp -p "$bak" "$dest" && info "Restaurado: $dest (desde $(basename "$bak"))"
    else
        warn "Sin backup: $dest"
    fi
}

apply() {
    # apply "desc" cmd [args...]
    local desc="$1"; shift
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] Would: $desc"
    else
        info "$desc"
        "$@"
    fi
}

# Busca sysctl en rutas habituales de Debian (puede estar en /sbin, no en PATH por defecto)
find_sysctl() {
    for candidate in sysctl /sbin/sysctl /usr/sbin/sysctl; do
        if command -v "$candidate" &>/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    # fallback: escribir directamente en /proc/sys si existe
    echo ""
    return 1
}
# shellcheck disable=SC2034  # SYSCTL la consumen los scripts que hacen source
SYSCTL="$(find_sysctl || true)"


# ── Escritura atómica ────────────────────────────────────────────────────────
write_file() {
    # write_file <ruta> [modo] < contenido
    # Escribe stdin en <ruta> vía archivo temporal + mv (nunca deja un config
    # a medio escribir). En dry-run muestra el contenido sin tocar nada.
    local dest="$1" mode="${2:-0644}" tmp
    if [ "$DRY_RUN" = "1" ]; then
        warn "[DRY-RUN] Would write: $dest"
        sed 's/^/    | /'
        return 0
    fi
    tmp="$(mktemp "${dest}.lockd.XXXXXX")"
    cat > "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dest"
}

# ── Línea base por ciclo de activación ───────────────────────────────────────
# Un rollback correcto devuelve el sistema al estado PREVIO a Lockd, no al de
# la última ejecución. baseline_begin captura los archivos una sola vez por
# ciclo (enable sobre un módulo sin línea base): reaplicar enable no la pisa.
# Los archivos que no existían se anotan en .absent (restaurarlos = borrarlos).
# baseline_restore la reinstala; baseline_end cierra el ciclo.
_baseline_marker() { printf '%s/%s/.baseline' "$BACKUP_BASE" "$1"; }

baseline_active() { [ -f "$(_baseline_marker "$1")" ]; }

baseline_begin() {
    # baseline_begin <module_id> [archivo...]
    local mod="$1"; shift
    local dir="${BACKUP_BASE}/${mod}" f
    if baseline_active "$mod"; then
        info "Línea base de '$mod' ya capturada: se conserva (reaplicación)."
        return 0
    fi
    if [ "$DRY_RUN" = "1" ]; then
        for f in "$@"; do warn "[DRY-RUN] Would backup (línea base): $f"; done
        return 0
    fi
    mkdir -p "$dir"
    : > "${dir}/.absent"
    for f in "$@"; do
        if [ -e "$f" ]; then
            backup "$f" "$mod"
        else
            printf '%s\n' "$f" >> "${dir}/.absent"
        fi
    done
    date -Is > "$(_baseline_marker "$mod")"
}

baseline_restore() {
    # baseline_restore <module_id> <archivo...>
    local mod="$1"; shift
    local absent="${BACKUP_BASE}/${mod}/.absent" f
    for f in "$@"; do
        if [ -f "$absent" ] && grep -qxF -- "$f" "$absent"; then
            apply "Eliminar $f (no existía antes de Lockd)" rm -f "$f"
        elif [ "$DRY_RUN" = "1" ]; then
            warn "[DRY-RUN] Would restore: $f"
        else
            restore "$f" "$mod"
        fi
    done
}

baseline_end() {
    local mod="$1"
    apply "Cerrar ciclo de línea base de '$mod'" \
        rm -f "$(_baseline_marker "$mod")" "${BACKUP_BASE}/${mod}/.absent"
}

# ── sshd ─────────────────────────────────────────────────────────────────────
reload_sshd() {
    # Recarga sshd según cómo corre. Las sesiones abiertas no se cortan: la
    # configuración nueva rige para las conexiones nuevas.
    local unit
    if ! command -v systemctl &>/dev/null || [ ! -d /run/systemd/system ]; then
        warn "Sin systemd: recargá sshd a mano (SIGHUP al proceso principal)."
        return 0
    fi
    for unit in ssh.service sshd.service; do
        if systemctl is-active --quiet "$unit"; then
            systemctl reload "$unit"
            info "sshd recargado ($unit)."
            return 0
        fi
    done
    if systemctl is-active --quiet ssh.socket; then
        info "sshd activado por socket: la configuración rige desde la próxima conexión."
        return 0
    fi
    warn "sshd no está corriendo: la configuración rige cuando arranque."
}
