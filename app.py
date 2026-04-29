"""
LINCE — Servidor web del asistente virtual UAdeO.
Stack: FastAPI + httpx (sync) + Supabase
"""

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
import httpx
import asyncio
import uuid
import io
import os
from dotenv import load_dotenv

load_dotenv()

from config import OPENAI_API_KEY, OPENAI_MODEL, SUPABASE_URL, SUPABASE_ANON_KEY
from universidad_info import get_system_prompt

app = FastAPI()

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_supabase_client: Client | None = None

def get_supabase() -> Client:
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

def _api_key() -> str:
    return os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY

def _guardar_mensajes(session_id: str, pregunta: str, respuesta: str):
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

# ── Llamadas a OpenAI con httpx sync (más estable en Vercel que httpx async) ──

def _chat_sync(messages: list) -> str:
    with httpx.Client(timeout=25.0) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": OPENAI_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 400,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

def _tts_sync(texto: str) -> bytes:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": "tts-1",
                "voice": "ash",
                "input": texto,
                "response_format": "mp3",
                "speed": 1.2,
            },
        )
        r.raise_for_status()
        return r.content

def _stt_sync(nombre: str, contenido: bytes) -> str:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {_api_key()}"},
            data={
                "model": "whisper-1",
                "language": "es",
                "prompt": (
                    "Estudiante de la UAdeO Culiacán Sinaloa hablando con acento sinaloense. "
                    "Vocabulario esperado: kardex, credencial, beca, servicio social, "
                    "servicios escolares, biblioteca, edificio, carrera, coordinador, "
                    "titulación, trámite, horario, matrícula, semestre, prácticas, "
                    "UAdeO, Lince, aula, campus."
                ),
            },
            files={"file": (nombre, contenido, "audio/webm")},
        )
        r.raise_for_status()
        return r.json().get("text", "").strip()


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

    loop = asyncio.get_running_loop()
    historial = await loop.run_in_executor(None, _obtener_historial, session_id)
    historial.append({"role": "user", "content": pregunta})
    mensajes = [{"role": "system", "content": get_cached_prompt()}] + historial

    try:
        texto_completo = await loop.run_in_executor(None, _chat_sync, mensajes)
        loop.run_in_executor(None, _guardar_mensajes, session_id, pregunta, texto_completo)
        return JSONResponse({"respuesta": texto_completo, "session_id": session_id})
    except httpx.HTTPStatusError as e:
        print(f"[ERROR OpenAI] HTTP {e.response.status_code}: {e.response.text}")
        raise HTTPException(status_code=500, detail=f"OpenAI {e.response.status_code}")
    except Exception as e:
        print(f"[ERROR OpenAI] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def tts(request: Request):
    data = await request.json()
    texto = data.get("texto", "").strip()

    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío")

    loop = asyncio.get_running_loop()
    try:
        audio_bytes = await loop.run_in_executor(None, _tts_sync, texto)
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        print(f"[ERROR TTS] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Error al generar voz")


@app.post("/refresh-conocimiento")
async def refresh_conocimiento():
    global _system_prompt_cache
    loop = asyncio.get_running_loop()
    _system_prompt_cache = await loop.run_in_executor(None, get_system_prompt)
    return JSONResponse({"ok": True, "mensaje": "Conocimiento recargado"})


@app.post("/stt")
async def stt(audio: UploadFile = File(...)):
    contenido = await audio.read()
    if len(contenido) < 200:
        return JSONResponse({"texto": ""})

    nombre = audio.filename or "audio.webm"
    loop = asyncio.get_running_loop()
    try:
        texto = await loop.run_in_executor(None, _stt_sync, nombre, contenido)
        return JSONResponse({"texto": texto})
    except Exception as e:
        print(f"[ERROR Whisper] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Error en transcripción")


@app.post("/reset")
async def reset(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    if session_id:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: get_supabase().table("conversaciones").delete().eq("session_id", session_id).execute()
        )
    return JSONResponse({"ok": True})
