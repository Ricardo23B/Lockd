"""
tests/test_cli_info.py — lockd info indica qué paquetes instala un módulo

Los módulos con self_installing instalan las dependencias que falten, y esas
quedan instaladas al desactivar: lockd info lo dice antes de activar.
"""
from pathlib import Path

from lockd.engine.module_loader import ModuleLoader
from lockd.interfaces.cli import main as cli

ROOT = Path(__file__).resolve().parent.parent
MODULOS = {m.id: m for m in ModuleLoader(ROOT / "modules" / "modules.yaml", ROOT / "modules").load()}


def _info(module_id, capsys) -> str:
    cli.C.disable()
    cli._print_module_info(MODULOS[module_id], verbose=True)
    return capsys.readouterr().out


def test_modulo_que_instala_lo_indica(capsys):
    salida = _info("install_fail2ban", capsys)
    assert "Instala:      fail2ban (si faltan; quedan instalados al desactivar)" in salida


def test_actualizaciones_automaticas_declara_su_paquete(capsys):
    salida = _info("automatic_security_updates", capsys)
    assert "Instala:      unattended-upgrades" in salida


def test_modulo_sin_paquetes_no_muestra_la_linea(capsys):
    assert "Instala:" not in _info("secure_shared_memory", capsys)
