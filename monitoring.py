"""
Monitoreo de rendimiento — Lince Interactivo
Soporta LangSmith y Langfuse en paralelo.
Si las claves no están en .env, el módulo se deshabilita silenciosamente.
"""
from __future__ import annotations
import os
import time
from dotenv import load_dotenv

load_dotenv()

# ── Detección de configuración ────────────────────────────────────────────────
# Soporta tanto el nombre nuevo (LANGSMITH_API_KEY) como el antiguo (LANGCHAIN_API_KEY)

_langsmith_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")

LANGSMITH_HABILITADO = bool(_langsmith_key)
LANGFUSE_HABILITADO  = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))

# ── Configuración de LangSmith ────────────────────────────────────────────────
# LangSmith traza automáticamente todas las llamadas de LangChain (RAG/FAISS)
# con solo tener estas variables en el entorno.

if LANGSMITH_HABILITADO:
    os.environ.setdefault("LANGSMITH_API_KEY", _langsmith_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", _langsmith_key)   # compatibilidad LangChain antiguo
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "lince-interactivo-uadeo")
    os.environ.setdefault("LANGCHAIN_PROJECT", "lince-interactivo-uadeo")

# ── Inicialización de Langfuse ────────────────────────────────────────────────

_langfuse = None

if LANGFUSE_HABILITADO:
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as e:
        print(f"[Monitoreo] Langfuse no disponible: {e}")
        LANGFUSE_HABILITADO = False


# ── Cliente OpenAI (con trazado automático) ───────────────────────────────────

def get_openai_client(api_key: str, timeout: float = 25.0):
    """
    Devuelve un cliente OpenAI envuelto para trazado automático.
    Prioridad: Langfuse → LangSmith → cliente sin trazado.
    En todos los casos captura tokens, costo y latencia de cada llamada.
    """
    from openai import OpenAI
    cliente = OpenAI(api_key=api_key, timeout=timeout)

    if LANGFUSE_HABILITADO:
        try:
            from langfuse.openai import OpenAI as LangfuseOpenAI
            return LangfuseOpenAI(api_key=api_key, timeout=timeout)
        except Exception:
            pass

    if LANGSMITH_HABILITADO:
        try:
            from langsmith.wrappers import wrap_openai
            return wrap_openai(cliente)
        except Exception:
            pass

    return cliente


# ── Trazado manual de una conversación completa ───────────────────────────────

class TraceLlamada:
    """
    Context manager que registra una llamada completa al LLM en Langfuse:
    pregunta del estudiante, respuesta del bot, tokens usados y latencia.
    """

    def __init__(self, session_id: str, pregunta: str):
        self._session_id = session_id
        self._pregunta   = pregunta
        self._trace      = None
        self._span       = None
        self._inicio     = time.time()

    def __enter__(self):
        if _langfuse:
            self._trace = _langfuse.trace(
                name="respuesta-lince",
                session_id=self._session_id,
                input=self._pregunta,
                tags=["kiosco", "uadeo"],
            )
            self._span = self._trace.span(name="llm-call")
        return self

    def registrar_respuesta(self, respuesta: str, tokens_entrada: int = 0, tokens_salida: int = 0):
        latencia = round((time.time() - self._inicio) * 1000)
        if self._span:
            self._span.end(
                output=respuesta,
                metadata={
                    "tokens_entrada": tokens_entrada,
                    "tokens_salida":  tokens_salida,
                    "latencia_ms":    latencia,
                },
            )
        if self._trace:
            self._trace.update(output=respuesta)

    def __exit__(self, *_):
        pass


# ── Registro de puntuación (feedback) ────────────────────────────────────────

def registrar_score(trace_id: str, score: float, comentario: str = ""):
    """Registra una puntuación 0-1 sobre una respuesta (útil para análisis futuro)."""
    if _langfuse and trace_id:
        _langfuse.score(trace_id=trace_id, name="calidad", value=score, comment=comentario)


# ── Flush al cerrar la app ────────────────────────────────────────────────────

def cerrar():
    """Llama esto al cerrar la app para asegurar que todos los datos se enviaron."""
    if _langfuse:
        _langfuse.flush()


# ── Estado del monitoreo para mostrar en UI ───────────────────────────────────

def estado() -> str:
    partes = []
    if LANGSMITH_HABILITADO:
        partes.append("LangSmith")
    if LANGFUSE_HABILITADO:
        partes.append("Langfuse")
    return "Monitoreo: " + " + ".join(partes) if partes else "Monitoreo: deshabilitado"
