"""
LINCE v6 — Stack: FastAPI + urllib (nativo Python) + Supabase
Sin dependencia del SDK de OpenAI — usa urllib directamente.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
import asyncio
import uuid
import io
import os
import json
import urllib.request
import urllib.error
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

# ── OpenAI con urllib nativo (sin SDK, sin httpx) ─────────────────────────────

def _openai_post(endpoint: str, payload: dict, timeout: int = 25) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.openai.com/v1/{endpoint}",
        data=body,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode(errors="replace")
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body_err}")
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {type(e).__name__}: {e}")

def _chat_sync(messages: list) -> str:
    result = _openai_post("chat/completions", {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 400,
    })
    return result["choices"][0]["message"]["content"] or ""

def _tts_sync(texto: str) -> bytes:
    body = json.dumps({
        "model": "tts-1",
        "voice": "ash",
        "input": texto,
        "response_format": "mp3",
        "speed": 1.2,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()

def _stt_sync(nombre: str, contenido: bytes) -> str:
    import email.mime.multipart
    import email.mime.base
    # Multipart manual para Whisper
    boundary = "----LinceBoundary7MA4YWxkTrZu0gW"
    prompt_text = (
        "Estudiante de la UAdeO Culiacán Sinaloa hablando con acento sinaloense. "
        "Vocabulario: kardex, credencial, beca, servicio social, servicios escolares, "
        "biblioteca, carrera, coordinador, titulación, trámite, matrícula, semestre, UAdeO."
    )
    def field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = (
        field("model", "whisper-1") +
        field("language", "es") +
        field("prompt", prompt_text) +
        f"--{boundary}\r\n".encode() +
        f'Content-Disposition: form-data; name="file"; filename="{nombre}"\r\n'.encode() +
        b"Content-Type: audio/webm\r\n\r\n" +
        contenido +
        f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("text", "").strip()
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise RuntimeError(f"Whisper {e.code}: {err}")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
async def health():
    return {"version": "v6", "ok": True}


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
    except Exception as e:
        print(f"[ERROR chat] {e}")
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
        print(f"[ERROR TTS] {e}")
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
        print(f"[ERROR STT] {e}")
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
