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

# ── Modo test: raíz alternativa (LOCKD_SYSROOT) ──────────────────────────────
# Solo para tests: redirige las rutas del sistema de los módulos a un árbol de
# prueba ($SYSROOT/etc/fstab, ...). Nunca llega desde una ejecución real: el
# helper privilegiado arma un entorno mínimo sin esta variable y pkexec
# descarta el entorno del invocante. Una raíz que resuelve a "/" es el modo
# normal. En modo test todo falla cerrado:
#   - no corre como root: una ruta sin ${SYSROOT} o un comando llamado con
#     ruta absoluta fallan por permisos en vez de tocar el sistema real;
#   - antes de nada ejecuta el centinela $SYSROOT/.stubs/bin/lockd-stubs y
#     aborta si falta o no corre. Con /tmp montado noexec los stubs están pero
#     no se pueden ejecutar, y bash seguiría buscando en el PATH hasta dar con
#     el comando real;
#   - el PATH queda SOLO en $SYSROOT/.stubs/bin: lo que el árbol no provee
#     (stub o herramienta inocua) no existe, y command_not_found_handle lo
#     anota en $SYSROOT/.stubs/faltantes para que el test falle aunque el
#     módulo descarte el error;
#   - sin bus del sistema ni terminal: un systemctl alcanzado igual no llega a
#     systemd ni puede abrir un pedido de contraseña de polkit;
#   - avisa por stderr en cada ejecución.
SYSROOT=""
if [ -n "${LOCKD_SYSROOT:-}" ]; then
    # readlink -f normaliza "//", "/." y symlinks (pwd -P conserva "//")
    __lockd_root="$(readlink -f -- "$LOCKD_SYSROOT" 2>/dev/null)" || __lockd_root=""
    if [ -z "$__lockd_root" ] || [ ! -d "$__lockd_root" ]; then
        error "LOCKD_SYSROOT no es un directorio: $LOCKD_SYSROOT"
        exit 1
    fi
    if [ "$__lockd_root" != "/" ]; then
        if [ "$EUID" -eq 0 ]; then
            error "El modo test no corre como root: una ruta sin \${SYSROOT} tocaría el sistema real."
            exit 1
        fi
        if [ "$("$__lockd_root/.stubs/bin/lockd-stubs" 2>/dev/null)" != "ok" ]; then
            error "Faltan o no se pueden ejecutar los comandos simulados de $__lockd_root/.stubs/bin (¿montado con noexec?): se aborta para no tocar el sistema real."
            exit 1
        fi
        SYSROOT="$__lockd_root"
        PATH="$SYSROOT/.stubs/bin"           # cerrado a propósito
        export PATH
        export DBUS_SYSTEM_BUS_ADDRESS="unix:path=$SYSROOT/.stubs/sin-bus"
        exec </dev/null
        command_not_found_handle() {
            printf '%s\n' "$1" >> "$SYSROOT/.stubs/faltantes"
            echo "[lockd] MODO TEST: '$1' no tiene stub ni está entre las herramientas permitidas." >&2
            return 127
        }
        echo "[lockd] MODO TEST: raíz $SYSROOT; no se modifica el sistema real." >&2
    fi
    unset __lockd_root
fi
BACKUP_BASE="${LOCKD_BACKUP_BASE:-${SYSROOT}/var/lib/lockd/backups}"

check_root() {
    # Modo test: corre sin root por diseño (el bloque de arriba lo exige).
    [ -n "$SYSROOT" ] && return 0
    [ "$EUID" -eq 0 ] || { error "Requiere root."; exit 1; }
}
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
    # En modo test solo cuenta el PATH cerrado: una ruta absoluta saltearía
    # los stubs y llegaría al sysctl real.
    local candidates="sysctl /sbin/sysctl /usr/sbin/sysctl" candidate
    [ -n "$SYSROOT" ] && candidates="sysctl"
    for candidate in $candidates; do
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
    # Cada paso se comprueba, también cuando la llaman desde un if o un ||
    # (ahí bash no aplica set -e): $dest se reemplaza solo con el contenido
    # completo.
    tmp="$(mktemp "${dest}.lockd.XXXXXX")" || return 1
    if cat > "$tmp" && chmod "$mode" "$tmp" && mv -f "$tmp" "$dest"; then
        return 0
    fi
    rm -f "$tmp"
    return 1
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

