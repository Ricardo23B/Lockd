# 🔒 Lockd Linux

[![Pipeline](https://gitlab.com/Ricardo23B/Lockd/badges/main/pipeline.svg)](https://gitlab.com/Ricardo23B/Lockd/-/pipelines)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

**Herramienta de hardening para Linux con GUI, CLI y auditoría integrada.**

Lockd convierte configuraciones de seguridad complejas en interruptores simples,
accesibles tanto desde un escritorio gráfico, desde CLI o en un servidor remoto vía SSH.

---

## Características

- **Security Scan** con score 0–100 y sugerencias de corrección.
- **GUI moderna** GTK4 + libadwaita, responsiva, con tema claro/oscuro automático.
- **TUI interactiva** (curses) para entornos SSH o sin display.
- **Perfiles predefinidos** que aplican un conjunto de módulos en un paso.
- **Niveles acumulativos**: Básico → Avanzado → Experto → Paranoico.
- **Modo Avanzado**: toggles individuales por categoría con detalle de riesgo e impacto.
- **Dry-run**: simulación completa sin modificar el sistema.
- **ClamAV** integrado como categoría de módulo (escaneo antivirus opcional).
- Backups automáticos antes de cada cambio.
- Operaciones privilegiadas vía **Polkit** (pkexec), nunca sudo hardcodeado.

---

## Modos principales

### 1. Security Scan

Analiza el sistema y devuelve un **Security Score (0–100)** con checks sobre:
cortafuegos, Fail2ban, SSH, /tmp, /proc, USB, actualizaciones automáticas,
core dumps, sysctl, AppArmor, puertos abiertos, binarios SUID y más.

### 2. Perfiles

Aplica una configuración completa con un solo comando:

| Perfil                    | Módulos incluidos                              |
|---------------------------|------------------------------------------------|
| `home_desktop`            | Firewall, updates, Fail2ban, /tmp, /proc       |
| `developer_workstation`   | + SSH endurecido, sysctl                       |
| `server`                  | + USB bloqueado, /dev/shm, AppArmor            |
| `paranoid`                | Todo + kernel blacklist, SUID, compiladores    |

### 3. Modo Avanzado / Niveles

Activá módulos individuales o aplicá por nivel de hardening:

```
Básico    → Firewall + Fail2ban + Updates
Avanzado  → + SSH + sysctl + /tmp + /proc
Experto   → + AppArmor + Kernel modules + SUID
Paranoico → + USB + /dev/shm + Compiladores
```

---

## Requisitos del sistema

### Paquetes del sistema (GTK/libadwaita/Polkit — no instalables vía pip)

```bash
sudo apt install \
    python3 python3-gi python3-yaml \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    libpolkit-gobject-1-0 policykit-1
```

### ClamAV (opcional — para módulos de antivirus)

```bash
# Instalación del motor y daemon
sudo apt install clamav clamav-daemon clamav-freshclam

# Actualizar base de firmas (primera vez)
sudo freshclam

# Habilitar y arrancar el daemon
sudo systemctl enable --now clamav-daemon
sudo systemctl enable --now clamav-freshclam

# Verificar que funciona
clamscan --version
```

> **Nota:** Lockd detecta automáticamente si ClamAV está instalado.
> Los módulos de antivirus aparecen deshabilitados (switch gris) si `clamscan`
> o `clamav-daemon` no están presentes. No es obligatorio para el resto de la herramienta.

### UFW, Fail2ban (recomendados para la mayoría de módulos)

```bash
sudo apt install ufw fail2ban
```

---

## Instalación

```bash
git clone https://gitlab.com/Ricardo23B/Lockd.git
cd Lockd
bash setup.sh
```

`setup.sh` hace todo en un paso: da permisos a los scripts, instala aliases
en tu shell y detecta si hay pantalla disponible o estás conectado por SSH.

1. **Desktop:** abre la GUI directamente.
2. **SSH / servidor:** muestra un menú interactivo en terminal.
   En caso de que falle la GUI, el programa cae automáticamente a TUI en CLI.

Para activar los aliases en la sesión actual sin reiniciar:

```bash
source ~/.bashrc   # o source ~/.zshrc según tu shell
```

---

## Aliases disponibles tras el setup

### Lanzador principal

| Alias | Qué hace |
|-------|----------|
| `lockd` | Detecta el entorno: abre la GUI si hay display, TUI si no. |
| `lockd-gui` | Fuerza la apertura de la GUI GTK4 (requiere display). |
| `lockd-tui` | Fuerza la TUI interactiva en terminal (funciona por SSH). |
| `lockd-adv` | Igual que `lockd-tui` — modo avanzado directo. |

> **¿Cuándo usar cada uno?**
> - En tu escritorio de trabajo → `lockd` o `lockd-gui`
> - Conectado por SSH a un servidor → `lockd-tui` o `lockd-adv`
> - Script automatizado → CLI directa (`lockd scan`, `lockd enable …`)

### Operaciones rápidas

| Alias | Equivale a |
|-------|------------|
| `lockd-scan` | `lockd scan` — auditoría del sistema |
| `lockd-status` | `lockd status` — estado de todos los módulos |
| `lockd-list` | `lockd list` — listar módulos disponibles |
| `lockd-sim` | `lockd --dry-run` — simular sin aplicar cambios |

### ClamAV

| Alias | Qué hace |
|-------|----------|
| `lockd-clamav-on` | Activa el módulo ClamAV + escaneos programados |
| `lockd-clamav-off` | Desactiva los escaneos programados |
| `lockd-clamav-status` | Estado actual del módulo ClamAV |
| `lockd-clamav-info` | Información detallada (riesgo, impacto, deps) |
| `lockd-clamav-scan` | Ejecuta un escaneo manual inmediato de `/home /tmp /var/tmp` |

> Los aliases de ClamAV aparecen en el shell pero los comandos devuelven
> un error claro si `clamav` no está instalado — no rompen nada.

Para desinstalar todos los aliases:
```bash
bash install_aliases.sh --remove
```

---

## Modo Avanzado: GUI vs Terminal

El **Modo Avanzado** es la misma funcionalidad (toggles individuales por módulo,
agrupados por categoría) disponible en dos interfaces:

### En la GUI (GTK4 + libadwaita)

Accesible desde la pestaña **Avanzado** de la ventana principal.

- Cada módulo es un `AdwActionRow` con switch, badges de riesgo/nivel y botón ⓘ de detalle.
- Filtro "Solo seguros para servidor" para ocultar módulos solo-desktop.
- Al hacer click en una sugerencia del Security Scan, navega automáticamente
  al módulo correspondiente y lo resalta.
- Confirmaciones con diálogo antes de activar módulos destructivos (SSH, USB, SUID…).
- Feedback de resultado inline, sin bloquear la interfaz.

```bash
lockd-gui        # abre la ventana → ir a pestaña "Avanzado"
lockd            # igual, si hay display disponible
```

### En la terminal (TUI curses)

Accesible por SSH o en cualquier entorno sin display gráfico.

- Navegación con teclado: flechas, Enter para toggle, `q` para salir.
- Mismas categorías y módulos que la GUI.
- Funciona en cualquier terminal con soporte de colores ANSI.
- Ideal para servidores remotos.

```bash
lockd-tui        # TUI interactiva completa
lockd-adv        # alias equivalente
lockd advanced   # comando directo sin alias
```

### Comparativa rápida

| Característica | GUI | TUI |
|----------------|-----|-----|
| Toggle módulos | ✓ | ✓ |
| Filtro servidor | ✓ | ✓ |
| Ver detalles del módulo | ✓ (popover ⓘ) | ✓ (panel lateral) |
| Confirmaciones destructivas | ✓ (diálogo) | ✓ (prompt) |
| Funciona por SSH | ✗ | ✓ |
| Requiere display | ✓ | ✗ |
| Dry-run visual | ✓ (banner) | ✓ (indicador) |

```bash
lockd scan                      # auditoría del sistema
lockd list                      # lista todos los módulos
lockd list --category network   # filtrar por categoría
lockd list --server-only        # solo módulos server-safe
lockd status                    # estado actual de módulos

lockd enable  <module_id>       # activar módulo
lockd disable <module_id>       # desactivar módulo
lockd simulate <module_id>      # simular activación (sin cambios)
lockd info <module_id>          # información detallada

lockd profiles                  # listar perfiles
lockd profile <profile_id>      # aplicar perfil
lockd profile server --yes      # sin confirmación

lockd levels                    # listar niveles
lockd level advanced            # aplicar nivel

lockd advanced                  # TUI interactiva
lockd tui                       # alias de advanced

# Opciones globales
lockd --dry-run scan            # simular todo
lockd --log-level DEBUG scan    # logging detallado
lockd --no-color scan           # sin colores
lockd --version
```

---

## Seguridad y privilegios

- Usa **pkexec (Polkit)** para obtener root. Nunca `sudo` hardcodeado.
- Backups automáticos en `/var/lib/lockd/backups/<module>/`
- Estado persistente en `~/.config/lockd/state.json`
- Logs en `/var/log/lockd.log`

---

## Dry-run / Simulación

```bash
lockd --dry-run enable kernel_sysctl_hardening
# [WARN] [DRY-RUN] Would: Create /etc/sysctl.d/99-lockd-hardening.conf

DRY_RUN=1 bash modules/kernel_sysctl_hardening/enable.sh
```

---

## Crear un módulo nuevo

Ver [docs/CREACION_MODULE.md](docs/CREACION_MODULE.md).

1. `mkdir modules/mi_modulo/`
2. Escribir `enable.sh`, `disable.sh`, `check.sh`
3. `chmod +x modules/mi_modulo/*.sh`
4. Añadir entrada en `modules/modules.yaml`
5. Reiniciar Lockd — aparece automáticamente en GUI y CLI

---

## Estructura del proyecto

```
lockd/
├── lockd.py               # punto de entrada (GUI/CLI auto)
├── setup.sh               # setup + aliases + launcher
├── pyproject.toml         # metadatos del paquete Python
├── CHANGELOG.md           # historial de versiones
├── lockd/
│   ├── app/controller.py      # lógica de negocio central
│   ├── engine/
│   │   ├── module_loader.py   # carga y valida modules.yaml
│   │   ├── executor.py        # pkexec + threading
│   │   ├── scanner.py         # 16+ checks de auditoría
│   │   ├── state_runtime.py
│   │   ├── profile_ctx.py
│   │   ├── level_manager.py
│   │   ├── distro_detector.py
│   │   └── logger.py
│   └── interfaces/
│       ├── gui/               # GTK4 + libadwaita
│       │   ├── main_window.py
│       │   ├── profile_view.py
│       │   ├── level_view.py
│       │   ├── module_view.py
│       │   ├── module_widget.py
│       │   └── scan_view.py
│       └── cli/
│           ├── main.py        # CLI con colores
│           └── tui.py         # TUI interactiva (curses)
├── modules/
│   ├── modules.yaml           # catálogo maestro
│   ├── _common.sh
│   └── <modulo>/enable.sh  disable.sh  check.sh
├── profiles/
│   ├── home_desktop.yaml
│   ├── developer_workstation.yaml
│   ├── server.yaml
│   ├── paranoid.yaml
│   └── lab_test.yaml
├── packaging/
│   ├── desktop/io.github.lockd.desktop
│   └── polkit/io.github.lockd.policy
└── docs/
    ├── CREACION_MODULE.md
    └── ARQUITECTURA.md
```

---

## Licencia

GPLv3 — Ver [LICENSE](LICENSE).