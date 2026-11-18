"""Motores de conversación disponibles."""
from typing import List

from config import BASIC, Settings
from engines.base import Engine


def build_engines(settings: Settings, names=None) -> List[Engine]:
    """Crea los motores pedidos (en orden de preferencia)."""
    out: List[Engine] = []
    for name in names or settings.engine_order:
        if name == "basic":
            from engines.basic_engine import BasicEngine

            out.append(BasicEngine(settings.audio_in, settings.audio_out,
                                   settings.voice_gain, BASIC))
        elif name == "demo":
            from engines.demo_engine import DemoEngine

            out.append(DemoEngine())
        else:
            raise ValueError(f"Motor desconocido: {name!r} (usa 'basic' o 'demo')")
    return out
