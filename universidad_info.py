from __future__ import annotations
import json
import os

_BASE = os.path.dirname(__file__)

_PROMPT_BASE = """Eres el "Lince Interactivo", asistente virtual oficial de la UAdeO (Universidad Autónoma de Occidente), Unidad Regional Culiacán. Estás instalado como kiosco en el campus para orientar a los estudiantes.

PERSONALIDAD:
- Profesional, amable y claro. Transmites confianza institucional.
- Hablas en español formal pero accesible, nunca frío ni distante.
- Tuteas al estudiante de forma respetuosa.
- Eres conciso: no das discursos, vas directo al punto.

REGLAS:
1. Nunca inventes datos que no estén en tu base de conocimiento.
2. Nunca digas "no sé". Redirige siempre a Servicios Escolares, Control Escolar o www.udo.mx.
3. Responde en español formal pero cercano.
4. Horario administrativo: lunes a viernes de 9:00 AM a 7:00 PM.

MEMORIA DE CONTEXTO:
- Usa el historial activamente. Si el estudiante ya mencionó su semestre o carrera, no lo vuelvas a preguntar.
- Conecta respuestas relacionadas entre sí.
- La memoria dura solo durante la conversación actual.

ESTRUCTURA DE RESPUESTA:
- Pregunta simple → 2-3 oraciones + pregunta de seguimiento.
- Pregunta compleja → responde cada punto, usa viñetas si hay pasos, cierra con seguimiento.
- Toda respuesta debe terminar con una pregunta de seguimiento. Sin excepción."""


def _cargar_conocimiento() -> str:
    path = os.path.join(_BASE, "universidad.json")
    try:
        with open(path, encoding="utf-8") as f:
            datos = json.load(f)
        lineas = []
        for registro in datos:
            linea = (
                f"- {registro.get('Tema', '')} ({registro.get('Departamento', '')}):\n"
                f"  {registro.get('Informacion_Completa', '')}"
            )
            if registro.get("Pregunta_Frecuente"):
                linea += f"\n  Preguntas frecuentes: {registro['Pregunta_Frecuente']}"
            if registro.get("Contacto"):
                linea += f"\n  Contacto: {registro['Contacto']}"
            lineas.append(linea)
        return "\n\n".join(lineas)
    except FileNotFoundError:
        return "Base de conocimiento no cargada aún. Contacta a Servicios Escolares o visita www.udo.mx"
    except Exception:
        return "Información no disponible."


def get_system_prompt() -> str:
    """Prompt completo con toda la base de conocimiento embebida (modo sin RAG)."""
    return f"{_PROMPT_BASE}\n\nBASE DE CONOCIMIENTO (UAdeO Culiacán):\n{_cargar_conocimiento()}"


def get_system_prompt_con_contexto(contexto: str) -> str:
    """Prompt con solo el contexto recuperado por RAG para esta consulta."""
    if contexto:
        seccion = f"\nCONTEXTO RELEVANTE (información recuperada para esta consulta):\n{contexto}"
    else:
        seccion = "\nNo se encontró información específica. Si no puedes responder con certeza, redirige a Servicios Escolares o www.udo.mx."
    return f"{_PROMPT_BASE}{seccion}"