# ── Reversión exacta: fstab, opciones de montaje y grupos ────────────────────
# Un módulo que endurece un punto de montaje deja tres rastros, y disable
# deshace exactamente esos, sin tocar lo ajeno:
#   - su línea en fstab, marcada al final con "# <marca>". Si el usuario ya
#     tenía una entrada para ese punto, se comenta con "# <marca>:original " y
#     la línea de Lockd suma sus opciones a las del usuario, así queda una
#     sola entrada activa por punto. La línea lleva explícitas las banderas
#     restrictivas que el punto ya tenía en ejecución (nosuid, nodev, noexec):
#     mount -o remount PUNTO y el arranque aplican las opciones de fstab, y
#     así las mantienen (comprobado con util-linux 2.39, con la API de montaje
#     nueva y con mount(2));
#   - las opciones en ejecución previas, guardadas una vez por ciclo de
#     activación (reaplicar enable las conserva). disable devuelve a su valor
#     previo las opciones que el módulo toca y también nosuid, nodev y noexec,
#     porque el remontaje mezcla las opciones de fstab;
#   - los grupos que creó y los miembros que agregó.
# enable es atómico: si el remontaje falla, fstab y lo guardado quedan como
# estaban antes de esa ejecución y el script sale con error.

_lockd_fstab() { printf '%s/etc/fstab' "$SYSROOT"; }

_lockd_en_lista() {
    # _lockd_en_lista "<a,b,c>" <elemento>: ¿está en la lista separada por comas?
    [[ ",$1," == *",$2,"* ]]
}

_lockd_valor_opcion() {
    # _lockd_valor_opcion "<opciones>" <clave>: imprime el valor de clave=valor
    local o IFS=','
    for o in $1; do
        if [[ "$o" == "$2="* ]]; then
            printf '%s\n' "${o#*=}"
            return 0
        fi
    done
}

_lockd_banderas_restrictivas() {
    # _lockd_banderas_restrictivas "<opciones>": las de nosuid,nodev,noexec presentes
    local b
    local -a res=()
    for b in nosuid nodev noexec; do
        if _lockd_en_lista "$1" "$b"; then res+=("$b"); fi
    done
    local IFS=','
    printf '%s\n' "${res[*]}"
}

_lockd_opcion_contraria() {
    case "$1" in
        exec) echo noexec ;;  noexec) echo exec ;;
        suid) echo nosuid ;;  nosuid) echo suid ;;
        dev)  echo nodev ;;   nodev)  echo dev ;;
        rw)   echo ro ;;      ro)     echo rw ;;
    esac
}

_lockd_opciones_fusionar() {
    # _lockd_opciones_fusionar "<base>" "<nuevas>": como mount, lo último gana.
    # Cada opción nueva reemplaza a la misma clave (clave=valor) y a su
    # contraria (exec/noexec, suid/nosuid, dev/nodev, rw/ro).
    local base="$1" op o clave contraria
    local -a res=() nuevas=() resto=()
    IFS=',' read -r -a res <<< "$base"
    IFS=',' read -r -a nuevas <<< "$2"
    for op in "${nuevas[@]}"; do
        [ -n "$op" ] || continue
        clave=""
        if [[ "$op" == *=* ]]; then clave="${op%%=*}="; fi
        contraria="$(_lockd_opcion_contraria "$op")"
        resto=()
        for o in "${res[@]}"; do
            if [ "$o" = "$op" ] || [ "$o" = "$contraria" ]; then continue; fi
            if [ -n "$clave" ] && [[ "$o" == "$clave"* ]]; then continue; fi
            resto+=("$o")
        done
        res=("${resto[@]}" "$op")
    done
    local IFS=','
    printf '%s\n' "${res[*]}"
}

