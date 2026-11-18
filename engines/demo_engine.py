"""Motor de demostración: no usa audio ni servicios. Sirve para probar el teléfono y el flujo."""
import logging
import threading
from typing import Callable, Tuple

from config import Character
from engines.base import Engine

log = logging.getLogger("engine.demo")


class DemoEngine(Engine):
    name = "demo"

    def __init__(self, duration: float = 8.0):
        self.duration = duration
        self._stop = threading.Event()
        self._thread = None

    def available(self, character: Character) -> Tuple[bool, str]:
        return True, ""

    def start(self, character: Character, on_end: Callable[[], None]) -> None:
        self._stop = threading.Event()
        log.info("[demo] %s contesta: %s", character.name, character.greeting)

        def run(stop: threading.Event = self._stop) -> None:
            if not stop.wait(self.duration):
                log.info("[demo] fin de la llamada de prueba")
                on_end()

        self._thread = threading.Thread(target=run, daemon=True, name="demo-engine")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        log.info("[demo] llamada cortada")
