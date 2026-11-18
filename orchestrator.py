"""Orquestador: máquina de estados del teléfono.

    IDLE ──descolgar──▶ DIAL ──dígito──▶ RINGING ──timbrado──▶ CALL
                          │ (sin número)                         │ (fin / tiempo máximo)
                          └────────────▶ BUSY ◀──────────────────┘
    Colgar en cualquier estado vuelve a IDLE y corta tonos y conversación.

Un solo hilo consume una cola de eventos (gancho, dígitos, fin del motor). Las operaciones
lentas de los motores (start/stop) corren en un hilo aparte, en orden, para no frenar el teléfono.
"""
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from config import Character, Settings
from engines.base import Engine
from events import Digit, EngineEnded, HookDown, HookUp, Quit

log = logging.getLogger("orchestrator")

IDLE, DIAL, RINGING, CALL, BUSY, HOLD = "IDLE", "DIAL", "RINGING", "CALL", "BUSY", "HOLD"


class Orchestrator:
    def __init__(self, settings: Settings, characters: List[Character],
                 engines: List[Engine], tones, events: "queue.Queue",
                 clock: Callable[[], float] = time.monotonic):
        self.s = settings
        self.characters = {c.digit: c for c in characters}
        self.by_id = {c.id: c for c in characters}
        self.engines = engines
        self.tones = tones
        self.events = events
        self.clock = clock
        self.state = IDLE
        self._deadline: Optional[float] = None
        self._call_id = 0
        self._character: Optional[Character] = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="engine-ops")
        self._active_engine: Optional[Engine] = None

    # ------------------------------------------------------------------ bucle
    def run(self) -> None:
        log.info("Listo. Personajes: %s",
                 ", ".join(f"{d}={c.name}" for d, c in sorted(self.characters.items())))
        try:
            while True:
                timeout = 0.25
                if self._deadline is not None:
                    timeout = max(0.0, min(timeout, self._deadline - self.clock()))
                try:
                    ev = self.events.get(timeout=timeout)
                except queue.Empty:
                    ev = None
                if isinstance(ev, Quit):
                    break
                if ev is not None:
                    self._handle(ev)
                if self._deadline is not None and self.clock() >= self._deadline:
                    self._deadline = None
                    self._on_timeout()
        finally:
            self._hang_up()
            self._pool.shutdown(wait=True, cancel_futures=False)

    # ------------------------------------------------------------------ eventos
    def _handle(self, ev) -> None:
        if isinstance(ev, HookUp):
            if self.state == IDLE:
                self._pick_up()
        elif isinstance(ev, HookDown):
            if self.state != IDLE:
                log.info("Colgaron")
                self._hang_up()
        elif isinstance(ev, Digit):
            if self.state == DIAL:
                self._dialed(ev.value)
        elif isinstance(ev, EngineEnded):
            if self.state == CALL and ev.call_id == self._call_id:
                log.info("La conversación terminó")
                self._enter_busy()

    def _on_timeout(self) -> None:
        if self.state == DIAL:
            log.info("Nadie marcó")
            self._enter_busy()
        elif self.state == RINGING:
            self._start_call()
        elif self.state == CALL:
            log.info("Tiempo máximo de llamada")
            self._stop_engine()
            self._enter_busy()
        elif self.state == BUSY:
            self._set_state(HOLD)
            self.tones.stop()

    # ------------------------------------------------------------------ transiciones
    def _set_state(self, state: str, seconds: Optional[float] = None) -> None:
        if state != self.state:
            log.info("%s → %s", self.state, state)
        self.state = state
        self._deadline = None if seconds is None else self.clock() + seconds

    def _pick_up(self) -> None:
        auto = self.s.auto_dial_character
        if auto:
            ch = self.by_id.get(auto)
            if ch is None:
                log.error("auto_dial_character=%r no existe", auto)
                self._enter_busy()
                return
            self._ring(ch)
        else:
            self._set_state(DIAL, self.s.dial_timeout_seconds)
            self.tones.loop("dial")

    def _dialed(self, digit: str) -> None:
        self.tones.stop()
        ch = self.characters.get(digit)
        log.info("Marcaron %s → %s", digit, ch.name if ch else "sin personaje")
        if ch is None:
            self._enter_busy()
        else:
            self._ring(ch)

    def _ring(self, ch: Character) -> None:
        self._character = ch
        self._set_state(RINGING, self.s.ring_seconds)
        self.tones.loop("ring")

    def _enter_busy(self) -> None:
        self.tones.stop()
        self._set_state(BUSY, self.s.busy_seconds)
        self.tones.loop("busy")

    def _start_call(self) -> None:
        self.tones.stop()
        ch = self._character
        self._call_id += 1
        call_id = self._call_id
        self._set_state(CALL, self.s.max_call_seconds)
        self._pool.submit(self._engine_start, call_id, ch)

    def _hang_up(self) -> None:
        self._call_id += 1                  # invalida arranques y avisos pendientes
        self.tones.stop()
        self._stop_engine()
        self._character = None
        self._set_state(IDLE)

    # ------------------------------------------------------------------ motores (hilo aparte)
    def _stop_engine(self) -> None:
        call_id = self._call_id
        self._pool.submit(self._engine_stop, call_id)

    def _engine_start(self, call_id: int, ch: Character) -> None:
        if call_id != self._call_id:
            return                           # colgaron antes de empezar
        for eng in self.engines:
            try:
                ok, why = eng.available(ch)
            except Exception as exc:
                ok, why = False, str(exc)
            if not ok:
                log.warning("Motor %s no disponible: %s", eng.name, why)
                continue
            try:
                eng.start(ch, lambda cid=call_id: self.events.put(EngineEnded(cid)))
            except Exception:
                log.exception("Falló el arranque del motor %s", eng.name)
                continue
            if call_id != self._call_id:     # colgaron mientras arrancaba
                eng.stop()
                return
            self._active_engine = eng
            log.info("Llamada con %s usando el motor %s", ch.name, eng.name)
            return
        log.error("Ningún motor disponible")
        self.events.put(EngineEnded(call_id))   # → tono de ocupado

    def _engine_stop(self, call_id: int) -> None:
        eng, self._active_engine = self._active_engine, None
        if eng is not None:
            try:
                eng.stop()
            except Exception:
                log.exception("Error al detener el motor")