fstab_aplicar() {
    # fstab_aplicar <marca> <origen> <punto> <tipo> <opciones> [conservar]
    # Deja una sola entrada activa para <punto>: la de Lockd, marcada. Sus
    # opciones: las de la línea del usuario si existía (que queda comentada),
    # más [conservar] (las banderas restrictivas en ejecución), más <opciones>.
    local marca="$1" origen="$2" punto="$3" tipo="$4" opciones="$5" conservar="${6:-}"
    local fstab linea base="" f1 f2 f3 f4 f5 f6
    local -a lineas=() salida=()
    fstab="$(_lockd_fstab)"
    if [ -f "$fstab" ]; then mapfile -t lineas < "$fstab"; fi
    for linea in "${lineas[@]}"; do
        if [[ "$linea" == *" # $marca" ]]; then
            continue                                  # la propia: se regenera
        elif [[ "$linea" == "# $marca:original "* ]]; then
            base="${linea#"# $marca:original "}"      # reaplicación
            salida+=("$linea")
            continue
        fi
        read -r f1 f2 _ <<< "$linea"
        if [ -n "${f1:-}" ] && [[ "$f1" != \#* ]] && [ "${f2:-}" = "$punto" ]; then
            if [ -z "$base" ]; then base="$linea"; fi
            salida+=("# $marca:original $linea")
        else
            salida+=("$linea")
        fi
    done
    local propias
    if [ -n "$base" ]; then
        read -r f1 f2 f3 f4 f5 f6 _ <<< "$base"
        propias="$(_lockd_opciones_fusionar "$f4" "$conservar")"
        propias="$(_lockd_opciones_fusionar "$propias" "$opciones")"
        salida+=("$f1 $f2 $f3 $propias ${f5:-0} ${f6:-0} # $marca")
    else
        propias="$(_lockd_opciones_fusionar "$conservar" "$opciones")"
        salida+=("$origen $punto $tipo $propias 0 0 # $marca")
    fi
    printf '%s\n' "${salida[@]}" | write_file "$fstab" 0644
}

fstab_quitar() {
    # fstab_quitar <marca>: borra la línea de Lockd y descomenta la del usuario.
    local marca="$1" fstab linea cambio=0
    local -a lineas=() salida=()
    fstab="$(_lockd_fstab)"
    [ -f "$fstab" ] || return 0
    mapfile -t lineas < "$fstab"
    for linea in "${lineas[@]}"; do
        if [[ "$linea" == *" # $marca" ]]; then
            cambio=1
        elif [[ "$linea" == "# $marca:original "* ]]; then
            salida+=("${linea#"# $marca:original "}")
            cambio=1
        else
            salida+=("$linea")
        fi
    done
    [ "$cambio" = 1 ] || return 0
    if [ "${#salida[@]}" -gt 0 ]; then printf '%s\n' "${salida[@]}"; fi | write_file "$fstab" 0644
}

_lockd_estado_montaje() {
    # _lockd_estado_montaje <mod> <punto>: archivo con las opciones previas
    local nombre="${2#/}"
    nombre="${nombre//\//_}"
    printf '%s/%s/montaje-%s.previas' "$BACKUP_BASE" "$1" "${nombre:-raiz}"
}

montaje_guardado() {
    # montaje_guardado <mod> <punto>: ¿este ciclo ya guardó las opciones?
    [ -f "$(_lockd_estado_montaje "$1" "$2")" ]
}

montaje_olvidar() {
    # montaje_olvidar <mod> <punto>: descarta lo guardado (enable que se deshace)
    rm -f "$(_lockd_estado_montaje "$1" "$2")"
}

montaje_guardar() {
    # montaje_guardar <mod> <punto>: guarda las opciones en ejecución, una vez
    # por ciclo. Devuelve 1 si <punto> no está montado.
    local estado opciones
    estado="$(_lockd_estado_montaje "$1" "$2")"
    [ -f "$estado" ] && return 0
    opciones="$(findmnt -n -o OPTIONS "$2" 2>/dev/null)" || return 1
    opciones="${opciones##*$'\n'}"                    # el montaje de arriba
    mkdir -p "$(dirname "$estado")"
    printf '%s\n' "$opciones" > "$estado"
}

montaje_restaurar() {
    # montaje_restaurar <mod> <punto> <opción...>: devuelve cada opción que el
    # módulo toca, y siempre nosuid, nodev y noexec, a su valor previo, y
    # olvida lo guardado. Opciones con regla: noexec, nosuid, nodev (vuelven a
    # la restrictiva o a su contraria) y hidepid, gid (sin valor previo: 0, el
    # valor por defecto del kernel).
    # Sin opciones guardadas (activado con una versión anterior de Lockd) no
    # adivina las banderas: las deja como están y avisa.
    local mod="$1" punto="$2" estado previas="" op valor
    local -a lista=()
    shift 2
    estado="$(_lockd_estado_montaje "$mod" "$punto")"
    if [ -f "$estado" ]; then
        previas="$(cat "$estado")"
    else
        warn "No hay opciones previas guardadas de $punto: exec/suid/dev quedan como están hasta reiniciar."
    fi
    local -a ops=("$@")
    for op in nosuid nodev noexec; do
        if ! _lockd_en_lista "$(IFS=','; echo "${ops[*]}")" "$op"; then ops+=("$op"); fi
    done
    for op in "${ops[@]}"; do
        case "$op" in
            noexec|nosuid|nodev)
                [ -f "$estado" ] || continue
                if _lockd_en_lista "$previas" "$op"; then lista+=("$op"); else lista+=("${op#no}"); fi
                ;;
            hidepid|gid)
                valor="$(_lockd_valor_opcion "$previas" "$op")"
                lista+=("$op=${valor:-0}")
                ;;
            *)
                error "montaje_restaurar: '$op' no tiene regla de restauración."
                return 1
                ;;
        esac
    done
    if [ "${#lista[@]}" -gt 0 ]; then
        local IFS=','
        mount -o "remount,${lista[*]}" "$punto" || return 1
    fi
    rm -f "$estado"
}

