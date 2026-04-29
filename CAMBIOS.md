# LINCE — Registro de cambios

---

## v1.0 — Base del proyecto
**Archivos:** `lince_bot.py`, `config.py`, `universidad_info.py`

Bot de voz por terminal usando OpenAI GPT-4o-mini, reconocimiento de voz con SpeechRecognition y síntesis de voz con gTTS/pyttsx3.

---

## v2.0 — Versión Web (Flask → FastAPI + Supabase)
**Archivos modificados:** `app.py`, `config.py`, `requirements.txt`
**Archivos nuevos:** `vercel.json`, `supabase_setup.sql`

### ¿Qué cambió y por qué?

**`app.py` — migración de Flask a FastAPI**
- Flask fue reemplazado por FastAPI porque funciona mejor en Vercel (serverless).
- Se conectó Supabase para guardar el historial de conversaciones en base de datos real.
- El historial ya no se pierde al reiniciar el servidor.
- Cada usuario tiene un `session_id` único guardado en su navegador (localStorage).

**`config.py` — nuevas variables**
- Se agregaron `SUPABASE_URL` y `SUPABASE_ANON_KEY` leídas desde el archivo `.env`.

**`requirements.txt`**
- Se agregaron: `fastapi`, `uvicorn[standard]`, `supabase`, `aiofiles`, `jinja2`.

**`vercel.json` (nuevo)**
- Archivo de configuración para desplegar el proyecto en Vercel con un solo comando.

**`supabase_setup.sql` (nuevo)**
- Script SQL para crear la tabla `conversaciones` en Supabase.
- Guarda cada mensaje (usuario y bot) con su sesión, rol, contenido y fecha.

**`index.html`**
- Se agregó manejo de `session_id` con `localStorage` para que cada usuario tenga su propia conversación persistente.

---

## v2.1 — Base de conocimiento en Supabase
**Archivos modificados:** `universidad_info.py`, `app.py`
**Archivos nuevos:** `supabase_conocimiento.sql`

### ¿Qué cambió y por qué?

**`universidad_info.py` — información dinámica**
- La información de la UAdeO ya no está escrita en el código (hardcoded).
- Ahora se carga desde la tabla `conocimiento` en Supabase.
- El personal de la universidad puede editar la información directo en Supabase sin tocar código.
- Si Supabase no está disponible, el bot muestra un mensaje de aviso.

**`app.py` — caché del conocimiento**
- Se agregó un caché en memoria del system prompt para no consultar Supabase en cada mensaje.
- Se agregó el endpoint `POST /refresh-conocimiento` para recargar la información sin reiniciar el servidor.

**`supabase_conocimiento.sql` (nuevo)**
- Script SQL para crear la tabla `conocimiento` con campos: `categoria`, `titulo`, `contenido`, `activo`.
- Incluye datos iniciales de la UAdeO listos para editar.
- El campo `activo` permite desactivar una sección sin borrarla.

---

## v2.2 — Voz humana con OpenAI TTS
**Archivos modificados:** `app.py`, `templates/index.html`

### ¿Qué cambió y por qué?

**`app.py` — nuevo endpoint `/tts`**
- Se agregó el endpoint `POST /tts` que recibe texto y devuelve audio MP3.
- Usa el modelo `tts-1` de OpenAI con la voz `nova` (femenina, natural en español).
- La voz de OpenAI suena humana y natural, a diferencia de la voz del navegador que suena robótica.
- Voces disponibles: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`.

**`templates/index.html` — reproductor de audio real**
- Se reemplazó `window.speechSynthesis` (voz del sistema) por llamadas al endpoint `/tts`.
- El bot genera el audio en el servidor y lo reproduce como un archivo MP3 en el navegador.
- Si hay un audio reproduciéndose y el usuario habla, el audio se detiene automáticamente.

---

## Cómo correr el proyecto localmente

```bash
# Instalar dependencias
.venv\Scripts\pip install -r requirements.txt

# Iniciar servidor web
.venv\Scripts\uvicorn app:app --reload --port 5000

# Abrir en navegador
http://127.0.0.1:5000
```

## Variables de entorno requeridas (.env)

```
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

## Deploy en Vercel

1. Subir el proyecto a GitHub
2. Importar en Vercel
3. Agregar las variables de entorno en Vercel → Settings → Environment Variables
4. Deploy automático
