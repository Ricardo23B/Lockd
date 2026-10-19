#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable.
# Activo si el servicio apparmor corre y ningún perfil quedó en complain, con
# el criterio de enable (apparmor_en_complain en _common.sh): no cuentan los
# deshabilitados (enlace en disable/) ni los que declaran unconfined. Lee
# /etc/apparmor.d, que no pide privilegios.
DIR="${LOCKD_SYSROOT:-}/etc/apparmor.d"
systemctl is-active --quiet apparmor 2>/dev/null || exit 1
[ -d "$DIR" ] || exit 1
if [ ! -r "$DIR" ] || [ ! -x "$DIR" ]; then exit 2; fi
for f in "$DIR"/*; do
    if [ ! -f "$f" ] || [ -L "$f" ]; then continue; fi
    n="${f##*/}"
    case "$n" in
        .*|README|*.dpkg-new|*.dpkg-old|*.dpkg-dist|*.dpkg-bak|*.dpkg-remove) continue ;;
        *.pacsave|*.pacnew|*.rpmnew|*.rpmsave|*.orig|*.rej|*~) continue ;;
    esac
    [ -L "$DIR/disable/$n" ] && continue
    [ -r "$f" ] || exit 2
    banderas=",$(sed -nE 's/^[[:space:]]*[^#[:space:]].*\(([^)]*)\)[[:space:]]*\{.*$/\1,/p' "$f" \
        | tr -d ' \t\n')"
    [[ "$banderas" == *,unconfined,* ]] && continue
    if [ -L "$DIR/force-complain/$n" ] || [[ "$banderas" == *,complain,* ]]; then
        exit 1
    fi
done
exit 0
