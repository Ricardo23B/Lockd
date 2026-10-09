#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable. Sin root.
#
# Activo = el drop-in de Lockd existe Y cada opción que define es la que sshd
# usa de verdad. Se resuelve como sshd: gana el PRIMER valor, `Include` se
# expande en su posición (orden léxico) y cada archivo se corta en su primer
# `Match`. Un archivo ilegible antes de resolver todas las opciones → 2.
# (Antes bastaba con que el archivo existiera, aunque otro drop-in lo pisara.)
# Las variables LOCKD_SSHD_* solo existen para los tests.
export LC_ALL=C
shopt -s nullglob
SSHD_CONFIG="${LOCKD_SSHD_CONFIG:-/etc/ssh/sshd_config}"
DROP_IN="${LOCKD_SSHD_DROPIN:-/etc/ssh/sshd_config.d/00-lockd-hardening.conf}"
LEGACY="${LOCKD_SSHD_DROPIN_LEGACY:-/etc/ssh/sshd_config.d/99-lockd-hardening.conf}"

[ -f "$DROP_IN" ] || DROP_IN="$LEGACY"      # instalado por una versión anterior
[ -f "$DROP_IN" ] || exit 1
if [ ! -r "$DROP_IN" ] || [ ! -r "$SSHD_CONFIG" ]; then
    exit 2
fi

walk() {
    # Emite "opción<TAB>valor" en el orden de lectura de sshd;
    # "!unreadable<TAB>archivo" si no puede leer uno.
    local file="$1" depth="$2" line kw rest pat inc
    [ "$depth" -gt 8 ] && return 0
    if [ ! -r "$file" ]; then
        printf '!unreadable\t%s\n' "$file"
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [ -z "$line" ] && continue
        [ "${line:0:1}" = "#" ] && continue
        kw="${line%%[[:space:]=]*}"
        rest="${line:${#kw}}"
        rest="${rest#"${rest%%[![:space:]=]*}"}"
        kw="${kw,,}"
        if [ "$kw" = "challengeresponseauthentication" ]; then
            kw="kbdinteractiveauthentication"       # alias histórico
        fi
        case "$kw" in
            match) return 0 ;;
            include)
                for pat in $rest; do
                    [[ "$pat" = /* ]] || pat="$(dirname "$SSHD_CONFIG")/$pat"
                    # expansión de glob intencional (nullglob, orden léxico C)
                    # shellcheck disable=SC2086
                    for inc in $pat; do walk "$inc" $((depth + 1)); done
                done ;;
            *) printf '%s\t%s\n' "$kw" "${rest%%[[:space:]]*}" ;;
        esac
    done < "$file"
}

declare -A want=() seen=()
while IFS=$'\t' read -r kw val; do
    [ "$kw" = "!unreadable" ] && exit 2
    want["$kw"]="${val,,}"
done < <(walk "$DROP_IN" 0)
[ "${#want[@]}" -gt 0 ] || exit 1

pending=${#want[@]}
while IFS=$'\t' read -r kw val; do
    [ "$kw" = "!unreadable" ] && exit 2
    [ -n "${want[$kw]+x}" ] || continue
    [ -n "${seen[$kw]+x}" ] && continue
    seen["$kw"]=1
    [ "${val,,}" = "${want[$kw]}" ] || exit 1
    pending=$((pending - 1))
    [ "$pending" -eq 0 ] && exit 0
done < <(walk "$SSHD_CONFIG" 0)
exit 1          # alguna opción del drop-in no llega a sshd (¿falta el Include?)
