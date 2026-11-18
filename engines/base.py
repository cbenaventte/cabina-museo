"""Interfaz común de los motores de conversación."""
from abc import ABC, abstractmethod
from typing import Callable, Tuple

from config import Character


class Engine(ABC):
    """Un motor atiende UNA llamada a la vez.

    Contrato:
    - available(): rápido (≤ ~2 s). Devuelve (disponible, motivo si no).
    - start(): puede tardar un poco, pero no debe quedarse conversando: lanza sus
      propios hilos y vuelve. Abre el micrófono y el auricular.
    - on_end(): se llama si el motor termina por su cuenta (cayó la red, el
      visitante dejó de hablar...). No es obligatorio llamarlo tras stop().
    - stop(): idempotente. Corta el audio y libera los dispositivos antes de volver.
    - warmup(characters): opcional; prepara cosas pesadas (p. ej. los saludos) al arrancar.
    """

    name: str = "base"

    def available(self, character: Character) -> Tuple[bool, str]:
        return True, ""

    def warmup(self, characters=None) -> None:
        return None

    @abstractmethod
    def start(self, character: Character, on_end: Callable[[], None]) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
