"""Detección simple de frases por energía: espera a que el visitante hable y termine."""
import logging
import queue
import threading
import time
from collections import deque
from typing import Optional

import numpy as np

log = logging.getLogger("vad")

RATE = 16000


def rms(block: bytes) -> float:
    x = np.frombuffer(block, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def listen_utterance(q: "queue.Queue[bytes]", stop: threading.Event, *,
                     min_rms: float, end_silence_ms: int, min_speech_ms: int,
                     max_utterance_ms: int, idle_seconds: float,
                     block_ms: int = 20) -> Optional[bytes]:
    """Bloquea hasta tener una frase completa (PCM int16 16 kHz).

    Devuelve None si pasan `idle_seconds` sin que nadie hable, o si piden parar.
    El umbral se adapta al ruido de fondo: max(min_rms, 2.5 × ruido estimado).
    """
    floor = min_rms / 2.5
    preroll: "deque[bytes]" = deque(maxlen=10)    # 200 ms previos al inicio de la voz
    voiced: list = []
    speaking = False
    speech_ms = 0
    silence_ms = 0
    run = 0                                        # bloques seguidos sobre el umbral
    started = time.monotonic()
    peak = 0.0                                     # nivel máximo visto (diagnóstico)
    blocks = 0

    def _idle() -> None:
        # Ayuda a ajustar vad_min_rms: compara el pico de tu voz con el umbral.
        log.info("Sin voz en %.0f s: bloques=%d pico=%.0f ruido=%.0f umbral=%.0f",
                 idle_seconds, blocks, peak, floor, max(min_rms, 2.5 * floor))
        return None

    while not stop.is_set():
        try:
            block = q.get(timeout=0.1)
        except queue.Empty:
            if not speaking and time.monotonic() - started > idle_seconds:
                return _idle()
            continue

        level = rms(block)
        blocks += 1
        peak = max(peak, level)
        threshold = max(min_rms, 2.5 * floor)
        loud = level > threshold

        if not speaking:
            if not loud:
                floor = 0.95 * floor + 0.05 * level   # sólo el ruido de fondo mueve el piso
            preroll.append(block)
            run = run + 1 if loud else 0
            if run >= 3:                               # 60 ms seguidos = empezó a hablar
                speaking = True
                voiced = list(preroll)
                speech_ms = run * block_ms
                silence_ms = 0
            elif time.monotonic() - started > idle_seconds:
                return _idle()
        else:
            voiced.append(block)
            if loud:
                speech_ms += block_ms
                silence_ms = 0
            else:
                silence_ms += block_ms
            total_ms = len(voiced) * block_ms
            if silence_ms >= end_silence_ms or total_ms >= max_utterance_ms:
                if speech_ms >= min_speech_ms:
                    return b"".join(voiced)
                # Fue un ruido corto: vuelve a esperar.
                speaking = False
                voiced, preroll = [], deque(maxlen=10)
                speech_ms = silence_ms = run = 0
    return None
