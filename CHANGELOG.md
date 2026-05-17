# Changelog — Lockd Linux

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).
Lockd usa [Versionado Semántico](https://semver.org/lang/es/).

---

## [Unreleased]

### En progreso
- Integración completa de ClamAV: escaneo programado, panel de resultados en GUI.
- Soporte para Fedora/RHEL (dnf) en `distro_detector.py`.
- Tema oscuro automático respetando preferencia del sistema.

---

## [0.4.0] — 2026-05-15

### Añadido
- **GUI GTK4 + libadwaita completa**: `AdwApplicationWindow`, `AdwViewStack` con tres pestañas (Perfiles, Niveles, Avanzado), `AdwViewSwitcher` en header y `AdwViewSwitcherBar` en footer para móvil/ventana estrecha.
- **Status bar dinámica** con Security Score coloreado, nivel actual y perfil activo. Chips de sugerencias con `Gtk.FlowBox` (wrap automático al redimensionar).
- **`ModuleWidget`** basado en `AdwActionRow`: badges de riesgo/nivel, ícono de reinicio requerido, indicador de compatibilidad servidor/desktop y popover de detalles (ⓘ).
- **Modo Avanzado** (`ModuleView`): toggle individual por categoría usando `AdwPreferencesGroup`. Filtro "solo seguros para servidor". `highlight_and_enable()` para navegar directamente desde sugerencias del scan.
- **Banner de dry-run** (`AdwBanner`) visible cuando el modo simulación está activo.
- **`AdwMessageDialog`** para confirmaciones destructivas (SSH, USB, SUID, AppArmor, compiladores).
- **`AdwAboutWindow`** accesible desde el menú hamburguesa.
- **Pipeline GitLab CI** con lint (flake8), test matrix Python 3.11/3.12/3.13 y build `.deb` automático en tags `vX.Y.Z`.
- **`pyproject.toml`** estándar con dependencias declaradas y entry point `lockd`.
- **`install_aliases.sh`**: instalación de aliases en bash/zsh con detección de entorno (GUI vs SSH→TUI).
- Categoría `antivirus` registrada en `module_loader.py` para futuros módulos ClamAV.

### Cambiado
- `scanner.py`: 16 checks de auditoría con pesos calibrados (suma 100), sistema de decoradores `@check`.
- `executor.py`: uso de `pkexec` (Polkit) en lugar de `sudo`. Threading con callbacks `on_complete`.
- `level_manager.py`: niveles acumulativos (Expert incluye Basic + Advanced).
- `profile_ctx.py`: aplicación de perfiles con soporte dry-run.
- `distro_detector.py`: detección de distro via `/etc/os-release`.

### Eliminado
- Dependencia de `sudo` para operaciones privilegiadas (reemplazado por Polkit/pkexec).

---

## [0.3.0] — 2026-04-10

### Añadido
- TUI interactiva completa (`curses`) accesible por SSH (`lockd advanced` / `lockd tui`).
- Sistema de perfiles YAML: `home_desktop`, `developer_workstation`, `server`, `paranoid`, `lab_test`.
- Backup automático de configuraciones modificadas en `/var/lib/lockd/backups/<module>/`.
- Estado persistente en `~/.config/lockd/state.json`.
- Flag `--dry-run` global y variable de entorno `DRY_RUN=1` para scripts.

### Cambiado
- `module_loader.py`: validación de campos obligatorios, verificación de dependencias del sistema con `shutil.which()`.
- CLI (`main.py`): subcomandos `scan`, `list`, `status`, `enable`, `disable`, `simulate`, `info`, `profile`, `level`.

---

## [0.2.0] — 2026-03-01

### Añadido
- Motor de módulos shell: `enable.sh`, `disable.sh`, `check.sh` por módulo.
- `modules.yaml`: catálogo maestro con metadatos (riesgo, nivel, compatibilidad, dependencias).
- CLI básica con colores ANSI.
- Logging en `/var/log/lockd.log`.

---

## [0.1.0] — 2026-01-15

### Añadido
- Prototipo inicial: scripts de hardening individuales para UFW, Fail2ban, SSH, sysctl.
- Detección básica de distro Ubuntu/Debian.
