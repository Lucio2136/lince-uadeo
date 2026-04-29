"""
LINCE — Servidor web del asistente virtual UAdeO.
Stack: FastAPI + OpenAI + Supabase
"""

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from supabase import create_client, Client
import asyncio
import uuid
import io
import json
import os
from dotenv import load_dotenv

load_dotenv()

from config import OPENAI_API_KEY, OPENAI_MODEL, SUPABASE_URL, SUPABASE_ANON_KEY
from universidad_info import get_system_prompt

app = FastAPI()

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_openai_client: OpenAI | None = None
_supabase_client: Client | None = None

def get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", OPENAI_API_KEY))
    return _openai_client

def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            os.getenv("SUPABASE_URL", SUPABASE_URL),
            os.getenv("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY),
        )
    return _supabase_client

_system_prompt_cache: str | None = None

def get_cached_prompt() -> str:
    global _system_prompt_cache
    if _system_prompt_cache is None:
        _system_prompt_cache = get_system_prompt()
    return _system_prompt_cache

def _guardar_mensajes(session_id: str, pregunta: str, respuesta: str):
    """Guarda ambos mensajes en Supabase en una sola llamada."""
    get_supabase().table("conversaciones").insert([
        {"session_id": session_id, "role": "user",      "content": pregunta},
        {"session_id": session_id, "role": "assistant", "content": respuesta},
    ]).execute()

def _obtener_historial(session_id: str) -> list:
    result = (
        get_supabase().table("conversaciones")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return list(reversed([{"role": r["role"], "content": r["content"]} for r in result.data]))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    session_id = data.get("session_id") or str(uuid.uuid4())
    pregunta = data.get("mensaje", "").strip()

    if not pregunta:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    loop = asyncio.get_event_loop()
    historial = await loop.run_in_executor(None, _obtener_historial, session_id)
    historial.append({"role": "user", "content": pregunta})
    mensajes = [{"role": "system", "content": get_cached_prompt()}] + historial

    async def stream_respuesta():
        texto_completo = ""
        try:
            with get_openai().chat.completions.create(
                model=OPENAI_MODEL,
                messages=mensajes,
                temperature=0.7,
                max_tokens=400,
                stream=True,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        texto_completo += delta
                        yield f"data: {json.dumps({'chunk': delta})}\n\n"

            # Guardar en DB sin bloquear y enviar señal de fin
            loop.run_in_executor(None, _guardar_mensajes, session_id, pregunta, texto_completo)
            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

        except Exception as e:
            print(f"[ERROR OpenAI stream] {e}")
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'texto': texto_completo})}\n\n"

    return StreamingResponse(stream_respuesta(), media_type="text/event-stream")


@app.post("/tts")
async def tts(request: Request):
    data = await request.json()
    texto = data.get("texto", "").strip()

    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío")

    loop = asyncio.get_event_loop()

    try:
        response = await loop.run_in_executor(
            None,
            lambda: get_openai().audio.speech.create(
                model="tts-1",          # tts-1 es más rápido, buena calidad
                voice="ash",
                input=texto,
                response_format="mp3",
                speed=1.2,              # ligeramente más rápido al hablar
            )
        )
        audio_bytes = response.read()
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")

    except Exception as e:
        print(f"[ERROR TTS] {e}")
        raise HTTPException(status_code=500, detail="Error al generar voz")


@app.post("/refresh-conocimiento")
async def refresh_conocimiento():
    global _system_prompt_cache
    loop = asyncio.get_event_loop()
    _system_prompt_cache = await loop.run_in_executor(None, get_system_prompt)
    return JSONResponse({"ok": True, "mensaje": "Conocimiento recargado"})


@app.post("/stt")
async def stt(audio: UploadFile = File(...)):
    contenido = await audio.read()
    print(f"[STT] recibido {len(contenido)} bytes, filename={audio.filename}")

    if len(contenido) < 200:
        return JSONResponse({"texto": ""})

    archivo = io.BytesIO(contenido)
    nombre  = audio.filename or "audio.webm"

    loop = asyncio.get_event_loop()
    try:
        transcript = await loop.run_in_executor(
            None,
            lambda: get_openai().audio.transcriptions.create(
                model="whisper-1",
                file=(nombre, archivo, "audio/webm"),
                language="es",
                prompt=(
                    "Estudiante de la UAdeO Culiacán Sinaloa hablando con acento sinaloense. "
                    "Vocabulario esperado: kardex, credencial, beca, servicio social, "
                    "servicios escolares, biblioteca, edificio, carrera, coordinador, "
                    "titulación, trámite, horario, matrícula, semestre, prácticas, "
                    "UAdeO, Lince, aula, campus. "
                    "Expresiones: órale, chido, ahorita, mande, ¿qué onda?, híjole, "
                    "ándale, óye, está cañón, ¿cómo le hago?, "
                    "¿dónde está?, ¿cuándo es?, ¿cómo saco?"
                ),
            )
        )
        texto = transcript.text.strip()
        print(f"[STT] transcripción: {repr(texto)}")
        return JSONResponse({"texto": texto})
    except Exception as e:
        print(f"[ERROR Whisper] {e}")
        raise HTTPException(status_code=500, detail="Error en transcripción")


@app.post("/reset")
async def reset(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    if session_id:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: get_supabase().table("conversaciones").delete().eq("session_id", session_id).execute()
        )
    return JSONResponse({"ok": True})
