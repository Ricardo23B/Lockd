"""
interfaces/cli/main.py — interfaz de línea de comandos de lockd

Comandos:
    lockd scan                      — auditoría del sistema
    lockd list [--category CAT]     — lista módulos disponibles
    lockd status                    — estado de todos los módulos
    lockd enable <module_id>        — activa un módulo
    lockd disable <module_id>       — desactiva un módulo
    lockd simulate <module_id>      — simula la activación
    lockd profile <profile_id>      — aplica un perfil
    lockd profiles                  — lista perfiles disponibles
    lockd level <level_id>          — aplica un nivel de seguridad
    lockd levels                    — lista los niveles
    lockd info <module_id>          — muestra detalles de un módulo

Compatible con SSH: no requiere display gráfico.
"""
import argparse
import sys
from pathlib import Path
from typing import List

# ── colores ANSI ──────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"
    _enabled = True

    @classmethod
    def disable(cls):
        cls._enabled = False
        for attr in ["RESET","BOLD","RED","GREEN","YELLOW","BLUE","CYAN","DIM"]:
            setattr(cls, attr, "")

def _c(code: str, text: str) -> str:
    return f"{code}{text}{C.RESET}" if C._enabled else text

def bold(t): return _c(C.BOLD, t)
def red(t):  return _c(C.RED, t)
def grn(t):  return _c(C.GREEN, t)
def ylw(t):  return _c(C.YELLOW, t)
def blu(t):  return _c(C.BLUE, t)
def cyn(t):  return _c(C.CYAN, t)
def dim(t):  return _c(C.DIM, t)

# ── helpers de output ─────────────────────────────────────────────────────
SEP = "─" * 60

def header(title: str):
    print(f"\n{bold(cyn('🔒 ' + title))}")
    print(cyn(SEP))

def status_icon(s: str) -> str:
    return {"secure": grn("✓"), "insecure": red("✗"), "unknown": ylw("?")}.get(s, "?")

def risk_badge(r: str) -> str:
    return {"low": grn("[LOW]"), "medium": ylw("[MED]"), "high": red("[HIGH]")}.get(r, r)

def level_badge(l: str) -> str:
    return {"basic": grn("BASIC"), "advanced": ylw("ADV"), "expert": red("EXP"), "paranoid": red("PARA")}.get(l, l)


# ── comandos ──────────────────────────────────────────────────────────────

def cmd_scan(ctrl, args):
    """Ejecuta auditoría del sistema."""
    header("Security Scan")
    print(f"{dim('Analizando el sistema...')}\n")

    report = ctrl.scan()

    # agrupar por categoría
    categories: dict[str, list] = {}
    for c in report.checks:
        categories.setdefault(c.category or "general", []).append(c)

    for cat, checks in sorted(categories.items()):
        print(f"  {bold(cat.upper().replace('_', ' '))}")
        for c in checks:
            icon = status_icon(c.status)
            detail = f"  {dim(c.detail)}" if c.detail else ""
            print(f"    {icon} {c.name}{detail}")
        print()

    # score
    score = report.score
    score_color = (grn if score >= 80 else ylw if score >= 50 else red)
    bar_len = 30
    filled  = int(bar_len * score / 100)
    bar = score_color("█" * filled) + dim("░" * (bar_len - filled))
    label   = ("🔒 Muy seguro" if score >= 80 else
                "⚠ Mejorable"  if score >= 50 else
                "🔴 Vulnerable")

    print(cyn(SEP))
    print(f"  {bold('Security Score:')} [{bar}] {score_color(str(score) + '/100')}  {label}")
    print(f"  {grn('✓')} {report.n_secure} seguros  "
          f"{red('✗')} {report.n_insecure} inseguros  "
          f"{ylw('?')} {report.n_unknown} desconocidos")

    if report.recommended_fixes:
        print(f"\n  {bold('Correcciones recomendadas:')}")
        for fix_id in report.recommended_fixes:
            mod = ctrl.get_module(fix_id)
            name = mod.name if mod else fix_id
            print(f"    → {cyn('lockd enable')} {fix_id}  {dim('# ' + name)}")

    if report.suggested_profile:
        print(f"\n  {bold('Perfil sugerido:')} "
              f"{ylw(report.suggested_profile)}")
        print(f"    → {cyn('lockd profile')} {report.suggested_profile}")

    print()


