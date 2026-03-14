# Cómo crear un módulo para LockToggle

> **Note:**

Un módulo es una carpeta con scripts Bash y una entrada en `modules/modules.yaml`.
No hace falta tocar el código Python.

---

## Estructura mínima

```
modules/mi_modulo/
├── enable.sh    ← aplica la medida de seguridad
├── disable.sh   ← deshace exactamente lo que hizo enable.sh
└── check.sh     ← devuelve 0 si activo, 1 si no
```

---

## Paso 1: Crear la carpeta

```bash
mkdir -p modules/mi_modulo
```

El nombre de la carpeta debe coincidir con el `id` del YAML.
Solo letras minúsculas, números y guiones bajos (`mi_modulo`).

---

## Paso 2: enable.sh

```bash
#!/bin/bash
# mi_modulo/enable.sh — breve descripción
set -euo pipefail
source "$(dirname "$0")/../_common.sh"

# Verificaciones previas
check_root
check_cmd mi_herramienta    # verifica que el binario existe

BACKUP_DIR="${BACKUP_BASE}/mi_modulo"
MI_CONF="/etc/mi_archivo.conf"

# Dry-run: mostrar qué haría sin hacer nada
if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would modify $MI_CONF"
    warn "[DRY-RUN] Would restart mi_servicio"
    exit 0
fi

# Backup del archivo antes de modificar
mkdir -p "$BACKUP_DIR"
backup "$MI_CONF" mi_modulo

# Lógica principal
cat >> "$MI_CONF" << 'CONF'
# LockToggle — Mi configuración
MiOpcion = valor
CONF

systemctl restart mi_servicio
info "Módulo activado correctamente."
exit 0
```

### Reglas obligatorias

- `set -euo pipefail` — aborta ante cualquier error
- `check_root` — verificar que corre como root
- Backup antes de modificar cualquier archivo del sistema
- Soportar `DRY_RUN=1` mostrando qué haría
- `exit 0` si es correcto, `exit 1` si da error

---

## Paso 3: disable.sh

Debe deshacer **exactamente** lo que hizo `enable.sh` y ser idempotente (ejecutarlo dos veces no debe causar errores).

```bash
#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/../_common.sh"

check_root
BACKUP_DIR="${BACKUP_BASE}/mi_modulo"
MI_CONF="/etc/mi_archivo.conf"

if [ "$DRY_RUN" = "1" ]; then
    warn "[DRY-RUN] Would restore $MI_CONF from backup"
    exit 0
fi

# restaurar backup si existe
restore "$MI_CONF" mi_modulo

systemctl restart mi_servicio 2>/dev/null || true
info "Módulo desactivado."
exit 0
```

---

## Paso 4: check.sh

Devuelve el estado actual del módulo:
- **0** → módulo activo (secure en el scan)
- **1** → módulo inactivo
- **2** → no se puede determinar (unknown)

```bash
#!/bin/bash
# check.sh — devuelve 0 si el módulo está activo
grep -q "MiOpcion = valor" /etc/mi_archivo.conf 2>/dev/null && exit 0 || exit 1
```

---

## Paso 5: Añadir en modules.yaml

```yaml
  - id: mi_modulo
    name: "Nombre Legible del Módulo"
    description: >
      Explicación en lenguaje sencillo para el usuario final.
      Qué hace, para qué sirve, cuándo NO conviene activarlo.
    category: network           # network|filesystem|kernel|services|access_control|system_hardening
    security_level: advanced    # basic|advanced|expert|paranoid
    risk_level: low             # low|medium|high
    requires_reboot: false
    impact: "Consecuencia visible para el usuario si algo falla."
    server_safe: true           # ¿seguro en producción?
    desktop_safe: true          # ¿seguro en desktop personal?
    enable_script: "mi_modulo/enable.sh"
    disable_script: "mi_modulo/disable.sh"
    check_script: "mi_modulo/check.sh"
    dependencies: []            # paquetes apt necesarios
    supported_distros:
      - debian
      - ubuntu
```

---

## Paso 6: Probar

```bash
# Test de scripts directamente
sudo DRY_RUN=1 bash modules/mi_modulo/enable.sh   # simulación
sudo bash modules/mi_modulo/enable.sh             # real
sudo bash modules/mi_modulo/check.sh; echo $?     # 0 = activo
sudo bash modules/mi_modulo/disable.sh            # revertir

# Test desde CLI
python3 locktoggle.py info mi_modulo
python3 locktoggle.py simulate mi_modulo
python3 locktoggle.py enable mi_modulo

# Verificar en GUI — el toggle aparece automáticamente
python3 locktoggle.py
```

---

## Buenas prácticas

### Preferir drop-ins sobre editar archivos directamente

```bash
# En vez de editar /etc/ssh/sshd_config:
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-mi-modulo.conf << 'CONF'
# LockToggle — Mi configuración SSH
MaxAuthTries 3
CONF
```

`disable.sh` solo necesita `rm -f /etc/ssh/sshd_config.d/99-mi-modulo.conf`.

### Validar antes de recargar servicios críticos

```bash
if sshd -t 2>/dev/null; then
    systemctl reload sshd
else
    rm -f /etc/ssh/sshd_config.d/99-mi-modulo.conf
    error "Configuración inválida. Revirtiendo."
    exit 1
fi
```

### Usar las funciones de _common.sh

```bash
source "$(dirname "$0")/../_common.sh"

check_root         # verifica root, sale si da no
check_cmd gcc      # verifica que gcc existe, sale si no
backup /etc/foo bar_module    # crea backup en /var/lib/locktoggle/backups/bar_module/
restore /etc/foo bar_module   # restaura desde backup
apply "Descripción" comando arg1 arg2   # ejecuta o muestra en dry-run
```

---

## Categorías y niveles disponibles

**Categorías (`category`):**
`network` · `filesystem` · `kernel` · `services` · `access_control` · `system_hardening` · `privacy`

**Niveles (`security_level`):**
- `basic` — medidas esenciales para cualquier sistema
- `advanced` — hardening moderado, adecuado para la mayoría
- `expert` — requiere conocimiento del impacto en el sistema
- `paranoid` — máxima restricción, revisar compatibilidad

---

## Contribuir al repositorio

Abre un Pull Request con:
- La carpeta `modules/mi_modulo/` completa
- La entrada en `modules/modules.yaml`
- README.md del módulo explicando qué hace
- Salida de `sudo DRY_RUN=1 bash enable.sh` en tu equipo
- Versión de Debian/Ubuntu probada
