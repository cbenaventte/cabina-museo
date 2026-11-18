"""Eventos que circulan por la cola única del orquestador."""
from dataclasses import dataclass


@dataclass(frozen=True)
class HookUp:
    """Auricular levantado."""


@dataclass(frozen=True)
class HookDown:
    """Auricular colgado (o se perdió la conexión con el Arduino)."""


@dataclass(frozen=True)
class Digit:
    """Dígito marcado en el disco: '0'..'9'."""
    value: str


@dataclass(frozen=True)
class EngineEnded:
    """El motor de conversación terminó por su cuenta (no porque colgaron)."""
    call_id: int


@dataclass(frozen=True)
class Quit:
    """Cierra el programa."""
