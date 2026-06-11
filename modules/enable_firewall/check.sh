#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable.
# Sin root: `ufw status` requiere privilegios, así que se lee la fuente de
# verdad persistente (/etc/ufw/ufw.conf, donde `ufw enable` escribe
# ENABLED=yes) con fallback al estado del servicio.
command -v ufw &>/dev/null || exit 2
CONF=/etc/ufw/ufw.conf
if [ -r "$CONF" ]; then
    grep -q "^ENABLED=yes" "$CONF" && exit 0 || exit 1
fi
systemctl is-active --quiet ufw && exit 0 || exit 2
