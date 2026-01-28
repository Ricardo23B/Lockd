# _common.sh — funciones comunes para todos los scripts de Lockd
# Source: source "$(dirname "$0")/../_common.sh"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
DRY_RUN="${DRY_RUN:-0}"
BACKUP_BASE="/var/lib/lockd/backups"

check_root() { [ "$EUID" -eq 0 ] || { error "Requiere root."; exit 1; }; }
check_cmd()  { command -v "$1" &>/dev/null || { error "Falta: $1 (apt install $1)"; exit 1; }; }

backup() {
    local src="$1" mod="$2"
    local dir="${BACKUP_BASE}/${mod}"
    mkdir -p "$dir"
    [ -f "$src" ] && cp "$src" "${dir}/$(basename "$src").bak" && info "Backup: $src"
}

restore() {
    local dest="$1" mod="$2"
    local bak="${BACKUP_BASE}/${mod}/$(basename "$dest").bak"
    [ -f "$bak" ] && cp "$bak" "$dest" && info "Restaurado: $dest" || warn "Sin backup: $dest"
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
SYSCTL="$(find_sysctl || true)"

