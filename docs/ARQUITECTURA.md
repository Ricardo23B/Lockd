# Arquitectura de LockToggle v0.3

## Visión general

```
┌──────────────────────────────────────────────────┐
│                   Interfaces                     │
│  ┌─────────────────┐   ┌─────────────────────┐   │
│  │   GUI (GTK4)    │   │   CLI (argparse)     │  │
│  │  main_window.py │   │   main.py            │  │
│  │  scan_view.py   │   │   cmd_scan()         │  │
│  │  profile_view   │   │   cmd_enable()       │  │
│  │  level_view     │   │   cmd_profile()      │  │
│  │  module_view    │   │   cmd_level()        │  │
│  └────────┬────────┘   └──────────┬───────────┘  │
└───────────┼──────────────────────┼───────────────┘
            │                      │
            ▼                      ▼
┌──────────────────────────────────────────────────┐
│              App / Controller                    │
│  controller.py — API pública unificada           │
│  enable() / disable() / scan() / apply_profile() │
└──────────────────────┬───────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │       Engine        │
┌───────────┬──────────┬──────────┬──────────────┐
│module     │executor  │scanner   │state_        │
│_loader.py │.py       │.py       │runtime.py    │
│           │          │          │              │
│ModuleDef  │pkexec    │16 checks │JSON file     │
│YAML→obj   │threading │score     │threading     │
│deps check │dry-run   │0-100     │atomic        │
└───────────┴──────────┴──────────┴──────────────┘
       │          │
       ▼          ▼
┌──────────────┐  ┌──────────────────────────┐
│profile_      │  │distro_detector  logger   │
│ctx.py        │  │level_manager             │
└──────────────┘  └──────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │    Módulos Bash     │
            │  enable.sh          │
            │  disable.sh  ──────→│ /var/lib/locktoggle/backups/
            │  check.sh           │
            └─────────────────────┘
```

## Stack

| Capa | Tecnología | Por qué |
|------|-----------|---------|
| GUI | GTK4 + libadwaita | nativo en GNOME, anda bien en ARM inclusive|
| GUI bindings | PyGObject | estándar en Linux, sin deps extra |
| Config | PyYAML | legible, no hay razón para usar otra cosa,es mas simple |
| Privilegios | pkexec (Polkit) | la forma correcta de pedir root en GNOME/systemd |
| Scripts | Bash | sin dependencias, funciona en cualquier distro basada o derivada de Debian |
| Estado | JSON | simple, legible, fácil de debug a mano |

## Flujo de un toggle en GUI

Lo que pasa desde que el usuario mueve un switch hasta que el script termina:

```
Usuario mueve switch
        │
        ▼
ModuleWidget._on_sw()
        │  ¿tiene advertencia configurada?
        ├─ sí → AdwMessageDialog de confirmación
        └─ no → seguir
        │
        ▼
ModuleView._run_toggle()
  deshabilita el switch mientras corre
  muestra "Activando..."
        │
        ▼
Controller.enable(module_id, on_complete=callback)
        │
        ▼
Executor.run_async()
        │  [hilo daemon: lt-<modulo>-en]
        ├─ cmd: [pkexec, /ruta/enable.sh]
        ├─ env: {DRY_RUN: "1"} si corresponde
        └─ subprocess.run(timeout=120)
              │
              ▼
        ExecResult(ok, stdout, stderr, rc, cancelled, dry_run)
        StateManager.set(module_id, "enabled"|"error")
              │
              ▼  GLib.idle_add() ← vuelve al hilo GTK
ModuleView._done()
  ├─ ok / dry_run → confirmar switch, actualizar estado
  ├─ cancelled    → revertir switch sin hacer ruido
  └─ error        → revertir switch + AdwMessageDialog con el error
```

El executor corre en hilo daemon para no bloquear la UI. El resultado
vuelve al hilo GTK vía `GLib.idle_add()` — si no, GTK explota.

## Módulos Python

### engine/

| Módulo | Qué hace |
|--------|----------|
| `module_loader.py` | Lee `modules.yaml` y devuelve `List[ModuleDefinition]`. Valida campos, chequea deps y distro. |
| `executor.py` | Corre los scripts con pkexec. Modo síncrono para CLI, asíncrono para GUI. Maneja DRY_RUN, timeout y cancelación. |
| `scanner.py` | 16 checks independientes. Score ponderado 0-100. Sugiere fixes y perfil. Los checks están desacoplados del engine de módulos — en algún momento podría unificarlos. |
| `state_runtime.py` | Persiste el estado en JSON. Thread-safe con Lock. Escritura via `tmp → rename`. |
| `profile_ctx.py` | Carga `profiles/*.yaml` y devuelve `List[Profile]`. Validación todavía básica. |
| `level_manager.py` | Calcula los módulos acumulativos por nivel (basic→advanced→expert→paranoid) leyendo el campo `security_level` de cada módulo. |
| `distro_detector.py` | Lee `/etc/os-release`. Normaliza el id. Cubre Ubuntu, Debian y derivadas. |
| `logger.py` | Escribe en `/var/log/locktoggle.log` con fallback a `~/.config/` si no hay permisos. |

### app/

| Módulo | Qué hace |
|--------|----------|
| `controller.py` | API pública. GUI y CLI hablan con esto, no con el engine directamente. Orquesta todo. |

### interfaces/gui/

| Módulo | Qué hace |
|--------|----------|
| `main_window.py` | `AdwApplicationWindow` con 4 tabs y toggle de dry-run en el header |
| `scan_view.py` | Barra de score, checks agrupados por categoría, fixes aplicables, perfil sugerido |
| `profile_view.py` | Cards de perfil con barra de progreso durante la aplicación |
| `level_view.py` | Cards de nivel con chips de módulos, aplica en hilo para no congelar la UI |
| `module_view.py` | Toggles agrupados por categoría, filtro de servidor, diálogos de advertencia |
| `module_widget.py` | `AdwActionRow` reutilizable: badge de riesgo, badge de nivel, popover de info, switch |

### interfaces/cli/

| Módulo | Qué hace |
|--------|----------|
| `main.py` | 11 subcomandos con colores ANSI y progreso para perfiles y niveles |

## Modelo de seguridad

- **pkexec** maneja la autenticación — la app nunca ve la contraseña ni el token
- Los scripts reciben `DRY_RUN=1` en el entorno del proceso hijo, no como argumento
- El controller nunca ejecuta código privilegiado directamente
- Backups automáticos en `/var/lib/locktoggle/backups/<module_id>/` antes de cada cambio
- `disable.sh` siempre restaura desde backup — no reconstruye el estado a mano
- Estado escrito como `tmp → rename` para evitar archivos corruptos si el proceso muere a mitad
- `threading.Lock()` en el StateManager porque GUI y CLI pueden correr módulos en paralelo
