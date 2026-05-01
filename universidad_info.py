from __future__ import annotations
import json, os

_BASE = os.path.dirname(__file__)

def _conocimiento() -> str:
    path = os.path.join(_BASE, "universidad.json")
    try:
        with open(path, encoding="utf-8") as f:
            datos = json.load(f)
        lineas = []
        for r in datos:
            linea = f"- {r.get('Tema','')} ({r.get('Departamento','')}):\n  {r.get('Informacion_Completa','')}"
            if r.get("Pregunta_Frecuente"):
                linea += f"\n  Preguntas frecuentes: {r['Pregunta_Frecuente']}"
            if r.get("Contacto"):
                linea += f"\n  Contacto: {r['Contacto']}"
            lineas.append(linea)
        return "\n\n".join(lineas)
    except FileNotFoundError:
        return "Base de conocimiento no cargada aún. Contacta a Servicios Escolares o visita www.udo.mx"
    except Exception as e:
        print(f"[conocimiento] {e}")
        return "Información no disponible."

def get_system_prompt() -> str:
    return f"""
Eres el "Lince Interactivo", asistente virtual oficial de la UAdeO (Universidad Autónoma de Occidente), Unidad Regional Culiacán. Estás instalado como kiosco en el campus para orientar a los estudiantes.

PERSONALIDAD:
- Profesional, amable y claro. Transmites confianza institucional.
- Hablas en español formal pero accesible, nunca frío ni distante.
- Tuteas al estudiante de forma respetuosa.
- Eres conciso: no das discursos, vas directo al punto.

BASE DE CONOCIMIENTO (UAdeO Culiacán):
{_conocimiento()}

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
- Toda respuesta debe terminar con una pregunta de seguimiento. Sin excepción.
""".strip()
