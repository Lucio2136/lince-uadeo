from __future__ import annotations
import customtkinter as ctk
import threading, queue, uuid, io, os, time, tempfile
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile
import pygame
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
from config import OPENAI_API_KEY, OPENAI_MODEL, SUPABASE_URL, SUPABASE_ANON_KEY
from universidad_info import get_system_prompt

BG     = "#0a0f1e"
CARD   = "#111827"
BLUE   = "#4f46e5"
TEXT   = "#e2e8f0"
MUTED  = "#64748b"
U_CLR  = "#1e3a5f"
B_CLR  = "#1a1f2e"
RED    = "#dc2626"

SR        = 16000    # sample rate
THRESHOLD = 0.015    # detección de voz
SIL_SEC   = 1.5      # silencio para cortar grabación
MAX_WAIT  = 8.0      # espera máxima antes de hablar
INACT_S   = 60       # inactividad para volver al inicio

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class LinceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.openai   = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY, timeout=25.0)
        self.supabase = create_client(os.getenv("SUPABASE_URL", SUPABASE_URL),
                                      os.getenv("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY))
        self.prompt     = get_system_prompt()
        self.session_id = str(uuid.uuid4())
        self.historial  : list = []
        self.grabando   = False
        self.procesando = False
        self.q          = queue.Queue()
        self._ultimo    = time.time()

        pygame.mixer.init()
        self.title("Lince Interactivo — UAdeO")
        self.geometry("960x680")
        self.configure(fg_color=BG)
        self.minsize(800, 560)

        self._ui()
        self._landing()
        self._poll()
        self._inact_watch()

    # ── UI ────────────────────────────────────────────────────

    def _ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LANDING
        self.fl = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.fl.grid(row=0, column=0, sticky="nsew")
        self.fl.grid_columnconfigure(0, weight=1)
        self.fl.grid_rowconfigure(0, weight=1)

        c = ctk.CTkFrame(self.fl, fg_color="transparent")
        c.grid(row=0, column=0)
        ctk.CTkLabel(c, text="🐾", font=("Segoe UI Emoji", 72)).pack(pady=(0,6))
        ctk.CTkLabel(c, text="LINCE INTERACTIVO", font=("Arial",34,"bold"), text_color=TEXT).pack()
        ctk.CTkLabel(c, text="Asistente Virtual · UAdeO Culiacán", font=("Arial",15), text_color=MUTED).pack(pady=(4,36))

        self.btn_mic_l = ctk.CTkButton(c, text="🎤", font=("Segoe UI Emoji",34),
            width=120, height=120, corner_radius=60, fg_color=BLUE, hover_color="#3730a3",
            command=self._mic_l)
        self.btn_mic_l.pack(pady=10)

        self.lbl_l = ctk.CTkLabel(c, text="Presiona y habla", font=("Arial",14), text_color=MUTED)
        self.lbl_l.pack(pady=10)

        chips = ctk.CTkFrame(c, fg_color="transparent")
        chips.pack(pady=16)
        for t in ["¿Qué carreras ofrecen?","¿Cómo me inscribo?","¿Cómo saco mi credencial?","¿Qué becas hay?"]:
            ctk.CTkButton(chips, text=t, font=("Arial",12), fg_color=CARD, hover_color="#1e2a3a",
                text_color=TEXT, corner_radius=20, height=36,
                command=lambda x=t: self._chip(x)).pack(side="left", padx=5)

        # CHAT
        self.fc = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.fc.grid(row=0, column=0, sticky="nsew")
        self.fc.grid_columnconfigure(0, weight=1)
        self.fc.grid_rowconfigure(1, weight=1)

        h = ctk.CTkFrame(self.fc, fg_color=CARD, height=58, corner_radius=0)
        h.grid(row=0, column=0, sticky="ew")
        h.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(h, text="🐾  Lince Interactivo", font=("Arial",16,"bold"), text_color=TEXT
            ).grid(row=0, column=0, padx=20, pady=16, sticky="w")
        ctk.CTkButton(h, text="↺  Nueva conversación", font=("Arial",12),
            fg_color="transparent", hover_color="#1e2a3a", text_color=MUTED, width=170,
            command=self._reset).grid(row=0, column=2, padx=16)

        self.scroll = ctk.CTkScrollableFrame(self.fc, fg_color=BG, corner_radius=0)
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        f = ctk.CTkFrame(self.fc, fg_color=CARD, corner_radius=0)
        f.grid(row=2, column=0, sticky="ew")
        f.grid_columnconfigure(1, weight=1)

        self.btn_mic_c = ctk.CTkButton(f, text="🎤", font=("Segoe UI Emoji",20),
            width=52, height=52, corner_radius=26, fg_color=BLUE, hover_color="#3730a3",
            command=self._mic_c)
        self.btn_mic_c.grid(row=0, column=0, padx=(14,8), pady=14)

        self.entry = ctk.CTkEntry(f, placeholder_text="Escribe tu pregunta...",
            font=("Arial",14), height=44, corner_radius=22)
        self.entry.grid(row=0, column=1, padx=8, pady=14, sticky="ew")
        self.entry.bind("<Return>", lambda _: self._enviar())

        ctk.CTkButton(f, text="Enviar", font=("Arial",13,"bold"),
            fg_color=BLUE, hover_color="#3730a3", width=80, height=44, corner_radius=22,
            command=self._enviar).grid(row=0, column=2, padx=(8,14), pady=14)

        self.lbl_c = ctk.CTkLabel(f, text="", font=("Arial",11), text_color=MUTED)
        self.lbl_c.grid(row=1, column=0, columnspan=3, pady=(0,6))

    # ── Vistas ───────────────────────────────────────────────

    def _landing(self):
        self.fc.grid_remove(); self.fl.grid()
        self._st("Presiona y habla")

    def _chat(self):
        self.fl.grid_remove(); self.fc.grid()

    def _reset(self):
        sid = self.session_id
        threading.Thread(target=lambda: self.supabase.table("conversaciones")
            .delete().eq("session_id", sid).execute(), daemon=True).start()
        self.historial = []; self.session_id = str(uuid.uuid4())
        for w in self.scroll.winfo_children(): w.destroy()
        self._landing()

    # ── Micrófono ────────────────────────────────────────────

    def _mic_l(self):
        if not self.grabando and not self.procesando: self._grabar(True)

    def _mic_c(self):
        if not self.grabando and not self.procesando: self._grabar(False)

    def _grabar(self, landing: bool):
        self.grabando = True
        self.btn_mic_l.configure(fg_color=RED)
        self.btn_mic_c.configure(fg_color=RED)
        self._st("🎤  Habla ahora...")
        threading.Thread(target=self._grabar_t, args=(landing,), daemon=True).start()

    def _grabar_t(self, landing: bool):
        try:
            buf = self._vad()
            if buf is None:
                self.q.put(("rst", "No se detectó voz.")); return
            self.q.put(("st", "Procesando..."))
            buf.name = "audio.wav"
            t = self.openai.audio.transcriptions.create(
                model="whisper-1", file=buf, language="es",
                prompt="UAdeO Culiacán: kardex, credencial, beca, carrera, matrícula.")
            texto = t.text.strip()
            self.q.put(("env", (texto, landing)) if texto else ("rst", "No te entendí."))
        except Exception as e:
            self.q.put(("rst", f"Error mic: {e}"))

    def _vad(self) -> io.BytesIO | None:
        chunks, hablando, sil, esp = [], False, 0, 0
        chunk = 0.1
        max_sil = int(SIL_SEC / chunk)
        max_esp = int(MAX_WAIT / chunk)
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32") as s:
            while True:
                d, _ = s.read(int(SR * chunk))
                v = float(np.sqrt(np.mean(d**2)))
                if v > THRESHOLD:
                    hablando = True; sil = 0; chunks.append(d.copy())
                elif hablando:
                    chunks.append(d.copy()); sil += 1
                    if sil >= max_sil: break
                else:
                    esp += 1
                    if esp >= max_esp: return None
        audio = np.concatenate(chunks)
        buf = io.BytesIO()
        wavfile.write(buf, SR, (audio * 32767).astype(np.int16))
        buf.seek(0)
        return buf

    # ── Chat ─────────────────────────────────────────────────

    def _chip(self, t): self._proc(t, True)

    def _enviar(self):
        t = self.entry.get().strip()
        if t and not self.procesando:
            self.entry.delete(0, "end"); self._proc(t, False)

    def _proc(self, texto: str, landing: bool):
        if landing: self._chat()
        self.procesando = True; self._ultimo = time.time()
        self._burbuja(texto, "user"); self._st("Lince está pensando...")
        threading.Thread(target=self._chat_t, args=(texto,), daemon=True).start()

    def _chat_t(self, texto: str):
        try:
            self.historial.append({"role": "user", "content": texto})
            r = self.openai.chat.completions.create(
                model=OPENAI_MODEL, temperature=0.7, max_tokens=400,
                messages=[{"role":"system","content":self.prompt}] + self.historial[-20:])
            resp = r.choices[0].message.content or ""
            self.historial.append({"role": "assistant", "content": resp})
            threading.Thread(target=lambda: self.supabase.table("conversaciones").insert([
                {"session_id": self.session_id, "role": "user",      "content": texto},
                {"session_id": self.session_id, "role": "assistant", "content": resp},
            ]).execute(), daemon=True).start()
            self.q.put(("resp", resp))
        except Exception as e:
            self.q.put(("err", str(e)))

    def _tts_t(self, texto: str):
        try:
            data = self.openai.audio.speech.create(
                model="tts-1", voice="ash", input=texto,
                response_format="mp3", speed=1.2).read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                f.write(data); path = f.name
            pygame.mixer.music.load(path); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): time.sleep(0.1)
            pygame.mixer.music.unload(); os.unlink(path)
        except Exception as e:
            print(f"[TTS] {e}")
        finally:
            self.q.put(("tts_end", None))

    # ── UI helpers ───────────────────────────────────────────

    def _burbuja(self, texto: str, rol: str):
        user = rol == "user"
        row  = len(self.scroll.winfo_children())
        f = ctk.CTkFrame(self.scroll, fg_color=U_CLR if user else B_CLR, corner_radius=14)
        f.grid(row=row, column=0,
               sticky="e" if user else "w",
               padx=(80,12) if user else (12,80), pady=5)
        ctk.CTkLabel(f, text=("Tú  " if user else "🐾 Lince  ") + texto,
            font=("Arial",13), text_color=TEXT, wraplength=520, justify="left").pack(padx=16, pady=10)
        self.scroll.after(120, lambda: self.scroll._parent_canvas.yview_moveto(1.0))

    def _st(self, t: str):
        self.lbl_l.configure(text=t)
        self.lbl_c.configure(text=t)

    def _mics_reset(self):
        self.btn_mic_l.configure(fg_color=BLUE)
        self.btn_mic_c.configure(fg_color=BLUE)
        self.grabando = False

    # ── Queue ────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                ev, data = self.q.get_nowait()
                if ev == "env":
                    self._mics_reset(); self._proc(*data)
                elif ev == "resp":
                    self._burbuja(data, "bot"); self._st("🔊  Hablando...")
                    threading.Thread(target=self._tts_t, args=(data,), daemon=True).start()
                elif ev == "tts_end":
                    self._st(""); self.procesando = False
                elif ev == "st":
                    self._st(data)
                elif ev == "rst":
                    self._st(data); self._mics_reset(); self.procesando = False
                elif ev == "err":
                    self._burbuja("Hubo un error. Intenta de nuevo.", "bot")
                    self._st(""); self.procesando = False
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ── Inactividad ──────────────────────────────────────────

    def _inact_watch(self):
        if time.time() - self._ultimo > INACT_S and self.fc.winfo_ismapped() and not self.procesando:
            self._reset()
        self.after(5000, self._inact_watch)


if __name__ == "__main__":
    LinceApp().mainloop()
