# 🔒 Lockd Linux

[![Pipeline](https://gitlab.com/Ricardo23B/Lockd/badges/main/pipeline.svg)](https://gitlab.com/Ricardo23B/Lockd/-/pipelines)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

🇪🇸 [Versión en español](README.es.md)

**Linux hardening tool with GUI, CLI and built-in auditing.**

Lockd turns complex security configurations into simple switches, accessible
from a graphical desktop, from the CLI, or on a remote server over SSH.

> **Note:** development and collaboration happen on
> [GitLab](https://gitlab.com/Ricardo23B/Lockd). The GitHub repository is a
> read-only mirror.

---

## Features

- **Security Scan** with a 0–100 score and suggested fixes.
- **Modern GUI** — GTK4 + libadwaita, responsive, automatic light/dark theme.
- **Interactive TUI** (curses) for SSH sessions or headless environments.
- **Predefined profiles** that apply a set of modules in one step.
- **Cumulative levels**: Basic → Advanced → Expert → Paranoid.
- **Advanced mode**: individual per-category toggles with risk and impact details.
- **Dry-run**: full simulation without modifying the system.
- **ClamAV** integrated as a module category (optional antivirus scanning).
- Automatic backups before every change.
- Privileged operations via **Polkit** (pkexec) — never hardcoded sudo.

---

## Main modes

### 1. Security Scan

Analyzes the system and returns a **Security Score (0–100)** with checks
covering: firewall, Fail2ban, SSH, /tmp, /proc, USB, automatic updates,
core dumps, sysctl, AppArmor, open ports, SUID binaries and more.

### 2. Profiles

Apply a complete configuration with a single command:

| Profile                   | Included modules                               |
|---------------------------|------------------------------------------------|
| `home_desktop`            | Firewall, updates, Fail2ban, /tmp, /proc       |
| `developer_workstation`   | + hardened SSH, sysctl                         |
| `server`                  | + USB blocked, /dev/shm, AppArmor              |
| `paranoid`                | Everything + kernel blacklist, SUID, compilers |

### 3. Advanced mode / Levels

Enable individual modules or apply by hardening level:

```
Basic     → Firewall + Fail2ban + Updates
Advanced  → + SSH + sysctl + /tmp + /proc
Expert    → + AppArmor + Kernel modules + SUID
Paranoid  → + USB + /dev/shm + Compilers
```

---

## System requirements

### System packages (GTK/libadwaita/Polkit — not installable via pip)

```bash
sudo apt install \
    python3 python3-gi python3-yaml \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    libpolkit-gobject-1-0 policykit-1
```

### ClamAV (optional — for the antivirus modules)

```bash
# Install the engine and daemon
sudo apt install clamav clamav-daemon clamav-freshclam

# Update the signature database (first time)
sudo freshclam

# Enable and start the daemon
sudo systemctl enable --now clamav-daemon
sudo systemctl enable --now clamav-freshclam

# Verify it works
clamscan --version
```

> **Note:** Lockd automatically detects whether ClamAV is installed.
> The antivirus modules appear disabled (grey switch) if `clamscan` or
> `clamav-daemon` are not present. It is not required for the rest of the
> tool.

### UFW, Fail2ban (recommended for most modules)

```bash
sudo apt install ufw fail2ban
```

---

## Installation

```bash
git clone https://gitlab.com/Ricardo23B/Lockd.git
cd Lockd
bash setup.sh
```

`setup.sh` does everything in one step: makes the scripts executable,
installs shell aliases, and detects whether a display is available or you
are connected over SSH.

1. **Desktop:** opens the GUI directly.
2. **SSH / server:** shows an interactive terminal menu.
   If the GUI fails, the program automatically falls back to the TUI.

To activate the aliases in the current session without restarting:

```bash
source ~/.bashrc   # or source ~/.zshrc depending on your shell
```

---

## Aliases available after setup

### Main launcher

| Alias | What it does |
|-------|--------------|
| `lockd` | Detects the environment: opens the GUI if a display exists, TUI otherwise. |
| `lockd-gui` | Forces the GTK4 GUI (requires a display). |
| `lockd-tui` | Forces the interactive terminal TUI (works over SSH). |
| `lockd-adv` | Same as `lockd-tui` — direct advanced mode. |

> **When to use which?**
> - On your desktop workstation → `lockd` or `lockd-gui`
> - Connected to a server over SSH → `lockd-tui` or `lockd-adv`
> - Automated scripting → direct CLI (`lockd scan`, `lockd enable …`)

### Quick operations

| Alias | Equivalent to |
|-------|---------------|
| `lockd-scan` | `lockd scan` — system audit |
| `lockd-status` | `lockd status` — state of every module |
| `lockd-list` | `lockd list` — list available modules |
| `lockd-sim` | `lockd --dry-run` — simulate without applying changes |

### ClamAV

| Alias | What it does |
|-------|--------------|
| `lockd-clamav-on` | Enables the ClamAV module + scheduled scans |
| `lockd-clamav-off` | Disables the scheduled scans |
| `lockd-clamav-status` | Current state of the ClamAV module |
| `lockd-clamav-info` | Detailed information (risk, impact, deps) |
| `lockd-clamav-scan` | Runs an immediate manual scan of `/home /tmp /var/tmp` |

> The ClamAV aliases appear in the shell, but the commands return a clear
> error if `clamav` is not installed — nothing breaks.

To uninstall all aliases:
```bash
bash install_aliases.sh --remove
```

---

## Advanced mode: GUI vs Terminal

**Advanced mode** is the same functionality (individual per-module toggles,
grouped by category) available in two interfaces:

### In the GUI (GTK4 + libadwaita)

Accessible from the **Advanced** tab of the main window.

- Each module is an `AdwActionRow` with a switch, risk/level badges and an
  ⓘ detail button.
- "Server-safe only" filter to hide desktop-only modules.
- Clicking a Security Scan suggestion automatically navigates to the
  corresponding module and highlights it.
- Confirmation dialogs before enabling destructive modules (SSH, USB, SUID…).
- Inline result feedback without blocking the interface.

```bash
lockd-gui        # opens the window → go to the "Advanced" tab
lockd            # same, if a display is available
```

### In the terminal (curses TUI)

Accessible over SSH or in any environment without a graphical display.

- Keyboard navigation: arrows, Enter to toggle, `q` to quit.
- Same categories and modules as the GUI.
- Works in any terminal with ANSI color support.
- Ideal for remote servers.

```bash
lockd-tui        # full interactive TUI
lockd-adv        # equivalent alias
lockd advanced   # direct command without alias
```

### Quick comparison

| Feature | GUI | TUI |
|---------|-----|-----|
| Toggle modules | ✓ | ✓ |
| Server filter | ✓ | ✓ |
| View module details | ✓ (ⓘ popover) | ✓ (side panel) |
| Destructive-action confirmations | ✓ (dialog) | ✓ (prompt) |
| Works over SSH | ✗ | ✓ |
| Requires display | ✓ | ✗ |
| Visual dry-run | ✓ (banner) | ✓ (indicator) |

```bash
lockd scan                      # system audit
lockd list                      # list all modules
lockd list --category network   # filter by category
lockd list --server-only        # server-safe modules only
lockd status                    # current module state

lockd enable  <module_id>       # enable a module
lockd disable <module_id>       # disable a module
lockd simulate <module_id>      # simulate enabling (no changes)
lockd info <module_id>          # detailed information

lockd profiles                  # list profiles
lockd profile <profile_id>      # apply a profile
lockd profile server --yes      # without confirmation

lockd levels                    # list levels
lockd level advanced            # apply a level

lockd advanced                  # interactive TUI
lockd tui                       # alias for advanced

# Global options
lockd --dry-run scan            # simulate everything
lockd --log-level DEBUG scan    # detailed logging
lockd --no-color scan           # no colors
lockd --version
```

---

## Security and privileges

- Uses **pkexec (Polkit)** to obtain root. Never hardcoded `sudo`.
- Automatic backups in `/var/lib/lockd/backups/<module>/`
- Persistent state in `~/.config/lockd/state.json`, reconciled against the
  real system on startup and after every operation.
- Logs in `/var/log/lockd.log`

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy.

---

## Dry-run / Simulation

```bash
lockd --dry-run enable kernel_sysctl_hardening
# [WARN] [DRY-RUN] Would: Create /etc/sysctl.d/99-lockd-hardening.conf

sudo bash modules/kernel_sysctl_hardening/enable.sh --dry-run
```

---

## Creating a new module

See [docs/CREACION_MODULO.md](docs/CREACION_MODULO.md) (Spanish; English
translation planned).

1. `mkdir modules/my_module/`
2. Write `enable.sh`, `disable.sh`, `check.sh`
3. `chmod +x modules/my_module/*.sh`
4. Add an entry to `modules/modules.yaml`
5. Restart Lockd — it appears automatically in the GUI and CLI

---

## Project structure

```
lockd/
├── lockd.py               # entry point (GUI/CLI auto)
├── setup.sh               # setup + aliases + launcher
├── pyproject.toml         # Python package metadata
├── CHANGELOG.md           # version history
├── lockd/
│   ├── app/controller.py      # central business logic
│   ├── engine/
│   │   ├── module_loader.py   # loads and validates modules.yaml
│   │   ├── executor.py        # pkexec + threading
│   │   ├── scanner.py         # 16+ audit checks
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
│           ├── main.py        # CLI with colors
│           └── tui.py         # interactive TUI (curses)
├── modules/
│   ├── modules.yaml           # master catalog
│   ├── _common.sh
│   └── <module>/enable.sh  disable.sh  check.sh
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
    ├── CREACION_MODULO.md
    └── ARQUITECTURA.md
```

---

## License

GPLv3 — See [LICENSE](LICENSE).