endurecer_montaje() {
    # endurecer_montaje <mod> <marca> <origen> <punto> <tipo> <opciones>
    # Guarda las opciones previas, deja la línea de Lockd en fstab y remonta.
    # Si el remontaje falla, fstab y lo guardado vuelven a como estaban antes
    # de esta ejecución y devuelve 1.
    local mod="$1" marca="$2" origen="$3" punto="$4" tipo="$5" opciones="$6"
    local fstab estado previo conservar estado_nuevo=0
    fstab="$(_lockd_fstab)"
    estado="$(_lockd_estado_montaje "$mod" "$punto")"
    [ -f "$estado" ] || estado_nuevo=1
    if ! montaje_guardar "$mod" "$punto"; then
        error "$punto no está montado."
        return 1
    fi
    conservar="$(_lockd_banderas_restrictivas "$(cat "$estado")")"
    # Se llama desde un if o un ||, donde bash no aplica set -e: cada paso se
    # comprueba a mano.
    previo="$(mktemp "${fstab}.lockd-previo.XXXXXX")" || return 1
    if ! cp -p "$fstab" "$previo"; then
        rm -f "$previo"
        error "No se pudo copiar $fstab: no se aplicó nada."
        return 1
    fi
    if fstab_aplicar "$marca" "$origen" "$punto" "$tipo" "$opciones" "$conservar" \
        && mount -o "remount,$opciones" "$punto"; then
        rm -f "$previo"
        return 0
    fi
    mv -f "$previo" "$fstab" || error "No se pudo devolver $fstab a su estado previo."
    if [ "$estado_nuevo" = 1 ]; then rm -f "$estado"; fi
    error "No se pudo aplicar $punto: fstab quedó como estaba y no se aplicó nada."
    return 1
}

revertir_montaje() {
    # revertir_montaje <mod> <marca> <punto> <opción...>
    # Primero fstab: mount -o remount PUNTO mezcla las opciones de fstab.
    local mod="$1" marca="$2" punto="$3"
    shift 3
    fstab_quitar "$marca"
    montaje_restaurar "$mod" "$punto" "$@"
}

_lockd_estado_grupos() { printf '%s/%s/grupos.estado' "$BACKUP_BASE" "$1"; }

grupos_registrados() {
    # grupos_registrados <mod>: ¿este ciclo ya creó grupos o sumó miembros?
    [ -f "$(_lockd_estado_grupos "$1")" ]
}

grupo_asegurar() {
    # grupo_asegurar <mod> <grupo>: crea el grupo si no existe y lo anota.
    local estado
    getent group "$2" >/dev/null && return 0
    groupadd "$2"
    estado="$(_lockd_estado_grupos "$1")"
    mkdir -p "$(dirname "$estado")"
    printf 'creado %s\n' "$2" >> "$estado"
}

grupo_sumar() {
    # grupo_sumar <mod> <grupo> <usuario>: si el usuario existe y no es
    # miembro, lo agrega y lo anota. Los miembros previos no se anotan.
    local mod="$1" grupo="$2" usuario="$3" estado miembros
    id "$usuario" &>/dev/null || return 0
    miembros="$(getent group "$grupo" | cut -d: -f4)"
    _lockd_en_lista "$miembros" "$usuario" && return 0
    usermod -aG "$grupo" "$usuario"
    estado="$(_lockd_estado_grupos "$mod")"
    mkdir -p "$(dirname "$estado")"
    printf 'miembro %s %s\n' "$grupo" "$usuario" >> "$estado"
}

grupo_revertir() {
    # grupo_revertir <mod>: quita los miembros que agregó Lockd y borra los
    # grupos que creó si quedaron vacíos. Lo previo a Lockd no se toca.
    local estado tipo grupo usuario
    estado="$(_lockd_estado_grupos "$1")"
    [ -f "$estado" ] || return 0
    while read -r tipo grupo usuario; do
        if [ "$tipo" = miembro ]; then
            gpasswd -d "$usuario" "$grupo" >/dev/null 2>&1 || true
        fi
    done < "$estado"
    while read -r tipo grupo _; do
        [ "$tipo" = creado ] || continue
        if [ -n "$(getent group "$grupo" | cut -d: -f4)" ]; then
            warn "El grupo $grupo tiene miembros que no agregó Lockd: se conserva."
        else
            groupdel "$grupo" || warn "No se pudo borrar el grupo $grupo."
        fi
    done < "$estado"
    rm -f "$estado"
}

