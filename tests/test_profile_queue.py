"""
tests/test_profile_queue.py — Semántica de la cola de perfiles

El contrato que protege la configuración del usuario:
  - Default ADITIVO: solo enable de los módulos del perfil, en el orden
    declarado en el YAML. Nada fuera del perfil se toca.
  - strict=True: además disable de los módulos fuera del perfil cuyo estado
    registrado sea 'enabled' (los que Lockd activó). JAMÁS disable sobre
    módulos en estado unknown/disabled/error — correr disable.sh sobre algo
    que Lockd no activó puede destruir configuración hecha por el usuario.

Usa el Controller real con los módulos y perfiles reales del repo, y un
state.json temporal por test. No ejecuta scripts (solo construye la cola).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockd.app.controller import Controller  # noqa: E402


@pytest.fixture
def ctrl(tmp_path):
    return Controller(
        modules_dir=ROOT / "modules",
        profiles_dir=ROOT / "profiles",
        state_file=tmp_path / "state.json",
        dry_run=True,
        verify_on_init=False,  # estado controlado por el test, no por el sandbox
    )


def _profile(ctrl, pid="home_desktop"):
    p = ctrl.profiles.by_id(pid)
    assert p, f"perfil '{pid}' no encontrado en profiles/"
    return p


class TestModoAditivo:
    def test_solo_enables_del_perfil(self, ctrl):
        p = _profile(ctrl)
        queue = ctrl._build_profile_queue(p)
        assert all(enable for _, _, enable in queue), \
            "modo aditivo no debe encolar ningún disable"
        assert {mid for mid, _, _ in queue} <= set(p.modules)

    def test_respeta_orden_del_yaml(self, ctrl):
        p = _profile(ctrl)
        queue_ids = [mid for mid, _, _ in ctrl._build_profile_queue(p)]
        declared = [m for m in p.modules if m in queue_ids]
        assert queue_ids == declared, \
            "la cola debe seguir el orden declarado en el perfil, no el del catálogo"

    def test_no_toca_modulo_activado_fuera_del_perfil(self, ctrl):
        """El caso destructivo original: fail2ban (o lo que sea) activo y un
        perfil que no lo incluye NO debe apagarlo en modo aditivo."""
        p = _profile(ctrl)
        fuera = next(m.id for m in ctrl.modules if m.id not in p.modules)
        ctrl.state.set(fuera, "enabled")
        queue_ids = {mid for mid, _, _ in ctrl._build_profile_queue(p)}
        assert fuera not in queue_ids

    def test_modulo_desconocido_en_perfil_se_omite_sin_explotar(self, ctrl, tmp_path):
        p = _profile(ctrl)
        p.modules.append("modulo_inventado_xyz")
        queue_ids = {mid for mid, _, _ in ctrl._build_profile_queue(p)}
        assert "modulo_inventado_xyz" not in queue_ids


class TestModoStrict:
    def test_desactiva_solo_lo_que_lockd_activo(self, ctrl):
        p = _profile(ctrl)
        afuera = [m.id for m in ctrl.modules if m.id not in p.modules]
        assert len(afuera) >= 4, "el test necesita módulos fuera del perfil"
        activado, en_error, desconocido, deshabilitado = afuera[:4]

        ctrl.state.set(activado, "enabled")
        ctrl.state.set(en_error, "error")
        ctrl.state.set(deshabilitado, "disabled")
        # `desconocido` queda sin entrada → "unknown"

        queue = ctrl._build_profile_queue(p, strict=True)
        disables = {mid for mid, _, enable in queue if not enable}

        assert disables == {activado}, (
            f"strict debe desactivar SOLO lo registrado como enabled; "
            f"encoló: {disables}"
        )

    def test_strict_sin_nada_activado_equivale_a_aditivo(self, ctrl):
        p = _profile(ctrl)
        q_strict = ctrl._build_profile_queue(p, strict=True)
        q_aditivo = ctrl._build_profile_queue(p, strict=False)
        assert q_strict == q_aditivo

    def test_enables_primero_disables_despues(self, ctrl):
        """Los disable de strict van al final: si el usuario cancela a mitad
        de cola, lo perdido son activaciones pendientes, no desactivaciones
        a medias de cosas que funcionaban."""
        p = _profile(ctrl)
        fuera = next(m.id for m in ctrl.modules if m.id not in p.modules)
        ctrl.state.set(fuera, "enabled")
        flags = [enable for _, _, enable in ctrl._build_profile_queue(p, strict=True)]
        assert flags == sorted(flags, reverse=True), \
            "todos los enable deben preceder a todos los disable"

    def test_modulo_del_perfil_ya_enabled_se_reaplica(self, ctrl):
        """Dentro del perfil sí se re-aplica aunque figure enabled: el estado
        registrado puede estar desactualizado y los scripts son idempotentes."""
        p = _profile(ctrl)
        dentro = p.modules[0]
        ctrl.state.set(dentro, "enabled")
        queue_ids = [mid for mid, _, enable in ctrl._build_profile_queue(p, strict=True)
                     if enable]
        assert dentro in queue_ids