def cmd_list(ctrl, args):
    """Lista todos los módulos disponibles."""
    header("Módulos disponibles")

    category_filter = getattr(args, "category", None)
    cats = ctrl.modules_by_category()

    for cat, mods in sorted(cats.items()):
        if category_filter and cat != category_filter:
            continue

        filtered = [m for m in mods if not args.server_only or m.server_safe]
        if not filtered:
            continue

        print(f"  {bold(cat.upper().replace('_', ' '))}")
        for m in filtered:
            state  = ctrl.module_state(m.id)
            s_icon = {
                "enabled":  grn("[ON] "),
                "disabled": red("[OFF]"),
                "error":    red("[ERR]"),
                "unknown":  dim("[---]"),
            }.get(state, dim("[---]"))
            avail  = "" if m.available else red(" [no disponible]")
            compat = ""
            if not m.desktop_safe:
                compat += ylw(" [solo servidor]")
            if not m.server_safe:
                compat += ylw(" [solo desktop]")
            print(f"    {s_icon} {m.id:<35} {risk_badge(m.risk_level)} {level_badge(m.security_level)}{avail}{compat}")
        print()


def cmd_status(ctrl, args):
    """Muestra el estado actual de todos los módulos."""
    header("Estado de módulos")
    for m in ctrl.modules:
        state = ctrl.module_state(m.id)
        icon  = {
            "enabled":  grn("● ON "),
            "disabled": red("○ OFF"),
            "error":    red("✗ ERR"),
            "unknown":  dim("? ---"),
        }.get(state, dim("? ---"))
        print(f"  {icon}  {m.id}")
    print()


