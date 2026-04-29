"""
Configuración central del prototipo Lince.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── OPENAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-4o-mini"

# ─── SUPABASE ──────────────────────────────────────────────────────────────────
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# ─── VOZ (solo para lince_bot.py en terminal) ──────────────────────────────────
SPEECH_LANGUAGE        = "es-MX"
LISTEN_TIMEOUT         = 6
PHRASE_TIME_LIMIT      = 12
AMBIENT_NOISE_DURATION = 0.6
TTS_ENGINE             = "gtts"
TTS_RATE               = 165
GTTS_LANG              = "es"
GTTS_TLD               = "com.mx"

# ─── COMPORTAMIENTO DEL BOT ────────────────────────────────────────────────────
BOT_NAME    = "Lince"
UNIVERSIDAD = "UAdeO"

PALABRAS_SALIDA = ["adiós", "adios", "hasta luego", "salir", "terminar", "cerrar", "bye", "chao"]

MENSAJE_BIENVENIDA = (
    f"¡Hola! Soy {BOT_NAME}, el asistente virtual de la {UNIVERSIDAD}. "
    "¿En qué te puedo ayudar hoy?"
)
MENSAJE_DESPEDIDA  = "¡Hasta luego! Mucho éxito en tus estudios. ¡Arriba el Lince!"
MENSAJE_NO_ENTENDI = "No te escuché bien, ¿puedes repetirlo?"
MENSAJE_ERROR_IA   = "Lo siento, tuve un problema al procesar tu pregunta. Intenta de nuevo."
