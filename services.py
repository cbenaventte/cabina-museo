"""Servicios externos del motor básico: transcripción y respuesta (Groq) y voz (edge-tts).

Son funciones sueltas y sin estado para poder reemplazarlas en las pruebas.
"""
import asyncio
import io
import logging
import re
import socket
import wave
from typing import List, Optional

log = logging.getLogger("services")

GROQ_BASE = "https://api.groq.com/openai/v1"
RATE = 16000

# Whisper inventa frases típicas cuando recibe silencio o ruido: se descartan.
_HALLUCINATIONS = (
    "subtítulos", "subtitulos", "amara.org", "gracias por ver", "suscríbete",
    "suscribete", "thanks for watching", "música", "musica",
)


def internet_ok(host: str = "api.groq.com", port: int = 443, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pcm_to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def clean_transcript(text: str) -> str:
    """Devuelve '' si el texto es vacío o una alucinación típica de Whisper."""
    t = (text or "").strip()
    low = t.lower()
    if len(re.sub(r"\W", "", t)) < 2:
        return ""
    if any(h in low for h in _HALLUCINATIONS) and len(t) < 60:
        return ""
    return t


def transcribe(pcm: bytes, api_key: str, model: str, language: str = "es",
               timeout: float = 20.0) -> str:
    import requests

    r = requests.post(
        f"{GROQ_BASE}/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("audio.wav", pcm_to_wav(pcm), "audio/wav")},
        data={"model": model, "language": language, "temperature": "0",
              "response_format": "json"},
        timeout=timeout,
    )
    _raise_for_status(r)
    return clean_transcript(r.json().get("text", ""))


def chat(messages: List[dict], api_key: str, model: str, max_tokens: int = 150,
         temperature: float = 0.7, timeout: float = 20.0,
         reasoning_effort: str = "") -> str:
    import requests

    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    r = requests.post(
        f"{GROQ_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=timeout,
    )
    _raise_for_status(r)
    content = (r.json()["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError("Groq devolvió una respuesta vacía (¿razonamiento demasiado largo? "
                           "revisa GROQ_REASONING_EFFORT o sube max_tokens)")
    return content


def _raise_for_status(r) -> None:
    if r.status_code >= 400:
        # El cuerpo de Groq explica el motivo (clave mala, modelo inexistente, límite).
        raise RuntimeError(f"Groq respondió {r.status_code}: {r.text[:300]}")


def split_sentences(text: str, max_chars: int = 220) -> List[str]:
    """Parte la respuesta en frases para empezar a hablar antes de terminar de sintetizar."""
    text = re.sub(r"[*_#`>\[\]]", "", text)       # sin markdown: se leería en voz alta
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?¡¿…])\s+", text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        while len(p) > max_chars:                  # frase larguísima: cortar en una coma
            cut = p.rfind(",", 0, max_chars)
            cut = cut if cut > 40 else max_chars
            out.append(p[:cut].strip())
            p = p[cut:].lstrip(", ")
        if p:
            out.append(p)
    return out


async def _edge_stream(text: str, voice: str, rate: str) -> bytes:
    import edge_tts

    buf = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def synthesize(text: str, voice: str, rate: str = "+0%") -> bytes:
    """Texto -> PCM int16 mono 16 kHz, listo para el receptor."""
    import miniaudio

    mp3 = asyncio.run(_edge_stream(text, voice, rate))
    if not mp3:
        raise RuntimeError("edge-tts no devolvió audio")
    decoded = miniaudio.decode(
        mp3, output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1, sample_rate=RATE,
    )
    return decoded.samples.tobytes()


def check_services(api_key: str, voice: str, llm_model: str,
                   reasoning_effort: str = "") -> List[str]:
    """Comprobaciones rápidas para `main.py --check`. Devuelve líneas de informe."""
    lines = []
    lines.append(("OK " if internet_ok() else "FALLA ") + "conexión con api.groq.com")
    if not api_key:
        lines.append("FALLA falta GROQ_API_KEY en el archivo .env")
    else:
        try:
            reply = chat([{"role": "user", "content": "Responde solo: listo"}], api_key,
                         llm_model, max_tokens=100,
                         reasoning_effort=reasoning_effort)
            lines.append(f"OK  respuesta de Groq: {reply!r}")
        except Exception as exc:
            lines.append(f"FALLA Groq: {exc}")
    try:
        pcm = synthesize("Prueba de voz.", voice)
        lines.append(f"OK  voz edge-tts ({voice}): {len(pcm) / 2 / RATE:.1f} s de audio")
    except Exception as exc:
        lines.append(f"FALLA voz edge-tts: {exc}")
    return lines
