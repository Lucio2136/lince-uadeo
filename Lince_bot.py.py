import google.generativeai as genai
import speech_recognition as sr
import pyttsx3

# --- 1. CONFIGURACIÓN DE VOZ (SALIDA) ---
engine = pyttsx3.init()
voices = engine.getProperty('voices')

# Intentar configurar voz en español
for voice in voices:
    if "spanish" in voice.name.lower():
        engine.setProperty('voice', voice.id)
        break

engine.setProperty('rate', 165) # Velocidad al hablar

def hablar(texto):
    print(f"Lince: {texto}")
    engine.say(texto)
    engine.runAndWait()

# --- 2. CONFIGURACIÓN DE IA (CEREBRO) ---
# REEMPLAZA ESTO CON TU KEY REAL
genai.configure(api_key="AIzaSyBQ7SzmbfCrqEspukhUVmpNS1FCYPnSG2g") 

model = genai.GenerativeModel(
    model_name="models/gemini-1.5-flash", 
    system_instruction="Eres el Lince de la UAdeO Culiacán. Responde corto, máximo 2 frases. Sé amable y entusiasta."
)
chat = model.start_chat(history=[])

# --- 3. CONFIGURACIÓN DE MICRÓFONO (ENTRADA) ---
rec = sr.Recognizer()

def escuchar():
    with sr.Microphone() as source:
        print("\n--- Escuchando... (Habla ahora) ---")
        # Ajuste para el ruido de fondo
        rec.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = rec.listen(source, timeout=5, phrase_time_limit=10)
            texto = rec.recognize_google(audio, language="es-MX")
            print(f"Tú dijiste: {texto}")
            return texto
        except sr.UnknownValueError:
            print("No te entendí nada, intenta de nuevo.")
            return None
        except Exception as e:
            print(f"Error con el micro: {e}")
            return None

# --- BUCLE PRINCIPAL ---
hablar("¡Hola! Soy el Lince de la UAdeO. ¿En qué te puedo ayudar hoy?")

while True:
    pregunta = escuchar()
    
    if pregunta:
        pregunta_low = pregunta.lower()
        if "adiós" in pregunta_low or "salir" in pregunta_low or "terminar" in pregunta_low:
            hablar("¡Nos vemos! Éxito en tus clases.")
            break
            
        try:
            response = chat.send_message(pregunta)
            hablar(response.text)
        except Exception as e:
            print(f"Error al conectar con Gemini: {e}")
            hablar("Lo siento, tuve un problema con mi conexión.")