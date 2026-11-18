"""Configuración de la cabina. Edita este archivo; las claves van en el archivo .env."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv es opcional
    pass

BASE_DIR = Path(__file__).resolve().parent


@dataclass
class Character:
    id: str
    name: str
    digit: str            # número que se marca en el disco: "1".."9" o "0"
    system_prompt: str    # quién es, qué sabe, cómo habla
    greeting: str         # primera frase al contestar el teléfono
    voice: str = ""       # voz de edge-tts; vacío = la de Settings.voice


# ---------------------------------------------------------------------------
# Personajes. Por ahora uno solo; para agregar otro basta añadir otro Character
# con un dígito distinto.
# ---------------------------------------------------------------------------
CHARACTERS: List[Character] = [
    Character(
        id="marie",
        name="Marie Bulling",
        digit="1",
        # TODO: pega aquí el prompt real de Marie (biografía, época, tono, qué sabe
        # y qué no). Este texto es solo un marcador de posición.
        system_prompt=(
            "Eres Marie Bulling, un personaje histórico que atiende una llamada "
            "telefónica en un museo. [PEGA AQUÍ la biografía, la época y el tono "
            "del personaje]. Habla siempre en español, con frases cortas (máximo "
            "tres por respuesta), como se habla por teléfono, sin listas ni "
            "símbolos. Si no sabes algo, dilo con naturalidad dentro del personaje. "
            "Si el visitante pregunta directamente si eres una inteligencia "
            "artificial, responde con honestidad."
        ),
        greeting="¿Aló? Habla Marie. ¿Con quién tengo el gusto?",
    ),
]


@dataclass
class Settings:
    # --- Arduino ---
    serial_port: str = os.getenv("CABINA_PORT", "COM3")
    serial_baud: int = 9600

    # --- Audio: parte del nombre del dispositivo (vacío = predeterminado del sistema).
    # Usa `python main.py --list-audio` para ver los nombres (ej. "AB13X").
    audio_in: str = os.getenv("CABINA_AUDIO_IN", "")
    audio_out: str = os.getenv("CABINA_AUDIO_OUT", "")

    # Motores en orden de preferencia; se usa el primero que esté disponible.
    # "basic" = Groq (gratis) + voz edge-tts. "demo" = sin servicios, solo prueba el flujo.
    engine_order: Tuple[str, ...] = ("basic",)

    # Si lo pones (por ejemplo "marie"), al descolgar se llama directo a ese
    # personaje sin tono de marcar ni dígito. None = hay que marcar el número.
    auto_dial_character: Optional[str] = None

    # --- Tiempos (segundos) ---
    ring_seconds: float = 2.5          # timbrado antes de que conteste el personaje
    dial_timeout_seconds: float = 25   # si nadie marca, pasa a tono de ocupado
    busy_seconds: float = 15           # cuánto suena el ocupado antes de callar
    max_call_seconds: float = 180      # corte automático de la llamada

    # --- Niveles (0..1). El receptor queda pegado al oído: no subir sin probar.
    tone_gain: float = 0.25
    voice_gain: float = 0.6

    # --- Tonos: nombre -> (frecuencia Hz, segundos sonando, segundos en silencio).
    # Valores de partida: ajústalos a gusto (no verifiqué el estándar chileno).
    tones: Dict[str, Tuple[float, float, float]] = field(
        default_factory=lambda: {
            "dial": (425.0, 1.0, 0.0),
            "ring": (425.0, 1.0, 2.0),
            "busy": (425.0, 0.5, 0.5),
        }
    )


@dataclass
class BasicSettings:
    """Motor básico: Groq (transcripción + respuesta, capa gratuita) y edge-tts (voz)."""
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    # Los nombres de modelo cambian con el tiempo: si Groq responde "model not found",
    # revisa la lista vigente en console.groq.com/docs/models y cámbialos en .env.
    stt_model: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
    llm_model: str = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
    # Modelos que "razonan" (gpt-oss): "low" evita que el razonamiento se coma los
    # max_tokens y deje la respuesta vacía. Vacío = no se envía (p. ej. para qwen).
    reasoning_effort: str = os.getenv("GROQ_REASONING_EFFORT", "low")
    language: str = "es"
    max_tokens: int = 150
    temperature: float = 0.7
    history_turns: int = 8            # cuántos intercambios recuerda el personaje
    request_timeout: float = 20.0

    # Voz de edge-tts (gratuita, necesita internet). Lista: `edge-tts --list-voices`.
    voice: str = os.getenv("CABINA_VOICE", "es-CL-CatalinaNeural")
    voice_rate: str = "+0%"           # velocidad, ej. "-10%" para hablar más lento

    # Detección de voz por energía (RMS sobre int16, 16 kHz).
    vad_min_rms: float = 350.0        # sube si capta ruido como voz
    end_silence_ms: int = 900         # silencio que cierra la frase del visitante
    min_speech_ms: int = 300          # menos que esto se descarta como ruido
    max_utterance_ms: int = 15000
    idle_listen_seconds: float = 12.0  # sin hablar: pregunta si sigue ahí; luego corta
    max_failures: int = 3             # errores seguidos antes de cortar la llamada

    idle_prompt: str = "¿Sigue ahí? No lo escucho bien."
    goodbye: str = "Parece que se cortó la comunicación. Llame de nuevo cuando quiera. Adiós."
    error_prompt: str = "Perdone, no le escuché bien. ¿Me lo repite?"


SETTINGS = Settings()
BASIC = BasicSettings()
