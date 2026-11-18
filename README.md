# Cabina telefónica del museo (versión básica y gratuita)

El visitante descuelga, marca el **1** y conversa con Marie. Todo por el auricular del teléfono.

```
disco/gancho ─▶ Arduino ─USB─▶ PC ◀─USB─ tarjeta de sonido ◀─▶ receptor y micrófono
                                │
                       Groq (transcribe y responde, gratis)
                       edge-tts (voz en español, gratis)
```

Flujo: tono de marcar → número → timbrado → Marie saluda → el visitante habla, Marie responde
(por turnos) → al colgar se corta todo. Si el visitante calla, Marie pregunta si sigue ahí y,
si sigue el silencio, se despide y corta. Tope de 3 minutos por llamada.

## 1. Instalar (una vez)

```
python -m pip install -r requirements.txt
```
(Windows: instala Python desde python.org marcando "Add to PATH". El Arduino con chip CH340
puede necesitar su driver. Linux: tu usuario debe estar en el grupo `dialout`.)

## 2. Clave gratuita

1. Crea una cuenta en console.groq.com y genera una **API key** (capa gratuita, sin tarjeta
   hasta donde yo sé; las condiciones y límites pueden cambiar).
2. Copia `.env.example` como `.env` y pega la clave en `GROQ_API_KEY=`.

## 3. Probar por etapas

| Paso | Comando | Qué debe pasar |
|---|---|---|
| a | `python main.py --list-ports` | aparece el Arduino (COM3, /dev/ttyUSB0…). Pon ese valor en `.env` (`CABINA_PORT`). |
| b | `python main.py --list-audio` | aparece la tarjeta (ej. `AB13X`). Pon el nombre en `CABINA_AUDIO_IN` y `CABINA_AUDIO_OUT`. |
| c | `python main.py --check` | tres líneas **OK**: internet, Groq y voz. |
| d | `python main.py --keyboard --engine demo --no-audio` | simula el teléfono con el teclado: `u` + Enter descuelga, `1` marca, `d` cuelga, `q` sale. Verás los estados en pantalla. |
| e | `python main.py --engine demo` | con el teléfono real: tono de marcar, timbrado y "contesta Marie" (sin voz). |
| f | `python main.py` | conversación real. |

Atajo para probar sin marcar: `python main.py --auto-dial marie`.

## 4. Ajustes (en `config.py`)

- **Personaje:** `CHARACTERS` → pega en `system_prompt` la biografía y el tono de Marie, y
  cambia `greeting`. Para otro personaje, añade otro `Character` con otro dígito.
- **Voz:** `BASIC.voice` (por defecto `es-CL-CatalinaNeural`; `edge-tts --list-voices` muestra
  todas) y `voice_rate` para hablar más lento.
- **Volumen del receptor:** `Settings.voice_gain` y `tone_gain`. Sube de a poco.
- **Si capta ruido como voz** (Marie responde sola): sube `vad_min_rms`. **Si no te detecta:**
  bájalo o acércate al micrófono. `end_silence_ms` es cuánto silencio cierra tu frase.
- **Cuánto recuerda:** `history_turns`.

## 5. Problemas típicos

- **"Groq respondió 404 / model not found":** cambiaron el nombre del modelo. Mira la lista en
  console.groq.com/docs/models y ajusta `GROQ_LLM_MODEL` / `GROQ_STT_MODEL` en `.env`. Con modelos que razonan (gpt-oss)
  deja `GROQ_REASONING_EFFORT=low`; con otros (qwen, llama) déjalo vacío.
- **"Groq respondió 429":** pasaste el límite gratuito; espera un poco.
- **El teclado se bloquea al conectar el micrófono:** la tarjeta AB13X tiene una interfaz de
  botones; con el cableado correcto no debería pasar. En Linux: `xinput list` y `xinput disable <id>`.
- **Sin internet:** esta versión no tiene modo sin conexión; la llamada da tono de ocupado.
  Se puede añadir como motor de respaldo más adelante.
- Los registros quedan en `cabina.log`.

## 6. Qué no está verificado

- Que edge-tts (librería no oficial que usa la voz de Microsoft Edge) siga disponible y que la
  voz `es-CL-CatalinaNeural` exista: pruébalo con `--check`.
- Los límites exactos de la capa gratuita de Groq y los nombres vigentes de sus modelos.
- Todo el código está probado con teléfono y servicios simulados (22 pruebas: `python -m pytest`),
  **no** con el hardware real ni con los servicios reales.
- La frecuencia y cadencia de los tonos (425 Hz) son valores de partida.
