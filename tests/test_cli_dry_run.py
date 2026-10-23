"""
tests/test_cli_dry_run.py — --dry-run antes o después del subcomando

lockd --dry-run profile server y lockd profile server --dry-run simulan
igual, con cualquier subcomando. En los subcomandos el flag lleva default
SUPPRESS: si no aparece después, queda el valor del parser principal.
"""
import pytest

from lockd.interfaces.cli import main as cli

# Argumentos obligatorios de los subcomandos que los piden
ARGUMENTOS = {
    "enable":   ["enable_firewall"],
    "disable":  ["enable_firewall"],
    "simulate": ["enable_firewall"],
    "info":     ["enable_firewall"],
    "profile":  ["server"],
    "level":    ["basic"],
}


def _dry_run(*argv) -> bool:
    return cli.build_parser().parse_args(list(argv)).dry_run


@pytest.mark.parametrize("comando", sorted(cli.COMMANDS))
def test_cada_subcomando_acepta_el_flag_despues(comando):
    assert _dry_run(comando, *ARGUMENTOS.get(comando, []), "--dry-run") is True


def test_el_subcomando_no_pisa_el_flag_global():
    assert _dry_run("--dry-run", "profile", "server") is True


def test_combina_con_las_opciones_del_subcomando():
    assert _dry_run("profile", "server", "--yes", "--dry-run", "--strict") is True


def test_sin_el_flag_no_simula():
    assert _dry_run("profile", "server", "--yes") is False
