#!/usr/bin/env bash
# clamav_scanner/enable.sh — instala ClamAV y activa escaneos programados
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../_common.sh"


TIMER_FILE="/etc/systemd/system/lockd-clamav.timer"
SERVICE_FILE="/etc/systemd/system/lockd-clamav.service"
SCAN_LOG="/var/log/lockd/clamav_scan.log"
QUARANTINE_DIR="/var/quarantine/lockd"

info "Verificando instalación de ClamAV..."

if ! command -v clamscan &>/dev/null; then
    info "ClamAV no encontrado. Instalando..."
    apt-get install -y clamav clamav-daemon clamav-freshclam
    info "ClamAV instalado."
else
    info "ClamAV ya está instalado."
fi

# Crear directorios necesarios
mkdir -p /var/log/lockd
mkdir -p "$QUARANTINE_DIR"
chmod 700 "$QUARANTINE_DIR"

# Actualizar base de datos de virus
info "Actualizando base de datos de firmas (freshclam)..."
systemctl stop clamav-freshclam 2>/dev/null || true
freshclam --quiet || warn "freshclam falló — base de datos puede estar desactualizada."
systemctl start clamav-freshclam 2>/dev/null || true

# Crear el servicio systemd que ejecuta el escaneo
cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=Lockd — Escaneo antivirus programado (ClamAV)
Documentation=https://github.com/Ricardo23B/Lockd
After=network.target clamav-freshclam.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c '\
    LOG=/var/log/lockd/clamav_scan.log; \
    QDIR=/var/quarantine/lockd; \
    echo "=== Escaneo iniciado: $(date) ===" >> $LOG; \
    clamscan --recursive --infected --remove=no \
             --move="$QDIR" \
             --log="$LOG" \
             /home /tmp /var/tmp 2>&1 | tail -20 >> $LOG; \
    echo "=== Escaneo finalizado: $(date) ===" >> $LOG; \
    INFECTED=$(grep -c "FOUND" $LOG 2>/dev/null || echo 0); \
    if [ "$INFECTED" -gt 0 ]; then \
        notify-send -u critical "Lockd — ClamAV" \
            "$INFECTED archivo(s) infectado(s) detectado(s). Revisar /var/log/lockd/clamav_scan.log" \
            2>/dev/null || true; \
    fi'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Crear el timer systemd (escaneo 3 veces por semana: lunes, miércoles, viernes a las 03:00)
cat > "$TIMER_FILE" <<'EOF'
[Unit]
Description=Lockd — Timer de escaneo antivirus ClamAV
Documentation=https://github.com/Ricardo23B/Lockd

[Timer]
OnCalendar=Mon,Wed,Fri 03:00:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now lockd-clamav.timer

info "ClamAV activado. Escaneos programados: lun/mié/vie a las 03:00."
info "Cuarentena: $QUARANTINE_DIR"
info "Log: $SCAN_LOG"
