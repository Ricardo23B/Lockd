#!/bin/bash
# Contrato de checks: 0 = activo · 1 = inactivo · 2 = no determinable.
# Sin root: `ufw status` requiere privilegios, así que se leen las fuentes de
# verdad persistentes: /etc/ufw/ufw.conf (ENABLED=yes lo escribe `ufw enable`)
# y /etc/default/ufw (política entrante). Activo = encendido Y entrante
# denegado: UFW encendido con entrante ACCEPT no es lo que aplica el módulo.
command -v ufw &>/dev/null || exit 2
CONF=/etc/ufw/ufw.conf
DEFAULTS=/etc/default/ufw
if [ -r "$CONF" ]; then
    grep -q "^ENABLED=yes" "$CONF" || exit 1
    if [ -r "$DEFAULTS" ]; then
        grep -qE '^DEFAULT_INPUT_POLICY="?(DROP|REJECT)"?' "$DEFAULTS" && exit 0 || exit 1
    fi
    exit 0
fi
systemctl is-active --quiet ufw && exit 0 || exit 2
