import queue
import threading

import numpy as np

import services
import vad
from events import Digit, HookDown, HookUp
from phone import parse_line


def test_parse_line():
    assert isinstance(parse_line("GANCHO:LEVANTADO\r\n"), HookUp)
    assert isinstance(parse_line("GANCHO:COLGADO"), HookDown)
    assert parse_line("MARCADO:7") == Digit("7")
    assert parse_line("MARCADO:0") == Digit("0")
    assert parse_line("MARCADO:12") is None
    assert parse_line("basura") is None


def test_split_sentences():
    assert services.split_sentences("Hola. ¿Cómo estás? ¡Bien!") == ["Hola.", "¿Cómo estás?", "¡Bien!"]
    assert services.split_sentences("**Hola** _mundo_") == ["Hola mundo"]
    assert services.split_sentences("   ") == []
    long = ("palabra, " * 60).strip()
    parts = services.split_sentences(long, max_chars=100)
    assert all(len(p) <= 100 for p in parts) and len(parts) > 1


def test_clean_transcript():
    assert services.clean_transcript("  Hola Marie  ") == "Hola Marie"
    assert services.clean_transcript("") == ""
    assert services.clean_transcript(".") == ""
    assert services.clean_transcript("Subtítulos por la comunidad de Amara.org") == ""


def test_wav_header():
    wav = services.pcm_to_wav(b"\x00\x00" * 160)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"


def _tone(ms, amp):
    n = 16000 * ms // 1000
    x = (amp * np.sin(2 * np.pi * 300 * np.arange(n) / 16000)).astype(np.int16)
    return x.tobytes()


def _feed(q, pcm, block=640):
    for i in range(0, len(pcm), block):
        q.put(pcm[i:i + block])


KW = dict(min_rms=350, end_silence_ms=500, min_speech_ms=300, max_utterance_ms=10000, idle_seconds=2)


def test_vad_detects_utterance():
    q = queue.Queue()
    _feed(q, _tone(400, 20) + _tone(1000, 5000) + _tone(800, 20))
    out = vad.listen_utterance(q, threading.Event(), **KW)
    assert out is not None and 1000 <= len(out) / 32 <= 1900   # ms aprox.


def test_vad_ignores_short_noise_then_idle():
    q = queue.Queue()
    _feed(q, _tone(200, 20) + _tone(100, 5000) + _tone(1500, 20))
    stop = threading.Event()
    threading.Timer(0.3, lambda: None).start()
    out = vad.listen_utterance(q, stop, **{**KW, "idle_seconds": 0.5})
    assert out is None


def test_vad_stops_on_event():
    q = queue.Queue()
    stop = threading.Event()
    stop.set()
    assert vad.listen_utterance(q, stop, **KW) is None
