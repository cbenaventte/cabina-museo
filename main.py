"""Cabina telefónica del museo.

Uso típico:
    python main.py --list-ports            # ver el puerto del Arduino (COMx)
    python main.py --list-audio            # ver los nombres de los dispositivos de audio
    python main.py --check                 # comprueba clave de Groq, internet y voz
    python main.py --keyboard --engine demo --no-audio   # probar el flujo sin hardware
    python main.py                         # funcionamiento normal
"""
import argparse
import logging
import queue
import sys
import threading
from dataclasses import replace

from config import BASIC, CHARACTERS, SETTINGS
from engines import build_engines
from orchestrator import Orchestrator
from phone import KeyboardPhone, SerialPhone, list_ports


def setup_logging(verbose: bool) -> None:
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=fmt,
                        handlers=[logging.StreamHandler(), logging.FileHandler("cabina.log", encoding="utf-8")])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-ports", action="store_true", help="lista los puertos serie")
    ap.add_argument("--list-audio", action="store_true", help="lista los dispositivos de audio")
    ap.add_argument("--check", action="store_true", help="comprueba Groq, internet y voz")
    ap.add_argument("--keyboard", action="store_true", help="simula el teléfono con el teclado")
    ap.add_argument("--no-audio", action="store_true", help="sin tonos (solo registro)")
    ap.add_argument("--engine", help="fuerza el motor: basic o demo")
    ap.add_argument("--port", help="puerto serie del Arduino (ej. COM3 o /dev/ttyUSB0)")
    ap.add_argument("--auto-dial", metavar="ID", help="al descolgar llama directo a ese personaje (ej. marie)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if args.list_ports:
        print(list_ports())
        return 0
    if args.list_audio:
        import audio_io

        print(audio_io.list_devices())
        return 0
    if args.check:
        import services

        for line in services.check_services(BASIC.groq_api_key, BASIC.voice, BASIC.llm_model,
                                           BASIC.reasoning_effort):
            print(line)
        return 0

    settings = SETTINGS
    if args.port:
        settings = replace(settings, serial_port=args.port)
    if args.auto_dial:
        settings = replace(settings, auto_dial_character=args.auto_dial)

    events: "queue.Queue" = queue.Queue()
    engines = build_engines(settings, [args.engine] if args.engine else None)

    if args.no_audio:
        from audio_io import NullTonePlayer

        tones = NullTonePlayer()
    else:
        from audio_io import TonePlayer

        tones = TonePlayer(settings.audio_out, settings.tones, settings.tone_gain)

    if args.keyboard:
        phone = KeyboardPhone(events)
    else:
        phone = SerialPhone(settings.serial_port, settings.serial_baud, events)
    phone.start()

    # Prepara los saludos en segundo plano para que el personaje conteste sin demora.
    for eng in engines:
        if hasattr(eng, "warmup"):
            threading.Thread(target=eng.warmup, args=(CHARACTERS,), daemon=True).start()

    orch = Orchestrator(settings, CHARACTERS, engines, tones, events)
    try:
        orch.run()
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(phone, "stop"):
            phone.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
