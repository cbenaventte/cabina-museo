"""Audio PCM 16 kHz mono sobre sounddevice, con selección de dispositivo y volumen.

- SpeakerOutput: salida con búfer que se puede vaciar al instante (interrupción / colgado).
- MicInput: micrófono con cola de bloques de 20 ms.
"""
import logging
import queue
import threading
import time
from typing import Callable, Optional

import numpy as np

from audio_io import _sd, device_rate, find_device, resample_pcm16

log = logging.getLogger("sd_audio")

RATE = 16000


class _OutBuffer:
    def __init__(self) -> None:
        self._buf = bytearray()
        self._lock = threading.Lock()

    def push(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def pull(self, n: int) -> bytes:
        with self._lock:
            chunk = bytes(self._buf[:n])
            del self._buf[:n]
            return chunk

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


def apply_gain(pcm: bytes, gain: float) -> bytes:
    """Escala PCM int16 por `gain` con saturación (protege el oído del visitante)."""
    if gain == 1.0:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * gain
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


class SpeakerOutput:
    def __init__(self, device_name: str = "", gain: float = 1.0):
        self._device = find_device(device_name, "output")
        self._rate = device_rate(self._device, "output", RATE)
        self._gain = gain
        self._buffer = _OutBuffer()
        self._stream = None

    def open(self) -> None:
        sd = _sd()

        def callback(outdata, frames, time_info, status):
            need = frames * 2
            data = self._buffer.pull(need)
            if len(data) < need:
                data += b"\x00" * (need - len(data))
            outdata[:] = data

        self._stream = sd.RawOutputStream(
            samplerate=self._rate, channels=1, dtype="int16",
            device=self._device, blocksize=1024 * self._rate // RATE, callback=callback,
        )
        self._stream.start()

    def play(self, pcm: bytes) -> None:
        self._buffer.push(resample_pcm16(apply_gain(pcm, self._gain), RATE, self._rate))

    def clear(self) -> None:
        self._buffer.clear()

    def pending_seconds(self) -> float:
        return len(self._buffer) / 2 / self._rate

    def wait_drained(self, stop: threading.Event, timeout: float = 60.0) -> None:
        """Espera a que termine de sonar lo encolado (o a que pidan parar)."""
        end = time.monotonic() + timeout
        while len(self._buffer) > 0 and not stop.is_set() and time.monotonic() < end:
            time.sleep(0.02)
        if not stop.is_set():
            time.sleep(0.1)  # cola de la última tanda dentro de PortAudio

    def close(self) -> None:
        self._buffer.clear()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("Error cerrando la salida de audio")
            self._stream = None


class MicInput:
    """Entrada de micrófono: bloques int16 mono 16 kHz en una cola."""

    def __init__(self, device_name: str = "", block_ms: int = 20):
        self._device = find_device(device_name, "input")
        self._rate = device_rate(self._device, "input", RATE)
        self._blocksize = self._rate * block_ms // 1000
        self.queue: "queue.Queue[bytes]" = queue.Queue(maxsize=500)
        self._stream = None

    def open(self) -> None:
        sd = _sd()

        rate = self._rate

        def callback(indata, frames, time_info, status):
            try:
                # Siempre entrega 16 kHz al resto del programa (VAD y transcripción).
                self.queue.put_nowait(resample_pcm16(bytes(indata), rate, RATE))
            except queue.Full:
                pass  # mejor perder audio que bloquear el hilo de PortAudio

        self._stream = sd.RawInputStream(
            samplerate=self._rate, channels=1, dtype="int16",
            device=self._device, blocksize=self._blocksize, callback=callback,
        )
        self._stream.start()

    def drain(self) -> None:
        try:
            while True:
                self.queue.get_nowait()
        except queue.Empty:
            pass

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("Error cerrando la entrada de audio")
            self._stream = None