# ── Servicios y paquetes ─────────────────────────────────────────────────────
# Un servicio vuelve a como estaba antes del ciclo de activación: habilitado o
# no, activo o no. servicio_guardar lo anota una vez por ciclo (reaplicar
# enable lo conserva) y servicio_restaurar lo reinstala. Un servicio que estaba
# activo antes de Lockd sigue activo al desactivar.
# Los paquetes que instala Lockd quedan instalados al desactivar: el módulo
# anota cuáles instaló y disable avisa que siguen en el sistema.

_lockd_estado_servicio() {
    # _lockd_estado_servicio <mod> <unidad>: archivo con el estado previo
    printf '%s/%s/servicio-%s.previo' "$BACKUP_BASE" "$1" "${2%.service}"
}

servicio_guardado() {
    # servicio_guardado <mod> <unidad>: ¿este ciclo ya guardó su estado?
    [ -f "$(_lockd_estado_servicio "$1" "$2")" ]
}

servicio_olvidar() {
    # servicio_olvidar <mod> <unidad>: descarta lo guardado (enable que se deshace)
    rm -f "$(_lockd_estado_servicio "$1" "$2")"
}

servicio_guardar() {
    # servicio_guardar <mod> <unidad>: anota si estaba habilitada y activa
    local estado habilitado=no activo=no
    estado="$(_lockd_estado_servicio "$1" "$2")"
    [ -f "$estado" ] && return 0
    if systemctl is-enabled --quiet "$2" 2>/dev/null; then habilitado=si; fi
    if systemctl is-active --quiet "$2" 2>/dev/null; then activo=si; fi
    mkdir -p "$(dirname "$estado")"
    printf 'habilitado=%s\nactivo=%s\n' "$habilitado" "$activo" > "$estado"
}

servicio_estaba_activo() {
    # servicio_estaba_activo <mod> <unidad>: ¿estaba activa antes del ciclo?
    grep -qx 'activo=si' "$(_lockd_estado_servicio "$1" "$2")" 2>/dev/null
}

servicio_restaurar() {
    # servicio_restaurar <mod> <unidad>: devuelve la unidad a su estado previo
    local estado
    estado="$(_lockd_estado_servicio "$1" "$2")"
    if [ ! -f "$estado" ]; then
        warn "No hay estado previo guardado de $2: queda como está."
        return 0
    fi
    if grep -qx 'activo=si' "$estado"; then
        systemctl start "$2"
    else
        systemctl stop "$2" 2>/dev/null || true
    fi
    if grep -qx 'habilitado=si' "$estado"; then
        systemctl enable "$2"
    else
        systemctl disable "$2" 2>/dev/null || true
    fi
    rm -f "$estado"
}

_lockd_registro_paquetes() { printf '%s/%s/paquetes' "$BACKUP_BASE" "$1"; }

_lockd_paquete_instalado() {
    # shellcheck disable=SC2016  # ${Status} es formato de dpkg-query
    [ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null)" = "install ok installed" ]
}

paquete_instalar() {
    # paquete_instalar <mod> <paquete...>: instala los que falten y anota cuáles
    # instaló Lockd.
    local mod="$1" p registro
    local -a faltan=()
    shift
    for p in "$@"; do
        if ! _lockd_paquete_instalado "$p"; then faltan+=("$p"); fi
    done
    [ "${#faltan[@]}" -gt 0 ] || return 0
    apt-get install -y "${faltan[@]}" || return 1
    registro="$(_lockd_registro_paquetes "$mod")"
    mkdir -p "$(dirname "$registro")"
    for p in "${faltan[@]}"; do
        if ! grep -qxF -- "$p" "$registro" 2>/dev/null; then
            printf '%s\n' "$p" >> "$registro"
        fi
    done
}

paquetes_avisar() {
    # paquetes_avisar <mod>: avisa qué paquetes instalados por Lockd siguen ahí
    local registro p
    registro="$(_lockd_registro_paquetes "$1")"
    [ -f "$registro" ] || return 0
    while read -r p; do
        [ -n "$p" ] || continue
        if _lockd_paquete_instalado "$p"; then
            info "$p sigue instalado (lo instaló Lockd). Si no lo usás: sudo apt remove $p"
        fi
    done < "$registro"
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
