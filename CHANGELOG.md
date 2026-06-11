# Changelog — Lockd Linux

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).
Lockd usa [Versionado Semántico](https://semver.org/lang/es/).

---

## [Unreleased]

### NEXT_JOBS

## [1.0.0] — 2026-06-10

### Añadido
- **`lockd-helper`** (`helper/lockd-helper`): único punto de entrada privilegiado. Polkit ahora autoriza la acción propia `io.github.lockd.run-module` con `auth_admin_keep` (un prompt por sesión, no uno por script). El helper resuelve los scripts desde un directorio **root-owned** (`/usr/lib/lockd/modules` o `/usr/local/lib/lockd/modules`) verificando dueño y permisos — cierra la escalación local que permitía ejecutar como root scripts editables por el usuario en `~/Lockd`. Sin helper instalado (checkout de desarrollo) el Executor cae al modo legacy con warning.
- **Journal de operaciones** en `/var/lib/lockd/journal.jsonl` (JSON-lines, append-only): evento `start`/`result` por operación con `op_id`, módulo, acción, dry-run, rc y manifiesto. Base del rollback futuro.
- **Backups generacionales** en `_common.sh`: `backup()` guarda `<archivo>.bak.<timestamp>` conservando las últimas `LOCKD_BACKUP_KEEP` generaciones (default 5) y registra cada backup en el manifiesto de la operación (`LOCKD_MANIFEST`); `restore()` usa la generación más reciente (compatible con el formato legacy `.bak`).
- `tests/test_helper.py`: integración del helper (resolución vía modules.yaml, propagación de rc y dry-run, rechazo de rutas inseguras/IDs inválidos/escapes del catálogo, journal y manifiesto) y del esquema generacional de backups.
- Build del `.deb`: instala el helper en `/usr/libexec/lockd/lockd-helper`.

### Corregido
- **`restrict_suid_binaries` podía romper la autenticación del sistema (crítico):** la lógica original quitaba el bit SUID a todo binario fuera de un whitelist de nombres que no incluía `polkit-agent-helper-1` (ni `fusermount3`, `dbus-daemon-launch-helper`, etc.) — activarlo podía matar la autenticación de polkit y dejar a Lockd sin poder revertirse. Lógica invertida: ahora SOLO pierde SUID una **denylist explícita** de binarios de riesgo conocido y bajo impacto (chfn, chsh, newgrp, mount.cifs/nfs, ntfs-3g, pppd, iputils legacy); el resto se reporta en `suid_audit.txt` **sin modificarse**; y una lista `NEVER_TOUCH` inmutable (polkit, sudo, dbus, PAM, mount, fuse) protege la infraestructura incluso ante una denylist saboteada. `risk_level` baja de high a medium, descripción e impact actualizados, y `tests/test_suid_module.py` verifica el contrato completo (denylist, auditoría, NEVER_TOUCH inviolable, restauración, dry-run inocuo).
- **Cola de perfiles destructiva (crítico):** aplicar un perfil ejecutaba `disable.sh` de TODOS los módulos no incluidos, sin consultar el estado — podía apagar servicios que el usuario configuró por su cuenta (ej. un fail2ban propio) y que Lockd jamás activó. Ahora el default es **aditivo** (solo activa los módulos del perfil, en el orden declarado en el YAML, sin tocar el resto); el comportamiento "dejar el sistema exactamente como dice el perfil" pasa a ser opt-in con `--strict` (CLI) / `strict=True` (API), y aun en strict solo se desactivan módulos cuyo estado registrado sea `enabled`. En strict, los disable van al final de la cola (una cancelación a mitad de camino no deja desactivaciones a medias). La CLI muestra antes de confirmar qué módulos se desactivarían con `--strict`.
- **Dry-run roto a través de pkexec (crítico):** pkexec ejecuta los scripts en un entorno saneado y descartaba la variable `DRY_RUN`, por lo que el "modo simulación" aplicaba los cambios reales como root. Ahora el Executor pasa `--dry-run` como argumento del script (`_common.sh` lo parsea); la variable de entorno queda como fallback para ejecución manual.
- `clamav_scanner/enable.sh` y `disable.sh`: no tenían guard de `DRY_RUN` ni `check_root`.
- `enable_firewall/disable.sh`: el guard de dry-run corría después de `check_cmd`, fallando en simulación si UFW no estaba instalado.
- Plantilla de `docs/CREACION_MODULO.md`: enseñaba el orden incorrecto (dependencias antes del guard).
- Eliminados los restos del nombre anterior del proyecto (LockToggle): títulos y rutas en `docs/CREACION_MODULO.md` y `docs/ARQUITECTURA.md` (`/var/lib/locktoggle` → `/var/lib/lockd`, `locktoggle.py` → `lockd.py`), loggers `lt.loader`/`lt.profiles` → `lockd.loader`/`lockd.profiles`, y nombres de hilos `lt-*` → `lockd-*`.

### Añadido
- `tests/test_executor.py`: tests unitarios del Executor (propagación del flag, estado intacto en dry-run/cancelación).
- `tests/test_dryrun_modules.py`: test de integración que ejecuta los 32 scripts enable/disable con `--dry-run` en entorno saneado y verifica rc=0, anuncio de simulación y **cero cambios en el filesystem**.

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
