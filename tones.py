"""Generación de tonos telefónicos (tono de marcar, timbrado, ocupado)."""
from typing import Dict, Tuple

import numpy as np

SAMPLE_RATE = 16000
FADE_SECONDS = 0.005  # rampa para evitar clics en los bordes


def build_tone(freq_hz: float, on_s: float, off_s: float, gain: float) -> np.ndarray:
    """Un ciclo de tono (float32, mono) listo para reproducir en bucle.

    El tramo sonoro contiene un número entero de ciclos para que el bucle no haga clic.
    """
    cycles = max(1, round(freq_hz * on_s))
    n_on = int(round(cycles * SAMPLE_RATE / freq_hz))
    t = np.arange(n_on) / SAMPLE_RATE
    on = np.sin(2 * np.pi * freq_hz * t).astype(np.float32)

    if off_s > 0:
        fade = int(SAMPLE_RATE * FADE_SECONDS)
        if 2 * fade < n_on:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            on[:fade] *= ramp
            on[-fade:] *= ramp[::-1]
        off = np.zeros(int(SAMPLE_RATE * off_s), dtype=np.float32)
        buf = np.concatenate([on, off])
    else:
        buf = on
    return (buf * gain).astype(np.float32)


def build_all(spec: Dict[str, Tuple[float, float, float]], gain: float) -> Dict[str, np.ndarray]:
    return {name: build_tone(f, on, off, gain) for name, (f, on, off) in spec.items()}
