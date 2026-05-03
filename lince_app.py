from __future__ import annotations
import threading
import queue
import uuid
import io
import os
import time
import tempfile
import sqlite3
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile
import pygame
import customtkinter as ctk

from config import OPENAI_API_KEY, OPENAI_MODEL
from universidad_info import get_system_prompt, get_system_prompt_con_contexto
import monitoring

# ── Paleta de colores ─────────────────────────────────────────────────────────
BG            = "#FFFFFF"
CARD          = "#111827"
BLUE          = "#4f46e5"
TEXT          = "#0a0f1e"
MUTED         = "#64748b"
COLOR_USUARIO = "#1e3a5f"
COLOR_BOT     = "#1a1f2e"
RED           = "#dc2626"
GREEN         = "#16a34a"

# ── Configuración de audio ────────────────────────────────────────────────────
SAMPLE_RATE    = 16000  # Hz
VOZ_UMBRAL     = 0.015  # nivel mínimo de volumen para detectar voz
SILENCIO_SEG   = 1.5    # segundos de silencio para cortar la grabación
ESPERA_MAX_SEG = 8.0    # segundos esperando voz antes de abandonar
INACTIVIDAD_S  = 60     # segundos sin actividad para volver a la pantalla de inicio

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Modos de ejecución ────────────────────────────────────────────────────────

@dataclass
class ModoApp:
    nombre:          str
    descripcion:     str
    fullscreen:      bool
    bloquear_cierre: bool
    ancho:           int = 0
    alto:            int = 0
    color_badge:     str = BLUE

MODOS: list[ModoApp] = [
    ModoApp(
        nombre="Normal",
        descripcion="Ventana redimensionable · ideal para desarrollo y pruebas",
        fullscreen=False, bloquear_cierre=False,
        ancho=1100, alto=760, color_badge=BLUE,
    ),
    ModoApp(
        nombre="Compacto",
        descripcion="Ventana pequeña fija · para pantallas o monitores reducidos",
        fullscreen=False, bloquear_cierre=False,
        ancho=820, alto=600, color_badge="#0891b2",
    ),
    ModoApp(
        nombre="Kiosco",
        descripcion="Pantalla completa bloqueada · modo producción en campus",
        fullscreen=True, bloquear_cierre=True,
        color_badge=GREEN,
    ),
]


# ── Selector de modo ──────────────────────────────────────────────────────────

