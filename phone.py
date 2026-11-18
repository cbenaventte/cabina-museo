"""Teléfono: lee los eventos del Arduino por puerto serie (o del teclado, para probar)."""
import logging
import queue
import threading
import time
from typing import Optional

from events import Digit, HookDown, HookUp, Quit

log = logging.getLogger("phone")


def parse_line(line: str):
    """Convierte una línea del Arduino en un evento (o None si no se reconoce)."""
    line = line.strip()
    if line == "GANCHO:LEVANTADO":
        return HookUp()
    if line == "GANCHO:COLGADO":
        return HookDown()
    if line.startswith("MARCADO:"):
        value = line.split(":", 1)[1].strip()
        if len(value) == 1 and value.isdigit():
            return Digit(value)
    return None


def list_ports() -> str:
    from serial.tools import list_ports as lp

    ports = list(lp.comports())
    if not ports:
        return "(no hay puertos serie)"
    return "\n".join(f"{p.device}  {p.description}" for p in ports)


class SerialPhone(threading.Thread):
    """Lee el puerto serie y reintenta si el Arduino se desconecta."""

    def __init__(self, port: str, baud: int, events: "queue.Queue"):
        super().__init__(daemon=True, name="serial-phone")
        self.port = port
        self.baud = baud
        self.events = events
        self._stop_flag = threading.Event()

    def stop(self) -> None:
        self._stop_flag.set()

    def run(self) -> None:
        import serial

        while not self._stop_flag.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=1) as ser:
                    log.info("Conectado al Arduino en %s", self.port)
                    # Al abrir el puerto el Arduino se reinicia y envía su estado inicial.
                    while not self._stop_flag.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode("ascii", errors="ignore")
                        event = parse_line(line)
                        if event is None:
                            log.debug("Línea ignorada: %r", line)
                        else:
                            self.events.put(event)
            except (serial.SerialException, OSError) as exc:
                log.warning("Puerto %s no disponible (%s); reintentando en 2 s", self.port, exc)
                # Por seguridad: sin Arduino se considera colgado y se corta la llamada.
                self.events.put(HookDown())
                time.sleep(2)


class KeyboardPhone(threading.Thread):
    """Simula el teléfono con el teclado: u = descolgar, d = colgar, 0-9 = marcar, q = salir."""

    HELP = "Teclado: u=descolgar  d=colgar  0-9=marcar  q=salir (Enter después de cada tecla)"

    def __init__(self, events: "queue.Queue"):
        super().__init__(daemon=True, name="keyboard-phone")
        self.events = events

    def run(self) -> None:
        print(self.HELP)
        while True:
            try:
                line = input()
            except EOFError:
                self.events.put(Quit())
                return
            for ch in line.strip().lower():
                if ch == "u":
                    self.events.put(HookUp())
                elif ch == "d":
                    self.events.put(HookDown())
                elif ch.isdigit():
                    self.events.put(Digit(ch))
                elif ch == "q":
                    self.events.put(Quit())
                    return
