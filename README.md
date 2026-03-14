# 🔒 Lockd Linux

**Herramienta de hardening para Linux con GUI, CLI y auditoría integrada.**

Lockd convierte configuraciones de seguridad complejas en interruptores simples,
accesibles tanto desde un escritorio, desde CLI o en un servidor remoto.

## Modos principales

### 1. Security Scan
Analiza el sistema y lo calcula con un **Security Score (0-100)**:

### 2. Perfiles
Aplica una configuración completa con un solo comando:

| Perfil                  | Módulos incluidos                           |
|-------------------------|---------------------------------------------|
| `home_desktop`          | Firewall, updates, Fail2ban, /tmp, /proc    |
| `developer_workstation` | + SSH endurecido, sysctl                    |
| `server`                | + USB bloqueado, /dev/shm, AppArmor         |
| `paranoid`              | Todo + kernel blacklist, SUID, compiladores |

### 3. Modo Avanzado / Niveles
Activa módulos individuales o aplica por nivel de hardening:

```
Básico    → Firewall + Fail2ban + Updates
Avanzado  → + SSH + sysctl + /tmp + /proc
Experto   → + AppArmor + Kernel modules + SUID
Paranoico → + USB + /dev/shm + Compiladores
```

## Requisitos

```bash
sudo apt install python3 python3-gi python3-yaml \
                 gir1.2-gtk-4.0 gir1.2-adw-1 \
                 libpolkit-gobject-1-0 policykit-1
```
(esto lo hace al ejecutar el setup.sh)
---

## Instalación

```bash
git clone https://github.com/Ricardo23B/Lockd.git
cd Lockd
bash setup.sh
```

`setup.sh` hace todo en un paso: da permisos a los scripts, instala aliases
en tu shell y detecta si hay pantalla disponible o estás conectado por SSH.

1) **Desktop:** abre la GUI directamente.
2) **SSH / servidor:** muestra un menú interactivo en terminal.
  En caso de que falle la GUI el programa cae a TUI en CLI

Para activar los aliases en la sesión actual sin reiniciar
```bash
source ~/.bashrc
```

---

## Aliases disponibles tras el setup

```bash
lockd             # abre GUI o CLI según el entorno
lockd-scan        # escaneo rápido del sistema
lockd-adv         # modo avanzado TUI (funciona por SSH)
lockd-tui         # igual que lockd-adv
lockd-status      # estado actual de todos los módulos
lockd-list        # listar módulos disponibles
lockd-sim         # dry-run global (simula sin aplicar cambios)
```

---

## Referencia CLI completa

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

# opciones globales
lockd --dry-run scan            # simular todo
lockd --log-level DEBUG scan    # logging detallado
lockd --no-color scan           # sin colores
lockd --version
```

## Seguridad y privilegios

- Usa **pkexec (Polkit)** para obtener root. Nunca `sudo`.
- Backups automáticos en `/var/lib/lockd/backups/<module>/`
- Estado persistente en `~/.config/lockd/state.json`
- Logs en `/var/log/lockd.log`

## Dry-run / Simulación

```bash
lockd --dry-run enable kernel_sysctl_hardening
# [WARN] [DRY-RUN] Would: Create /etc/sysctl.d/99-lockd-hardening.conf

DRY_RUN=1 bash modules/kernel_sysctl_hardening/enable.sh
```

## Crear un módulo nuevo

Ver [docs/CREACION_MODULE.md](docs/CREACION_MODULE.md).

1) `mkdir modules/mi_modulo/`
2) Escribir `enable.sh`, `disable.sh`, `check.sh`
3) `chmod +x modules/mi_modulo/*.sh`
4) Añadir entrada en `modules/modules.yaml`
5) Reiniciar Lockd — aparece automáticamente en GUI y CLI

## Estructura del proyecto

```
lockd/
├── lockd.py               # punto de entrada (GUI/CLI auto)
├── setup.sh               # setup + aliases + launcher
├── src/
│   ├── app/controller.py      # lógica de negocio central
│   ├── engine/
│   │   ├── module_loader.py
│   │   ├── executor.py        # pkexec + threading
│   │   ├── scanner.py         # 16 checks de auditoría
│   │   ├── state_runtime.py
│   │   ├── profile_ctx.py
│   │   ├── level_manager.py
│   │   ├── distro_detector.py
│   │   └── logger.py
│   └── interfaces/
│       ├── gui/               # GTK4 + Adwaita
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
└── docs/
    ├── CREACION_MODULE.md
    └── ARQUITECTURA.md
```

## Licencia

GPLv3 — Ver [LICENSE](LICENSE).
