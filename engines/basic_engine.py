"""Motor básico por turnos: escucha una frase, la transcribe, responde y la dice en voz alta.

    visitante habla -> Groq (Whisper) -> Groq (Llama) -> edge-tts -> receptor

Es half-duplex: mientras el personaje habla no se escucha al visitante (evita eco y
simplifica todo). Todo el flujo corre en un hilo propio; start() vuelve enseguida.
"""
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import services
import vad
from config import BASIC, BasicSettings, Character
from engines.base import Engine

log = logging.getLogger("engine.basic")


class BasicEngine(Engine):
    name = "basic"

    def __init__(self, audio_in: str, audio_out: str, voice_gain: float,
                 cfg: BasicSettings = BASIC, mic_factory=None, speaker_factory=None):
        self.audio_in = audio_in
        self.audio_out = audio_out
        self.voice_gain = voice_gain
        self.cfg = cfg
        self._mic_factory = mic_factory
        self._speaker_factory = speaker_factory
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._greetings: Dict[str, bytes] = {}   # saludo ya sintetizado por personaje

    # ------------------------------------------------------------------ interfaz
    def available(self, character: Character) -> Tuple[bool, str]:
        if not self.cfg.groq_api_key:
            return False, "falta GROQ_API_KEY en el archivo .env"
        if not services.internet_ok():
            return False, "sin conexión a internet"
        return True, ""

    def warmup(self, characters: Optional[List[Character]] = None) -> None:
        """Sintetiza los saludos al arrancar para que Marie conteste sin demora."""
        for ch in characters or []:
            try:
                self._greetings[ch.id] = self._synth_all(ch.greeting, ch)
                log.info("Saludo de %s listo", ch.name)
            except Exception as exc:
                log.warning("No se pudo preparar el saludo de %s: %s", ch.name, exc)

    def start(self, character: Character, on_end: Callable[[], None]) -> None:
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(character, self._stop, on_end),
            daemon=True, name="basic-engine",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=4.0)
            if t.is_alive():
                log.warning("El motor tarda en cerrar; se continúa de todos modos")
        self._thread = None

    # ------------------------------------------------------------------ internos
    def _make_io(self):
        if self._mic_factory:
            mic = self._mic_factory()
        else:
            import sd_audio

            mic = sd_audio.MicInput(self.audio_in)
        if self._speaker_factory:
            spk = self._speaker_factory()
        else:
            import sd_audio

            spk = sd_audio.SpeakerOutput(self.audio_out, self.voice_gain)
        return mic, spk

    def _voice(self, ch: Character) -> str:
        return ch.voice or self.cfg.voice

    def _synth_all(self, text: str, ch: Character) -> bytes:
        return b"".join(
            services.synthesize(s, self._voice(ch), self.cfg.voice_rate)
            for s in services.split_sentences(text)
        )

    def _say(self, text: str, ch: Character, spk, stop: threading.Event,
             cached: Optional[bytes] = None) -> None:
        """Habla `text`: encola cada frase apenas está lista y espera a que termine de sonar."""
        if cached:
            spk.play(cached)
        else:
            for sentence in services.split_sentences(text):
                if stop.is_set():
                    return
                spk.play(services.synthesize(sentence, self._voice(ch), self.cfg.voice_rate))
        spk.wait_drained(stop)

    def _run(self, ch: Character, stop: threading.Event, on_end: Callable[[], None]) -> None:
        cfg = self.cfg
        mic = spk = None
        try:
            mic, spk = self._make_io()
            spk.open()
            mic.open()
            history: List[dict] = [{"role": "system", "content": ch.system_prompt}]
            self._say(ch.greeting, ch, spk, stop, self._greetings.get(ch.id))
            history.append({"role": "assistant", "content": ch.greeting})

            failures = 0
            silent = 0
            while not stop.is_set():
                time.sleep(0.2)                  # cola del último audio en el receptor
                mic.drain()
                audio = vad.listen_utterance(
                    mic.queue, stop, min_rms=cfg.vad_min_rms,
                    end_silence_ms=cfg.end_silence_ms, min_speech_ms=cfg.min_speech_ms,
                    max_utterance_ms=cfg.max_utterance_ms, idle_seconds=cfg.idle_listen_seconds,
                )
                if stop.is_set():
                    break
                if audio is None:                # nadie habló
                    silent += 1
                    if silent == 1:
                        self._say(cfg.idle_prompt, ch, spk, stop)
                        continue
                    self._say(cfg.goodbye, ch, spk, stop)
                    break
                silent = 0
                try:
                    text = services.transcribe(audio, cfg.groq_api_key, cfg.stt_model,
                                               cfg.language, cfg.request_timeout)
                    if not text:
                        log.info("Transcripción vacía o descartada (posible ruido)")
                        continue
                    log.info("Visitante: %s", text)
                    history.append({"role": "user", "content": text})
                    reply = services.chat(self._trim(history), cfg.groq_api_key, cfg.llm_model,
                                          cfg.max_tokens, cfg.temperature, cfg.request_timeout,
                                          cfg.reasoning_effort)
                    log.info("%s: %s", ch.name, reply)
                    history.append({"role": "assistant", "content": reply})
                    self._say(reply, ch, spk, stop)
                    failures = 0
                except Exception as exc:
                    failures += 1
                    log.error("Falló el turno (%d/%d): %s", failures, cfg.max_failures, exc)
                    if failures >= cfg.max_failures:
                        break
                    try:
                        self._say(cfg.error_prompt, ch, spk, stop)
                    except Exception:
                        pass
        except Exception:
            log.exception("Error en el motor básico")
        finally:
            for dev in (mic, spk):
                if dev is not None:
                    try:
                        dev.close()
                    except Exception:
                        log.exception("Error cerrando audio")
            if not stop.is_set():
                on_end()

    def _trim(self, history: List[dict]) -> List[dict]:
        """Prompt del personaje + los últimos N intercambios (controla el tamaño y el costo)."""
        keep = self.cfg.history_turns * 2
        return [history[0]] + history[1:][-keep:]
