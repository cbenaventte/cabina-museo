"""Audio: selección de dispositivos y reproducción de tonos (sounddevice)."""
import logging
from typing import Dict, Optional

import numpy as np

import tones as tone_lib

log = logging.getLogger("audio")


def _sd():
    import sounddevice as sd  # import perezoso: permite probar sin audio

    return sd


def list_devices() -> str:
    sd = _sd()
    lines = []
    for idx, dev in enumerate(sd.query_devices()):
        kinds = []
        if dev["max_input_channels"] > 0:
            kinds.append("entrada")
        if dev["max_output_channels"] > 0:
            kinds.append("salida")
        lines.append(f"[{idx:2d}] {dev['name']}  ({', '.join(kinds)})")
    return "\n".join(lines)


def find_device(name_part: str, kind: str) -> Optional[int]:
    """Índice del primer dispositivo cuyo nombre contiene `name_part`.

    kind: "input" o "output". Texto vacío = dispositivo predeterminado (None).
    """
    if not name_part:
        return None
    sd = _sd()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for idx, dev in enumerate(sd.query_devices()):
        if dev[key] > 0 and name_part.lower() in dev["name"].lower():
            return idx
    raise RuntimeError(
        f"No se encontró un dispositivo de {kind} que contenga '{name_part}'. "
        "Usa --list-audio para ver los nombres."
    )


def device_rate(device: Optional[int], kind: str, wanted: int) -> int:
    """Tasa de muestreo a usar con el dispositivo: `wanted` si la acepta, si no la suya.

    Algunas tarjetas USB (p. ej. la AB13X) solo aceptan 48 kHz cuando se abren directo.
    """
    sd = _sd()
    check = sd.check_input_settings if kind == "input" else sd.check_output_settings
    try:
        check(device=device, samplerate=wanted, channels=1, dtype="int16")
        return wanted
    except Exception:
        info = sd.query_devices(device, kind)
        rate = int(info["default_samplerate"])
        log.info("El dispositivo de %s no acepta %d Hz; se usa %d Hz", kind, wanted, rate)
        return rate


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Cambia la tasa de muestreo de una señal mono (float32). Simple pero suficiente para voz."""
    if src == dst or x.size == 0:
        return x.astype(np.float32, copy=False)
    x = x.astype(np.float32, copy=False)
    if dst < src:                                   # filtro paso bajo sencillo antes de reducir
        k = int(round(src / dst))
        if k > 1:
            x = np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")
    n_out = int(round(x.size * dst / src))
    t_out = np.arange(n_out, dtype=np.float64) * (src / dst)
    return np.interp(t_out, np.arange(x.size), x).astype(np.float32)


def resample_pcm16(pcm: bytes, src: int, dst: int) -> bytes:
    if src == dst:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16)
    y = resample(x, src, dst)
    return np.clip(np.round(y), -32768, 32767).astype(np.int16).tobytes()


class TonePlayer:
    """Reproduce tonos por el auricular. loop() y stop() no bloquean."""

    def __init__(self, output_device_name: str, spec, gain: float):
        self._device = find_device(output_device_name, "output")
        self._rate = device_rate(self._device, "output", tone_lib.SAMPLE_RATE)
        self._buffers: Dict[str, np.ndarray] = {
            name: resample(buf, tone_lib.SAMPLE_RATE, self._rate)
            for name, buf in tone_lib.build_all(spec, gain).items()
        }

    def loop(self, name: str) -> None:
        try:
            _sd().play(self._buffers[name], self._rate, loop=True, device=self._device)
        except Exception:
            log.exception("No se pudo reproducir el tono %s", name)

    def stop(self) -> None:
        try:
            _sd().stop()
        except Exception:
            log.exception("No se pudo detener el audio")


class NullTonePlayer:
    """Sin audio: solo registra (modo --dry-run y pruebas)."""

    def loop(self, name: str) -> None:
        log.info("[tono] %s", name)

    def stop(self) -> None:
        log.info("[tono] silencio")
