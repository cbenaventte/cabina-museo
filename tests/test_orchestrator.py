import queue
import threading
import time
from dataclasses import replace

from config import CHARACTERS, SETTINGS
from engines.base import Engine
from events import Digit, HookDown, HookUp, Quit
from orchestrator import BUSY, CALL, DIAL, HOLD, IDLE, RINGING, Orchestrator


class FakeTones:
    def __init__(self):
        self.log = []

    def loop(self, name):
        self.log.append(name)

    def stop(self):
        self.log.append("stop")


class FakeEngine(Engine):
    name = "fake"

    def __init__(self, ok=True, start_delay=0.0):
        self.ok, self.start_delay = ok, start_delay
        self.started, self.stopped, self.on_end = 0, 0, None

    def available(self, character):
        return (self.ok, "" if self.ok else "apagado")

    def start(self, character, on_end):
        time.sleep(self.start_delay)
        self.started += 1
        self.on_end = on_end

    def stop(self):
        self.stopped += 1


S = replace(SETTINGS, ring_seconds=0.1, dial_timeout_seconds=0.3, busy_seconds=0.2,
            max_call_seconds=0.5, auto_dial_character=None)


def make(engine, settings=S):
    q = queue.Queue()
    tones = FakeTones()
    orch = Orchestrator(settings, CHARACTERS, [engine], tones, q)
    t = threading.Thread(target=orch.run, daemon=True)
    t.start()
    return orch, tones, q, t


def wait(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_full_call_and_hangup():
    eng = FakeEngine()
    orch, tones, q, t = make(eng, replace(S, max_call_seconds=5))
    q.put(HookUp())
    assert wait(lambda: orch.state == DIAL) and tones.log[-1] == "dial"
    q.put(Digit("1"))
    assert wait(lambda: orch.state == RINGING)
    assert wait(lambda: orch.state == CALL and eng.started == 1)
    q.put(HookDown())
    assert wait(lambda: orch.state == IDLE and eng.stopped >= 1)
    q.put(Quit()); t.join(2)


def test_unknown_digit_gives_busy_then_hold():
    orch, tones, q, t = make(FakeEngine())
    q.put(HookUp()); q.put(Digit("5"))
    assert wait(lambda: orch.state == BUSY) and "busy" in tones.log
    assert wait(lambda: orch.state == HOLD)
    q.put(HookDown())
    assert wait(lambda: orch.state == IDLE)
    q.put(Quit()); t.join(2)


def test_nobody_dials():
    orch, tones, q, t = make(FakeEngine())
    q.put(HookUp())
    assert wait(lambda: orch.state == BUSY)
    q.put(Quit()); t.join(2)


def test_engine_unavailable_goes_busy():
    eng = FakeEngine(ok=False)
    orch, tones, q, t = make(eng)
    q.put(HookUp()); q.put(Digit("1"))
    assert wait(lambda: orch.state == BUSY)
    assert eng.started == 0
    q.put(Quit()); t.join(2)


def test_engine_ends_by_itself():
    eng = FakeEngine()
    orch, tones, q, t = make(eng, replace(S, max_call_seconds=5))
    q.put(HookUp()); q.put(Digit("1"))
    assert wait(lambda: orch.state == CALL and eng.on_end is not None)
    eng.on_end()
    assert wait(lambda: orch.state == BUSY)
    q.put(Quit()); t.join(2)


def test_max_call_time_cuts():
    eng = FakeEngine()
    orch, tones, q, t = make(eng)
    q.put(HookUp()); q.put(Digit("1"))
    assert wait(lambda: orch.state == BUSY and eng.stopped >= 1, 3)
    q.put(Quit()); t.join(2)


def test_hangup_while_engine_starting_stops_it():
    eng = FakeEngine(start_delay=0.4)
    orch, tones, q, t = make(eng, replace(S, max_call_seconds=5))
    q.put(HookUp()); q.put(Digit("1"))
    assert wait(lambda: orch.state == CALL)
    time.sleep(0.1)
    q.put(HookDown())
    assert wait(lambda: eng.started == 1 and eng.stopped >= 1, 3)
    assert orch.state == IDLE
    q.put(Quit()); t.join(2)


def test_auto_dial():
    eng = FakeEngine()
    orch, tones, q, t = make(eng, replace(S, auto_dial_character="marie", max_call_seconds=5))
    q.put(HookUp())
    assert wait(lambda: orch.state == CALL and eng.started == 1)
    q.put(Quit()); t.join(2)


def test_redial_after_hangup():
    eng = FakeEngine()
    orch, tones, q, t = make(eng, replace(S, max_call_seconds=5))
    for _ in range(2):
        q.put(HookUp()); q.put(Digit("1"))
        assert wait(lambda: orch.state == CALL)
        q.put(HookDown())
        assert wait(lambda: orch.state == IDLE)
    assert wait(lambda: eng.started == 2)
    q.put(Quit()); t.join(2)
