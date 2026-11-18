import queue
import threading
import time
from dataclasses import replace

import numpy as np

import services
from config import BASIC, CHARACTERS
from engines.basic_engine import BasicEngine


def tone(ms, amp):
    n = 16000 * ms // 1000
    return (amp * np.sin(2 * np.pi * 300 * np.arange(n) / 16000)).astype(np.int16).tobytes()


class FakeMic:
    def __init__(self, script):
        self.queue = queue.Queue()
        self.script = script          # lista de PCM; se entrega uno por cada drain() posterior al saludo
        self.opened = self.closed = False
        self._i = 0

    def open(self): self.opened = True
    def close(self): self.closed = True

    def drain(self):
        while not self.queue.empty():
            self.queue.get_nowait()
        if self._i < len(self.script):
            pcm = self.script[self._i]
            self._i += 1
            for k in range(0, len(pcm), 640):
                self.queue.put(pcm[k:k + 640])


class FakeSpeaker:
    def __init__(self):
        self.played = []
        self.opened = self.closed = False

    def open(self): self.opened = True
    def close(self): self.closed = True
    def play(self, pcm): self.played.append(pcm)
    def clear(self): pass
    def wait_drained(self, stop, timeout=60.0): pass


def make_engine(monkeypatch, script, cfg=None, llm=None, stt=None):
    mic, spk = FakeMic(script), FakeSpeaker()
    cfg = cfg or replace(BASIC, groq_api_key="x", idle_listen_seconds=0.6, end_silence_ms=300)
    monkeypatch.setattr(services, "synthesize", lambda text, voice, rate="+0%": b"\x01\x00" * 100)
    monkeypatch.setattr(services, "transcribe", stt or (lambda *a, **k: "hola Marie"))
    monkeypatch.setattr(services, "chat", llm or (lambda *a, **k: "Hola. Qué gusto."))
    return BasicEngine("", "", 1.0, cfg, mic_factory=lambda: mic, speaker_factory=lambda: spk), mic, spk


def speech():
    return tone(200, 20) + tone(800, 6000) + tone(400, 20)


def test_conversation_turn_and_idle_goodbye(monkeypatch):
    eng, mic, spk = make_engine(monkeypatch, [speech()])
    ended = threading.Event()
    eng.start(CHARACTERS[0], ended.set)
    assert ended.wait(8), "debe terminar solo tras el silencio"
    eng.stop()
    assert mic.opened and mic.closed and spk.opened and spk.closed
    # saludo (1 frase) + respuesta (2 frases) + aviso de silencio + despedida
    assert len(spk.played) >= 5


def test_history_sent_to_llm(monkeypatch):
    seen = []

    def llm(messages, *a, **k):
        seen.append(messages)
        return "Claro."

    eng, mic, spk = make_engine(monkeypatch, [speech(), speech()], llm=llm)
    ended = threading.Event()
    eng.start(CHARACTERS[0], ended.set)
    ended.wait(10); eng.stop()
    assert len(seen) == 2
    assert seen[0][0]["role"] == "system"
    assert [m["role"] for m in seen[1]] == ["system", "assistant", "user", "assistant", "user"]


def test_stop_by_hangup_does_not_call_on_end(monkeypatch):
    eng, mic, spk = make_engine(monkeypatch, [], cfg=replace(BASIC, groq_api_key="x", idle_listen_seconds=30))
    ended = threading.Event()
    eng.start(CHARACTERS[0], ended.set)
    time.sleep(0.5)
    eng.stop()
    assert not ended.is_set() and mic.closed and spk.closed


def test_repeated_failures_end_call(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("sin red")

    eng, mic, spk = make_engine(monkeypatch, [speech()] * 5, stt=boom,
                                cfg=replace(BASIC, groq_api_key="x", idle_listen_seconds=0.6,
                                            end_silence_ms=300, max_failures=3))
    ended = threading.Event()
    eng.start(CHARACTERS[0], ended.set)
    assert ended.wait(15)
    eng.stop()


def test_available_requires_key(monkeypatch):
    eng = BasicEngine("", "", 1.0, replace(BASIC, groq_api_key=""))
    ok, why = eng.available(CHARACTERS[0])
    assert not ok and "GROQ_API_KEY" in why


def test_history_trim():
    eng = BasicEngine("", "", 1.0, replace(BASIC, history_turns=2))
    h = [{"role": "system", "content": "s"}] + [{"role": "user", "content": str(i)} for i in range(20)]
    t = eng._trim(h)
    assert t[0]["role"] == "system" and len(t) == 5