class SelectorModo(ctk.CTk):
    """Ventana pequeña que se muestra al inicio para elegir el modo de ejecución."""

    def __init__(self):
        super().__init__()
        self.modo_elegido: ModoApp | None = None
        self.title("Lince — Seleccionar modo")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self._construir()
        self._centrar(460, 400)

    def _centrar(self, ancho: int, alto: int):
        x = (self.winfo_screenwidth()  - ancho) // 2
        y = (self.winfo_screenheight() - alto)  // 2
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _construir(self):
        ctk.CTkLabel(self, text="🐾", font=("Segoe UI Emoji", 48)).pack(pady=(28, 2))
        ctk.CTkLabel(self, text="Lince Interactivo", font=("Arial", 20, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(self, text="Selecciona el modo de ejecución", font=("Arial", 12), text_color=MUTED).pack(pady=(4, 20))

        for modo in MODOS:
            contenedor = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
            contenedor.pack(fill="x", padx=30, pady=5)
            contenedor.grid_columnconfigure(1, weight=1)

            ctk.CTkFrame(contenedor, fg_color=modo.color_badge, width=6, corner_radius=3
                ).grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12, sticky="ns")

            ctk.CTkLabel(contenedor, text=modo.nombre, font=("Arial", 13, "bold"), text_color=TEXT
                ).grid(row=0, column=1, sticky="w", pady=(10, 0))
            ctk.CTkLabel(contenedor, text=modo.descripcion, font=("Arial", 10), text_color=MUTED, wraplength=280, justify="left"
                ).grid(row=1, column=1, sticky="w", pady=(0, 10))

            ctk.CTkButton(
                contenedor, text="Iniciar", font=("Arial", 12, "bold"),
                fg_color=modo.color_badge, hover_color=BLUE,
                width=80, height=32, corner_radius=16,
                command=lambda m=modo: self._elegir(m),
            ).grid(row=0, column=2, rowspan=2, padx=12)

    def _elegir(self, modo: ModoApp):
        self.modo_elegido = modo
        self.destroy()


# ── Aplicación principal ──────────────────────────────────────────────────────

class LinceApp(ctk.CTk):
    def __init__(self, modo: ModoApp):
        super().__init__()
        self.modo = modo
        self._iniciar_cliente_openai()
        self._iniciar_base_de_datos()
        self._iniciar_estado()
        self._iniciar_ventana()
        self._construir_ui()
        self._mostrar_inicio()
        self._procesar_eventos()
        self._vigilar_inactividad()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _iniciar_cliente_openai(self):
        self.cliente = monitoring.get_openai_client(OPENAI_API_KEY, timeout=25.0)

    def _iniciar_base_de_datos(self):
        self.db = sqlite3.connect("lince_data.db", check_same_thread=False)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role       TEXT,
                content    TEXT,
                ts         DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.commit()

    def _iniciar_estado(self):
        self.prompt     = get_system_prompt()
        self.rag        = None
        self.session_id = str(uuid.uuid4())
        self.historial  : list[dict] = []
        self.grabando   = False
        self.procesando = False
        self.eventos    = queue.Queue()
        self.ultimo_uso = time.time()
        pygame.mixer.init()
        threading.Thread(target=self._iniciar_rag, daemon=True).start()

    def _iniciar_rag(self):
        try:
            from rag_engine import RAGEngine
            self.rag = RAGEngine(OPENAI_API_KEY)
        except Exception:
            pass

    def _iniciar_ventana(self):
        self.title(f"Lince Interactivo — UAdeO  [{self.modo.nombre}]")
        self.configure(fg_color=BG)
        if self.modo.fullscreen:
            self.attributes("-fullscreen", True)
        else:
            self.resizable(True, True)
            self._centrar_ventana(self.modo.ancho, self.modo.alto)
        if self.modo.bloquear_cierre:
            self.bind("<Escape>", lambda _: None)
            self.protocol("WM_DELETE_WINDOW", lambda: None)

    def _centrar_ventana(self, ancho: int, alto: int):
        x = (self.winfo_screenwidth()  - ancho) // 2
        y = (self.winfo_screenheight() - alto)  // 2
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _construir_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._construir_pantalla_inicio()
        self._construir_pantalla_chat()

    def _construir_pantalla_inicio(self):
        self.frame_inicio = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.frame_inicio.grid(row=0, column=0, sticky="nsew")
        self.frame_inicio.grid_columnconfigure(0, weight=1)
        self.frame_inicio.grid_rowconfigure(0, weight=1)

        contenedor = ctk.CTkFrame(self.frame_inicio, fg_color="transparent")
        contenedor.grid(row=0, column=0)

        ctk.CTkLabel(contenedor, text="🐾", font=("Segoe UI Emoji", 72)).pack(pady=(0, 6))
        ctk.CTkLabel(contenedor, text="LINCE INTERACTIVO", font=("Arial", 34, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(contenedor, text="Asistente Virtual · UAdeO Culiacán", font=("Arial", 15), text_color=MUTED).pack(pady=(4, 36))

        self.btn_mic_inicio = ctk.CTkButton(
            contenedor, text="🎤", font=("Segoe UI Emoji", 34),
            width=120, height=120, corner_radius=60,
            fg_color=BLUE, hover_color="#3730a3",
            command=self._mic_inicio,
        )
        self.btn_mic_inicio.pack(pady=10)

        self.lbl_estado_inicio = ctk.CTkLabel(
            contenedor, text="Presiona y habla", font=("Arial", 14), text_color=MUTED,
        )
        self.lbl_estado_inicio.pack(pady=10)

        preguntas_rapidas = ctk.CTkFrame(contenedor, fg_color="transparent")
        preguntas_rapidas.pack(pady=16)
        preguntas = [
            "¿Qué carreras ofrecen?",
            "¿Cómo me inscribo?",
            "¿Cómo saco mi credencial?",
            "¿Qué becas hay?",
        ]
        for pregunta in preguntas:
            ctk.CTkButton(
                preguntas_rapidas, text=pregunta, font=("Arial", 12),
                fg_color=CARD, hover_color="#1e2a3a", text_color=TEXT,
                corner_radius=20, height=36,
                command=lambda p=pregunta: self._pregunta_rapida(p),
            ).pack(side="left", padx=5)

    def _construir_pantalla_chat(self):
        self.frame_chat = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.frame_chat.grid(row=0, column=0, sticky="nsew")
        self.frame_chat.grid_columnconfigure(0, weight=1)
        self.frame_chat.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(self.frame_chat, fg_color=CARD, height=58, corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew")
        encabezado.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            encabezado, text="🐾  Lince Interactivo",
            font=("Arial", 16, "bold"), text_color=TEXT,
        ).grid(row=0, column=0, padx=20, pady=16, sticky="w")
        ctk.CTkButton(
            encabezado, text="↺  Nueva conversación", font=("Arial", 12),
            fg_color="transparent", hover_color="#1e2a3a", text_color=MUTED, width=170,
            command=self._nueva_sesion,
        ).grid(row=0, column=2, padx=16)

        self.scroll = ctk.CTkScrollableFrame(self.frame_chat, fg_color=BG, corner_radius=0)
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        pie = ctk.CTkFrame(self.frame_chat, fg_color=CARD, corner_radius=0)
        pie.grid(row=2, column=0, sticky="ew")
        pie.grid_columnconfigure(1, weight=1)

        self.btn_mic_chat = ctk.CTkButton(
            pie, text="🎤", font=("Segoe UI Emoji", 20),
            width=52, height=52, corner_radius=26,
            fg_color=BLUE, hover_color="#3730a3",
            command=self._mic_chat,
        )
        self.btn_mic_chat.grid(row=0, column=0, padx=(14, 8), pady=14)

        self.entrada = ctk.CTkEntry(
            pie, placeholder_text="Escribe tu pregunta...",
            font=("Arial", 14), height=44, corner_radius=22,
        )
        self.entrada.grid(row=0, column=1, padx=8, pady=14, sticky="ew")
        self.entrada.bind("<Return>", lambda _: self._enviar_texto())

        ctk.CTkButton(
            pie, text="Enviar", font=("Arial", 13, "bold"),
            fg_color=BLUE, hover_color="#3730a3",
            width=80, height=44, corner_radius=22,
            command=self._enviar_texto,
        ).grid(row=0, column=2, padx=(8, 14), pady=14)

        self.lbl_estado_chat = ctk.CTkLabel(pie, text="", font=("Arial", 11), text_color=MUTED)
        self.lbl_estado_chat.grid(row=1, column=0, columnspan=3, pady=(0, 6))

    # ── Navegación entre pantallas ────────────────────────────────────────────

    def _mostrar_inicio(self):
        self.frame_chat.grid_remove()
        self.frame_inicio.grid()
        self._set_estado("Presiona y habla")

    def _mostrar_chat(self):
        self.frame_inicio.grid_remove()
        self.frame_chat.grid()

    def _nueva_sesion(self):
        threading.Thread(target=self._limpiar_sesion_db, args=(self.session_id,), daemon=True).start()
        self.historial = []
        self.session_id = str(uuid.uuid4())
        for widget in self.scroll.winfo_children():
            widget.destroy()
        self._mostrar_inicio()

    # ── Micrófono ─────────────────────────────────────────────────────────────

    def _mic_inicio(self):
        if not self.grabando and not self.procesando:
            self._iniciar_grabacion(desde_inicio=True)

    def _mic_chat(self):
        if not self.grabando and not self.procesando:
            self._iniciar_grabacion(desde_inicio=False)

    def _iniciar_grabacion(self, desde_inicio: bool):
        self.grabando = True
        self.btn_mic_inicio.configure(fg_color=RED)
        self.btn_mic_chat.configure(fg_color=RED)
        self._set_estado("🎤  Habla ahora...")
        threading.Thread(target=self._transcribir_audio, args=(desde_inicio,), daemon=True).start()

    def _transcribir_audio(self, desde_inicio: bool):
        try:
            audio = self._capturar_audio()
            if audio is None:
                self.eventos.put(("rst", "No se detectó voz."))
                return
            self.eventos.put(("st", "Procesando..."))
            audio.name = "audio.wav"
            resultado = self.cliente.audio.transcriptions.create(
                model="whisper-1", file=audio, language="es",
                prompt="UAdeO Culiacán: kardex, credencial, beca, carrera, matrícula.",
            )
            texto = resultado.text.strip()
            if texto:
                self.eventos.put(("env", (texto, desde_inicio)))
            else:
                self.eventos.put(("rst", "No te entendí."))
        except Exception as e:
            self.eventos.put(("rst", f"Error mic: {e}"))

    def _capturar_audio(self) -> io.BytesIO | None:
        # Detección de actividad de voz: graba mientras hay sonido y corta al silencio
        frames = []
        hablando = False
        contador_silencio = 0
        contador_espera   = 0
        duracion_chunk = 0.1
        max_silencio   = int(SILENCIO_SEG / duracion_chunk)
        max_espera     = int(ESPERA_MAX_SEG / duracion_chunk)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
            while True:
                datos, _ = stream.read(int(SAMPLE_RATE * duracion_chunk))
                volumen = float(np.sqrt(np.mean(datos**2)))

                if volumen > VOZ_UMBRAL:
                    hablando = True
                    contador_silencio = 0
                    frames.append(datos.copy())
                elif hablando:
                    frames.append(datos.copy())
                    contador_silencio += 1
                    if contador_silencio >= max_silencio:
                        break
                else:
                    contador_espera += 1
                    if contador_espera >= max_espera:
                        return None

        audio = np.concatenate(frames)
        buffer = io.BytesIO()
        wavfile.write(buffer, SAMPLE_RATE, (audio * 32767).astype(np.int16))
        buffer.seek(0)
        return buffer

    # ── Procesamiento del chat ────────────────────────────────────────────────

    def _pregunta_rapida(self, texto: str):
        self._procesar(texto, desde_inicio=True)

    def _enviar_texto(self):
        texto = self.entrada.get().strip()
        if texto and not self.procesando:
            self.entrada.delete(0, "end")
            self._procesar(texto, desde_inicio=False)

    def _procesar(self, texto: str, desde_inicio: bool):
        if desde_inicio:
            self._mostrar_chat()
        self.procesando = True
        self.ultimo_uso = time.time()
        self._agregar_mensaje(texto, "user")
        self._set_estado("Lince está pensando...")
        threading.Thread(target=self._responder, args=(texto,), daemon=True).start()

    def _responder(self, texto: str):
        try:
            self.historial.append({"role": "user", "content": texto})
            if self.rag and self.rag.disponible:
                contexto_conv = " ".join(
                    m["content"] for m in self.historial[-6:] if m["role"] == "user"
                )
                contexto = self.rag.buscar(f"{contexto_conv} {texto}".strip())
                prompt = get_system_prompt_con_contexto(contexto)
            else:
                prompt = self.prompt

            with monitoring.TraceLlamada(self.session_id, texto) as trace:
                respuesta_api = self.cliente.chat.completions.create(
                    model=OPENAI_MODEL,
                    temperature=0.7,
                    max_tokens=700,
                    messages=[{"role": "system", "content": prompt}] + self.historial[-20:],
                )
                respuesta = respuesta_api.choices[0].message.content or ""
                uso = respuesta_api.usage
                trace.registrar_respuesta(
                    respuesta,
                    tokens_entrada=uso.prompt_tokens if uso else 0,
                    tokens_salida=uso.completion_tokens if uso else 0,
                )

            self.historial.append({"role": "assistant", "content": respuesta})
            threading.Thread(
                target=self._guardar_mensajes,
                args=(self.session_id, texto, respuesta),
                daemon=True,
            ).start()
            self.eventos.put(("resp", respuesta))
        except Exception as e:
            self.eventos.put(("err", str(e)))

    def _reproducir_voz(self, texto: str):
        path = None
        try:
            audio_mp3 = self.cliente.audio.speech.create(
                model="tts-1", voice="ash", input=texto,
                response_format="mp3", speed=1.2,
            ).read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as archivo:
                archivo.write(audio_mp3)
                path = archivo.name
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.unload()
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self.eventos.put(("tts_end", None))

    # ── Base de datos ─────────────────────────────────────────────────────────

    def _guardar_mensajes(self, session_id: str, texto_usuario: str, respuesta: str):
        self.db.executemany(
            "INSERT INTO conversaciones (session_id, role, content) VALUES (?,?,?)",
            [(session_id, "user", texto_usuario), (session_id, "assistant", respuesta)],
        )
        self.db.commit()

    def _limpiar_sesion_db(self, session_id: str):
        self.db.execute("DELETE FROM conversaciones WHERE session_id=?", (session_id,))
        self.db.commit()

    # ── Helpers de UI ─────────────────────────────────────────────────────────

    def _agregar_mensaje(self, texto: str, rol: str):
        es_usuario = rol == "user"
        fila = len(self.scroll.winfo_children())
        burbuja = ctk.CTkFrame(
            self.scroll,
            fg_color=COLOR_USUARIO if es_usuario else COLOR_BOT,
            corner_radius=14,
        )
        burbuja.grid(
            row=fila, column=0,
            sticky="e" if es_usuario else "w",
            padx=(80, 12) if es_usuario else (12, 80),
            pady=5,
        )
        prefijo = "Tú  " if es_usuario else "🐾 Lince  "
        ctk.CTkLabel(
            burbuja, text=prefijo + texto,
            font=("Arial", 13), text_color=TEXT,
            wraplength=520, justify="left",
        ).pack(padx=16, pady=10)
        self.scroll.after(120, lambda: self.scroll._parent_canvas.yview_moveto(1.0))

    def _set_estado(self, mensaje: str):
        self.lbl_estado_inicio.configure(text=mensaje)
        self.lbl_estado_chat.configure(text=mensaje)

    def _restaurar_microfono(self):
        self.btn_mic_inicio.configure(fg_color=BLUE)
        self.btn_mic_chat.configure(fg_color=BLUE)
        self.grabando = False

    # ── Loop de eventos ───────────────────────────────────────────────────────

    def _procesar_eventos(self):
        try:
            while True:
                evento, datos = self.eventos.get_nowait()
                if evento == "env":
                    self._restaurar_microfono()
                    self._procesar(*datos)
                elif evento == "resp":
                    self._agregar_mensaje(datos, "bot")
                    self._set_estado("🔊  Hablando...")
                    threading.Thread(target=self._reproducir_voz, args=(datos,), daemon=True).start()
                elif evento == "tts_end":
                    self._set_estado("")
                    self.procesando = False
                elif evento == "st":
                    self._set_estado(datos)
                elif evento == "rst":
                    self._set_estado(datos)
                    self._restaurar_microfono()
                    self.procesando = False
                elif evento == "err":
                    self._agregar_mensaje("Hubo un error. Intenta de nuevo.", "bot")
                    self._set_estado("")
                    self.procesando = False
        except queue.Empty:
            pass
        self.after(80, self._procesar_eventos)

    # ── Vigilancia de inactividad ─────────────────────────────────────────────

    def _vigilar_inactividad(self):
        inactivo = time.time() - self.ultimo_uso > INACTIVIDAD_S
        en_chat  = self.frame_chat.winfo_ismapped()
        if inactivo and en_chat and not self.procesando:
            self._nueva_sesion()
        self.after(5000, self._vigilar_inactividad)


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # El flag --kiosco lo usa KIOSCO.bat para saltar el selector
    if "--kiosco" in sys.argv:
        modo = next(m for m in MODOS if m.nombre == "Kiosco")
    else:
        selector = SelectorModo()
        selector.mainloop()
        modo = selector.modo_elegido

    if modo:
        try:
            LinceApp(modo).mainloop()
        finally:
            monitoring.cerrar()
