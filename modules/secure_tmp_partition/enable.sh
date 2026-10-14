#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
check_root
DROP_IN="${SYSROOT}/etc/systemd/system/tmp.mount.d/lockd-secure.conf"
DROP_DIR="$(dirname "$DROP_IN")"
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Guardaría las opciones actuales de /tmp"
    warn "[DRY-RUN] Crearía $DROP_IN (nosuid,nodev,noexec)"
    warn "[DRY-RUN] systemctl daemon-reload"
    warn "[DRY-RUN] mount -o remount,nosuid,nodev,noexec /tmp"
    exit 0
fi

escribir_drop_in() {
    mkdir -p "$DROP_DIR"
    write_file "$DROP_IN" 0644 << 'CONF'
[Mount]
Options=mode=1777,strictatime,nosuid,nodev,noexec
CONF
}

if ! findmnt -n /tmp &>/dev/null; then
    # Sin montaje propio no hay nada que remontar: el drop-in rige cuando
    # tmp.mount se use.
    escribir_drop_in
    systemctl daemon-reload
    warn "/tmp no es un punto de montaje separado: el cambio rige cuando tmp.mount se use."
    exit 0
fi

# Atómico: si el remontaje falla, el drop-in y lo guardado vuelven a como
# estaban antes de esta ejecución.
guardado_previo=0
if montaje_guardado secure_tmp_partition /tmp; then guardado_previo=1; fi
montaje_guardar secure_tmp_partition /tmp
drop_in_previo=""
if [ -f "$DROP_IN" ]; then drop_in_previo="$(cat "$DROP_IN")"; fi
escribir_drop_in
systemctl daemon-reload
if ! mount -o remount,nosuid,nodev,noexec /tmp; then
    if [ -n "$drop_in_previo" ]; then
        printf '%s\n' "$drop_in_previo" | write_file "$DROP_IN" 0644
    else
        rm -f "$DROP_IN"
        rmdir --ignore-fail-on-non-empty "$DROP_DIR" 2>/dev/null || true
    fi
    systemctl daemon-reload
    if [ "$guardado_previo" = 0 ]; then montaje_olvidar secure_tmp_partition /tmp; fi
    error "No se pudo remontar /tmp: se deshizo el drop-in y no se aplicó nada."
    exit 1
fi
info "/tmp remontado con nosuid,nodev,noexec."
