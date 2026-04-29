"""
LINCE - Asistente Virtual de la Universidad de Occidente (UAdeO)
Prototipo de chat por voz usando OpenAI GPT.

Uso:
    python lince_bot.py
"""

import sys
import os
import time
import tempfile
import threading

# ─── DEPENDENCIAS ──────────────────────────────────────────────────────────────
try:
    from openai import OpenAI
except ImportError:
    print("[ERROR] Falta: pip install openai")
    sys.exit(1)

try:
    import speech_recognition as sr
except ImportError:
    print("[ERROR] Falta: pip install SpeechRecognition pyaudio")
    sys.exit(1)

from config import (
    OPENAI_API_KEY, OPENAI_MODEL,
    SPEECH_LANGUAGE, LISTEN_TIMEOUT, PHRASE_TIME_LIMIT, AMBIENT_NOISE_DURATION,
    TTS_ENGINE, TTS_RATE, GTTS_LANG, GTTS_TLD,
    BOT_NAME, PALABRAS_SALIDA,
    MENSAJE_BIENVENIDA, MENSAJE_DESPEDIDA,
    MENSAJE_NO_ENTENDI, MENSAJE_ERROR_IA,
)
from universidad_info import get_system_prompt


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE VOZ — SALIDA (TTS)
# ══════════════════════════════════════════════════════════════════════════════

def _init_pyttsx3():
    """Inicializa pyttsx3 y selecciona voz en español si existe."""
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    for voice in voices:
        if "spanish" in voice.name.lower() or "es_" in voice.id.lower():
            engine.setProperty("voice", voice.id)
            break
    engine.setProperty("rate", TTS_RATE)
    return engine


def _hablar_gtts(texto: str):
    """Síntesis de voz con Google TTS (requiere internet). Mejor calidad."""
    try:
        from gtts import gTTS
        import pygame

        tts = gTTS(text=texto, lang=GTTS_LANG, tld=GTTS_TLD, slow=False)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = tmp.name
        tts.save(tmp_path)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        pygame.mixer.music.stop()
        pygame.mixer.quit()
        os.unlink(tmp_path)

    except ImportError:
        print("[AVISO] gTTS/pygame no instalados, usando pyttsx3...")
        engine = _init_pyttsx3()
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        print(f"[AVISO] Error en gTTS ({e}), usando pyttsx3...")
        try:
            engine = _init_pyttsx3()
            engine.say(texto)
            engine.runAndWait()
        except Exception as e2:
            print(f"[ERROR TTS] {e2}")


_pyttsx3_engine = None

def hablar(texto: str):
    """Dice el texto en voz alta y lo imprime en pantalla."""
    global _pyttsx3_engine
    print(f"\n  {BOT_NAME}: {texto}\n")

    if TTS_ENGINE == "gtts":
        _hablar_gtts(texto)
    else:
        if _pyttsx3_engine is None:
            _pyttsx3_engine = _init_pyttsx3()
        _pyttsx3_engine.say(texto)
        _pyttsx3_engine.runAndWait()


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE VOZ — ENTRADA (STT)
# ══════════════════════════════════════════════════════════════════════════════

recognizer = sr.Recognizer()
recognizer.pause_threshold = 1.0
recognizer.energy_threshold = 300


def escuchar() -> str | None:
    """Escucha el micrófono y retorna el texto reconocido, o None si falla."""
    with sr.Microphone() as source:
        print("  [Escuchando...] Habla ahora")
        recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_DURATION)
        try:
            audio = recognizer.listen(
                source,
                timeout=LISTEN_TIMEOUT,
                phrase_time_limit=PHRASE_TIME_LIMIT,
            )
        except sr.WaitTimeoutError:
            print("  [Sin voz detectada]")
            return None

    print("  [Procesando voz...]")
    try:
        texto = recognizer.recognize_google(audio, language=SPEECH_LANGUAGE)
        print(f"  Tú: {texto}")
        return texto
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"  [ERROR STT] No se pudo conectar al servicio de voz: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE IA — OPENAI
# ══════════════════════════════════════════════════════════════════════════════

def iniciar_openai():
    """Crea y verifica el cliente de OpenAI."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    # Verificar conexión con un ping mínimo
    client.models.retrieve(OPENAI_MODEL)
    return client


def preguntar(client: OpenAI, historial: list, pregunta: str) -> str:
    """Envía una pregunta a OpenAI (con historial) y retorna la respuesta."""
    try:
        historial.append({"role": "user", "content": pregunta})

        respuesta = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": get_system_prompt()}] + historial,
            temperature=0.7,
            max_tokens=300,
        )

        texto = respuesta.choices[0].message.content.strip()
        historial.append({"role": "assistant", "content": texto})
        return texto

    except Exception as e:
        print(f"  [ERROR OpenAI] {e}")
        return MENSAJE_ERROR_IA


# ══════════════════════════════════════════════════════════════════════════════
# INTERFAZ VISUAL EN CONSOLA
# ══════════════════════════════════════════════════════════════════════════════

BANNER = r"""
╔══════════════════════════════════════════════════════╗
║                                                      ║
║    🐾  L I N C E  —  Asistente Virtual UAdeO  🐾     ║
║         Universidad de Occidente · Sinaloa           ║
║                                                      ║
║    Di "adiós" o "salir" para terminar                ║
╚══════════════════════════════════════════════════════╝
"""


def mostrar_banner():
    os.system("cls" if os.name == "nt" else "clear")
    print(BANNER)


def mostrar_pensando():
    """Animación de 'pensando' mientras espera respuesta."""
    simbolos = [".  ", ".. ", "..."]
    stop_event = threading.Event()

    def animar():
        i = 0
        while not stop_event.is_set():
            print(f"\r  [Pensando{simbolos[i % 3]}]", end="", flush=True)
            time.sleep(0.4)
            i += 1
        print("\r" + " " * 30 + "\r", end="", flush=True)

    hilo = threading.Thread(target=animar, daemon=True)
    hilo.start()
    return stop_event


# ══════════════════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    mostrar_banner()
    print("  Iniciando sistema...\n")

    # Conectar con OpenAI
    try:
        client = iniciar_openai()
        print("  [OK] OpenAI conectado.\n")
    except Exception as e:
        print(f"  [ERROR] No se pudo conectar con OpenAI: {e}")
        print("  Verifica tu API key en config.py")
        sys.exit(1)

    historial = []  # Memoria de la conversación

    # Saludo inicial
    hablar(MENSAJE_BIENVENIDA)

    # Bucle de conversación
    while True:
        print("─" * 54)
        pregunta = escuchar()

        if pregunta is None:
            hablar(MENSAJE_NO_ENTENDI)
            continue

        # Detectar palabra de salida
        if any(palabra in pregunta.lower() for palabra in PALABRAS_SALIDA):
            hablar(MENSAJE_DESPEDIDA)
            break

        # Obtener respuesta de la IA
        stop_animacion = mostrar_pensando()
        respuesta = preguntar(client, historial, pregunta)
        stop_animacion.set()
        time.sleep(0.1)

        hablar(respuesta)

    print("\n  Sesión terminada. ¡Hasta pronto!\n")


if __name__ == "__main__":
    main()