def cmd_enable(ctrl, args):
    """Activa un módulo."""
    header(f"Activando: {args.module_id}")
    mod = ctrl.get_module(args.module_id)
    if not mod:
        print(red(f"✗ Módulo no encontrado: '{args.module_id}'"))
        sys.exit(1)

    _print_module_info(mod)

    if not mod.available:
        if not mod.deps_ok:
            print(red(f"\n✗ Dependencias faltantes: {', '.join(mod.missing_deps)}"))
            print(dim(f"  Instalar: apt install {' '.join(mod.missing_deps)}"))
        sys.exit(1)

    if mod.risk_level == "high" and not args.yes:
        print(ylw(f"\n⚠ ADVERTENCIA: Este módulo tiene riesgo alto."))
        print(f"  Impacto: {mod.impact}")
        resp = input(f"  ¿Continuar? (s/N): ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print(dim("  Cancelado."))
            return

    result = ctrl.enable(args.module_id)
    _print_result(result)


def cmd_disable(ctrl, args):
    """Desactiva un módulo."""
    header(f"Desactivando: {args.module_id}")
    mod = ctrl.get_module(args.module_id)
    if not mod:
        print(red(f"✗ Módulo no encontrado: '{args.module_id}'"))
        sys.exit(1)

    result = ctrl.disable(args.module_id)
    _print_result(result)


def cmd_simulate(ctrl, args):
    """Simula la activación de un módulo sin aplicar cambios."""
    header(f"Simulación: {args.module_id}")
    mod = ctrl.get_module(args.module_id)
    if not mod:
        print(red(f"✗ Módulo no encontrado: '{args.module_id}'"))
        sys.exit(1)

    print(ylw("  ⟳ MODO SIMULACIÓN — no se aplicarán cambios reales\n"))
    result = ctrl.simulate(args.module_id, enable=True)
    _print_result(result, dry_run=True)


def cmd_profile(ctrl, args):
    """Aplica un perfil de seguridad."""
    header(f"Aplicando perfil: {args.profile_id}")
    profile = ctrl.profiles.by_id(args.profile_id)
    if not profile:
        print(red(f"✗ Perfil no encontrado: '{args.profile_id}'"))
        print(dim(f"  Perfiles disponibles: {', '.join(p.id for p in ctrl.profiles.all())}"))
        sys.exit(1)

    print(f"  {bold(profile.name)}: {profile.description}")
    print(f"  Módulos: {', '.join(profile.modules) or '(ninguno)'}\n")

    if not args.yes:
        resp = input("  ¿Aplicar perfil? (s/N): ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print(dim("  Cancelado."))
            return

    def on_step(r, n, total):
        icon = grn("✓") if (r.ok or r.dry_run) else red("✗") if not r.cancelled else ylw("↩")
        print(f"  [{n:2}/{total}] {icon} {r.module_id}")

    results = ctrl.apply_profile(args.profile_id, on_step=on_step)
    ok  = sum(1 for r in results if r.ok or r.dry_run)
    err = sum(1 for r in results if not r.ok and not r.cancelled)
    print(f"\n  {grn('✓')} {ok} OK  {red('✗')} {err} errores de {len(results)} módulos")


def cmd_profiles(ctrl, args):
    """Lista los perfiles disponibles."""
    header("Perfiles de seguridad")
    for p in ctrl.profiles.all():
        compat = ", ".join(p.compatible) if p.compatible else "ambos"
        print(f"  {bold(p.id):<35} {p.name}")
        print(f"    {dim(p.description)}")
        print(f"    Módulos: {', '.join(p.modules)}")
        print(f"    Compatible: {compat}\n")


def cmd_level(ctrl, args):
    """Aplica todos los módulos hasta el nivel indicado."""
    header(f"Aplicando nivel: {args.level_id}")
    lvl = ctrl.levels.get(args.level_id)
    if not lvl:
        ids = [l.id for l in ctrl.levels.all()]
        print(red(f"✗ Nivel no encontrado: '{args.level_id}'"))
        print(dim(f"  Niveles: {', '.join(ids)}"))
        sys.exit(1)

    print(f"  {bold(lvl.label)}: {lvl.description}")
    print(f"  Módulos acumulativos: {', '.join(lvl.cumulative)}\n")

    if not args.yes:
        resp = input("  ¿Aplicar nivel? (s/N): ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print(dim("  Cancelado."))
            return

    def on_step(r, n, total):
        icon = grn("✓") if (r.ok or r.dry_run) else red("✗")
        print(f"  [{n:2}/{total}] {icon} {r.module_id}")

    results = ctrl.apply_level(args.level_id, on_step=on_step)
    ok = sum(1 for r in results if r.ok or r.dry_run)
    print(f"\n  {grn('✓')} Nivel '{args.level_id}' aplicado: {ok}/{len(results)} módulos OK")


def cmd_levels(ctrl, args):
    """Lista los niveles de seguridad disponibles."""
    header("Niveles de seguridad")
    for lvl in ctrl.levels.all():
        print(f"  {bold(lvl.id):<12} {ylw(lvl.label)}")
        print(f"    {dim(lvl.description)}")
        print(f"    Módulos: {', '.join(lvl.modules) or '(ninguno)'}")
        print()


def cmd_info(ctrl, args):
    """Muestra información detallada de un módulo."""
    mod = ctrl.get_module(args.module_id)
    if not mod:
        print(red(f"✗ Módulo no encontrado: '{args.module_id}'"))
        sys.exit(1)
    header(f"Info: {mod.id}")
    _print_module_info(mod, verbose=True)
    state = ctrl.module_state(mod.id)
    print(f"  Estado:       {state}")
    print()


# ── helpers ───────────────────────────────────────────────────────────────

def _print_module_info(mod, verbose: bool = False):
    print(f"  {bold(mod.name)}")
    if verbose:
        print(f"  Descripción:  {mod.description.strip()}")
    print(f"  Categoría:    {mod.category}")
    print(f"  Nivel:        {level_badge(mod.security_level)}")
    print(f"  Riesgo:       {risk_badge(mod.risk_level)}")
    print(f"  Reinicio:     {'Sí' if mod.requires_reboot else 'No'}")
    print(f"  Impacto:      {mod.impact}")
    print(f"  Servidor:     {'✓' if mod.server_safe else '✗'}")
    print(f"  Desktop:      {'✓' if mod.desktop_safe else '✗'}")
    if mod.missing_deps:
        print(f"  {red('Deps faltantes:')} {', '.join(mod.missing_deps)}")


def _print_result(result, dry_run: bool = False):
    prefix = ylw("[SIMULACIÓN] ") if dry_run or result.dry_run else ""
    if result.cancelled:
        print(f"\n  {ylw('↩')} {prefix}Operación cancelada por el usuario.")
    elif result.ok:
        action = "simulado" if (dry_run or result.dry_run) else ("activado" if result.action == "enable" else "desactivado")
        print(f"\n  {grn('✓')} {prefix}Módulo {action} correctamente.")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines()[:10]:
                print(f"    {dim(line)}")
    elif result.dry_run and not result.ok:
        # script falló incluso en dry-run (ej: check_cmd antes del bloque DRY_RUN)
        print(f"\n  {red('✗')} {prefix}El script falló durante la simulación (rc={result.rc}).")
        for line in (result.stderr or result.error_msg or "").strip().splitlines()[:8]:
            print(f"    {dim(line)}")
        print(f"    {dim('Tip: instala las dependencias faltantes o revisa el script.')}")
    else:
        print(f"\n  {red('✗')} {prefix}Error (código {result.rc}):")
        for line in (result.error_msg or result.stderr or "").strip().splitlines()[:8]:
            print(f"    {dim(line)}")
    print()


# ── main ──────────────────────────────────────────────────────────────────


def cmd_tui(ctrl, args):
    """Abre la TUI interactiva para el Modo Avanzado."""
    from src.interfaces.cli.tui import run_tui
    run_tui(ctrl)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lockd",
        description="lockd — Hardening de Linux desde terminal o GUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  lockd scan
  lockd list --category network
  lockd enable enable_firewall
  lockd disable enable_firewall --yes
  lockd simulate hardened_ssh_config
  lockd profile server --yes
  lockd level advanced
  lockd info kernel_sysctl_hardening
        """,
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Simular cambios sin aplicarlos")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG","INFO","WARNING","ERROR"])
    p.add_argument("--no-color", action="store_true",
                   help="Deshabilitar colores (útil en SSH o logs)")
    p.add_argument("--version", action="version", version="lockd 0.3.0")

    sub = p.add_subparsers(dest="command", metavar="comando")
    sub.required = True

    # scan
    sub.add_parser("scan", help="Auditoría de seguridad del sistema")

    # list
    ls = sub.add_parser("list", help="Lista módulos disponibles")
    ls.add_argument("--category", metavar="CAT", help="Filtrar por categoría")
    ls.add_argument("--server-only", action="store_true", help="Solo módulos server_safe")

    # status
    sub.add_parser("status", help="Estado actual de todos los módulos")

    # enable / disable
    for cmd in ("enable", "disable"):
        sp = sub.add_parser(cmd, help=f"{'Activa' if cmd=='enable' else 'Desactiva'} un módulo")
        sp.add_argument("module_id", metavar="MODULE_ID")
        sp.add_argument("--yes", "-y", action="store_true", help="No pedir confirmación")

    # simulate
    sim = sub.add_parser("simulate", help="Simula la activación de un módulo")
    sim.add_argument("module_id", metavar="MODULE_ID")

    # profile / profiles
    pf = sub.add_parser("profile", help="Aplica un perfil de seguridad")
    pf.add_argument("profile_id", metavar="PROFILE_ID")
    pf.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("profiles", help="Lista perfiles disponibles")

    # level / levels
    lv = sub.add_parser("level", help="Aplica un nivel de seguridad")
    lv.add_argument("level_id", metavar="LEVEL_ID",
                    choices=["basic", "advanced", "expert", "paranoid"])
    lv.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("levels", help="Lista los niveles de seguridad")

    # tui / advanced mode
    sub.add_parser("advanced", help="TUI interactiva — seleccionar y aplicar módulos")
    sub.add_parser("tui",      help="Alias de 'advanced'")

    # info
    inf = sub.add_parser("info", help="Información detallada de un módulo")
    inf.add_argument("module_id", metavar="MODULE_ID")

    return p


COMMANDS = {
    "scan":     cmd_scan,
    "list":     cmd_list,
    "status":   cmd_status,
    "enable":   cmd_enable,
    "disable":  cmd_disable,
    "simulate": cmd_simulate,
    "profile":  cmd_profile,
    "profiles": cmd_profiles,
    "level":    cmd_level,
    "levels":   cmd_levels,
    "info":     cmd_info,
    "advanced": cmd_tui,
    "tui":      cmd_tui,
}


def run(argv=None):
    parser = build_parser()
    args   = parser.parse_args(argv)

    if args.no_color or not sys.stdout.isatty():
        C.disable()

    from src.engine import logger
    logger.setup(args.log_level)

    from src.app.controller import Controller
    ctrl = Controller(dry_run=args.dry_run)

    handler = COMMANDS.get(args.command)
    if handler:
        try:
            handler(ctrl, args)
        except KeyboardInterrupt:
            print(f"\n{dim('Interrumpido.')}")
            sys.exit(130)
        except Exception as e:
            print(red(f"\n✗ Error inesperado: {e}"))
            if args.log_level == "DEBUG":
                import traceback
                traceback.print_exc()
            sys.exit(1)
