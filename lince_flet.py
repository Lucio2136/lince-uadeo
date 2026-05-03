from __future__ import annotations
import threading
import uuid
import io
import os
import time
import tempfile
import sqlite3

import flet as ft
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile
import pygame

from config import OPENAI_API_KEY, OPENAI_MODEL
from universidad_info import get_system_prompt, get_system_prompt_con_contexto
import monitoring

# ── Paleta institucional UAdeO ────────────────────────────────────────────────
TINTO      = "#9D253C"   # Primario UAdeO (Pantone 1945 U)
TINTO_OSC  = "#6E1927"   # Oscuro — gradientes y profundidad
ORO        = "#D0A76B"   # Acento dorado
ORO_SUAVE  = "#F5EDD8"   # Dorado suave — hover sobre fondo claro
GRIS       = "#797F89"   # Secundario (Pantone 7545 C)
GRIS_MED   = "#BEC3CC"   # Bordes y separadores
BLANCO     = "#FFFFFF"
NEGRO      = "#1C1C2E"   # Texto principal (azul oscuro)
GRIS_SUAVE = "#F0F2F7"   # Fondo burbuja bot y campos
FONDO_APP  = "#FAFAFA"
FONDO_CHAT = "#ECEEF5"   # Fondo pantalla chat
SUPERFICIE = "#FFFFFF"   # Superficies de tarjetas
EXITO      = "#16A34A"
ERROR      = "#DC2626"

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_PIN      = "1234"
ADMIN_TAPS_REQ = 5

# ── Audio ─────────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000
VOZ_UMBRAL     = 0.015
SILENCIO_SEG   = 1.5
ESPERA_MAX_SEG = 8.0
INACTIVIDAD_S  = 60


class LinceApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self._iniciar_cliente()
        self._iniciar_db()
        self._iniciar_estado()
        self._configurar_pagina()
        self._construir_ui()
        self._mostrar_inicio()
        self._iniciar_animacion()
        self._vigilar_inactividad()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _iniciar_cliente(self):
        self.cliente = monitoring.get_openai_client(OPENAI_API_KEY, timeout=25.0)

    def _iniciar_db(self):
        self.db = sqlite3.connect("lince_data.db", check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role       TEXT,
                content    TEXT,
                ts         DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
        """)
        self.db.commit()

    def _iniciar_estado(self):
        self.prompt     = get_system_prompt()
        self.rag        = None
        self.session_id = str(uuid.uuid4())
        self.historial: list[dict] = []
        self.grabando   = False
        self.procesando = False
        self.ultimo_uso = time.time()
        self._admin_taps      = 0
        self._admin_tap_timer = None
        self._mic_test_activo = False
        self._error_logs: list[str] = []
        self.voz_umbral = self._cfg_leer("voz_umbral", VOZ_UMBRAL, float)
        self.admin_pin  = self._cfg_leer("admin_pin",  ADMIN_PIN,  str)
        self.voz_tts    = self._cfg_leer("voz_tts",    "ash",      str)
        pygame.mixer.init()
        threading.Thread(target=self._iniciar_rag, daemon=True).start()

    def _iniciar_rag(self):
        try:
            from rag_engine import RAGEngine
            self.rag = RAGEngine(OPENAI_API_KEY)
        except Exception:
            pass

    def _configurar_pagina(self):
        p = self.page
        p.title                = "Lince Interactivo — UAdeO"
        p.bgcolor              = FONDO_APP
        p.padding              = 0
        p.theme = ft.Theme(
            color_scheme_seed=TINTO,
            font_family="Roboto",
        )
        p.window.full_screen   = True
        p.window.prevent_close = True
        p.window.always_on_top = True
        p.window.movable       = False
        p.window.resizable     = False
        p.on_window_event      = lambda e: None

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _construir_ui(self):
        self._construir_appbar()
        self._construir_vista_inicio()
        self._construir_vista_chat()
        self._construir_dialogo_pin()
        self._construir_panel_admin()

        self.stack = ft.Stack([self.vista_inicio, self.vista_chat], expand=True)
        self.page.appbar = self.appbar
        self.page.overlay.extend([self.dlg_pin, self.dlg_admin])
        self.page.add(self.stack)

    # ── AppBar ────────────────────────────────────────────────────────────────

    def _construir_appbar(self):
        self.btn_nueva_sesion = ft.TextButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ADD_COMMENT_ROUNDED, size=14, color=ORO),
                    ft.Text("Nueva sesión", color=ORO, size=12,
                            weight=ft.FontWeight.W_600),
                ],
                spacing=5,
                tight=True,
            ),
            style=ft.ButtonStyle(
                overlay_color=ft.Colors.with_opacity(0.18, BLANCO),
                padding=ft.padding.symmetric(horizontal=14, vertical=7),
                shape=ft.RoundedRectangleBorder(radius=18),
                side=ft.BorderSide(1, ft.Colors.with_opacity(0.45, ORO)),
            ),
            visible=False,
            on_click=lambda _: self._nueva_sesion(),
        )

        logo = ft.IconButton(
            icon=ft.Icons.SCHOOL_ROUNDED,
            icon_color=ORO,
            icon_size=24,
            tooltip=None,
            style=ft.ButtonStyle(
                overlay_color=ft.Colors.with_opacity(0.0, BLANCO),
                padding=4,
            ),
            on_click=lambda _: self._tap_logo(),
        )

        self.appbar = ft.AppBar(
            leading=logo,
            leading_width=48,
            title=ft.Column(
                controls=[
                    ft.Text(
                        "Lince Interactivo",
                        color=BLANCO,
                        weight=ft.FontWeight.BOLD,
                        size=17,
                    ),
                    ft.Text(
                        "Universidad Autónoma de Occidente",
                        color=ft.Colors.with_opacity(0.72, ORO),
                        size=11,
                        weight=ft.FontWeight.W_400,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            center_title=False,
            bgcolor=TINTO,
            actions=[self.btn_nueva_sesion, ft.Container(width=10)],
            elevation=3,
        )

    # ── Vista inicio ──────────────────────────────────────────────────────────

    def _get_saludo(self) -> str:
        hora = time.localtime().tm_hour
        if 6 <= hora < 12:
            return "Buenos días"
        elif 12 <= hora < 20:
            return "Buenas tardes"
        return "Buenas noches"

    def _construir_vista_inicio(self):
        # ── Textos dinámicos ──────────────────────────────────────────────────
        self.lbl_saludo = ft.Text(
            self._get_saludo(),
            size=36,
            weight=ft.FontWeight.W_700,
            color=BLANCO,
            text_align=ft.TextAlign.CENTER,
            animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
        )
        self.lbl_reloj = ft.Text(
            time.strftime("%H:%M"),
            size=64,
            color=ORO,
            weight=ft.FontWeight.W_300,
            text_align=ft.TextAlign.CENTER,
        )
        self.lbl_estado_inicio = ft.Text(
            "Toca el micrófono para hablar",
            color=ft.Colors.with_opacity(0.75, BLANCO),
            size=14,
            text_align=ft.TextAlign.CENTER,
        )

        # ── Botón micrófono (blanco, ícono tinto — invertido sobre el fondo) ──
        self.btn_mic_inicio = ft.IconButton(
            icon=ft.Icons.MIC_ROUNDED,
            icon_color=TINTO,
            icon_size=48,
            tooltip="Hablar con Lince",
            style=ft.ButtonStyle(
                bgcolor={"": BLANCO, "hovered": ORO_SUAVE},
                shape=ft.CircleBorder(),
                padding=26,
                overlay_color=ft.Colors.with_opacity(0.10, TINTO),
                shadow_color=ft.Colors.with_opacity(0.40, NEGRO),
                elevation={"": 8, "hovered": 14, "pressed": 4},
            ),
            animate_scale=ft.Animation(1100, ft.AnimationCurve.EASE_IN_OUT),
            on_click=lambda _: self._mic_inicio(),
        )

        # ── Anillos pulsantes ─────────────────────────────────────────────────
        self.ring_pulso = ft.Container(
            width=155,
            height=155,
            border=ft.border.all(2.5, ft.Colors.with_opacity(0.45, BLANCO)),
            border_radius=78,
            opacity=0.20,
            animate_opacity=ft.Animation(1100, ft.AnimationCurve.EASE_IN_OUT),
            animate_scale=ft.Animation(1100, ft.AnimationCurve.EASE_IN_OUT),
        )
        self.ring_oro = ft.Container(
            width=195,
            height=195,
            border=ft.border.all(1.5, ft.Colors.with_opacity(0.50, ORO)),
            border_radius=98,
            opacity=0.18,
            animate_opacity=ft.Animation(1400, ft.AnimationCurve.EASE_IN_OUT),
            animate_scale=ft.Animation(1400, ft.AnimationCurve.EASE_IN_OUT),
        )

        # Stack centrado: ring externo → ring interno → botón
        # btn = ~100px (48 icon + 2*26 padding), ring_pulso = 155, ring_oro = 195
        mic_area = ft.Stack(
            controls=[
                ft.Container(content=self.ring_oro,       left=0,  top=0),
                ft.Container(content=self.ring_pulso,     left=20, top=20),
                ft.Container(content=self.btn_mic_inicio, left=48, top=48),
            ],
            width=195,
            height=195,
        )

        # ── Chips de preguntas rápidas ────────────────────────────────────────
        preguntas = [
            "¿Qué carreras ofrecen?",
            "¿Cómo me inscribo?",
            "¿Cómo saco mi credencial?",
            "¿Qué becas hay?",
        ]
        chips = ft.Row(
            controls=[
                ft.OutlinedButton(
                    content=ft.Text(p, size=12, color=BLANCO),
                    style=ft.ButtonStyle(
                        side=ft.BorderSide(
                            width=1, color=ft.Colors.with_opacity(0.55, BLANCO)
                        ),
                        shape=ft.RoundedRectangleBorder(radius=20),
                        padding=ft.padding.symmetric(horizontal=16, vertical=9),
                        overlay_color=ft.Colors.with_opacity(0.12, BLANCO),
                    ),
                    on_click=lambda _, q=p: self._pregunta_rapida(q),
                )
                for p in preguntas
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
            spacing=10,
            run_spacing=10,
        )

        # ── Área de marca/logo ────────────────────────────────────────────────
        marca = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.SCHOOL_ROUNDED, color=TINTO, size=36
                    ),
                    width=68,
                    height=68,
                    bgcolor=BLANCO,
                    border_radius=34,
                    alignment=ft.Alignment(0, 0),
                    shadow=ft.BoxShadow(
                        blur_radius=16,
                        color=ft.Colors.with_opacity(0.30, NEGRO),
                        offset=ft.Offset(0, 4),
                    ),
                ),
                ft.Container(height=6),
                ft.Text(
                    "LINCE",
                    size=13,
                    weight=ft.FontWeight.W_900,
                    color=ft.Colors.with_opacity(0.95, BLANCO),
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Asistente Virtual · UAdeO Culiacán",
                    size=11,
                    color=ft.Colors.with_opacity(0.60, BLANCO),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        # ── Separador decorativo ──────────────────────────────────────────────
        separador = ft.Row(
            controls=[
                ft.Container(
                    width=40, height=1,
                    bgcolor=ft.Colors.with_opacity(0.30, ORO),
                ),
                ft.Container(
                    width=6, height=6,
                    bgcolor=ORO,
                    border_radius=3,
                    opacity=0.70,
                ),
                ft.Container(
                    width=40, height=1,
                    bgcolor=ft.Colors.with_opacity(0.30, ORO),
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        )

        # ── Columna principal ─────────────────────────────────────────────────
        contenido = ft.Column(
            controls=[
                ft.Container(height=16),
                marca,
                ft.Container(height=10),
                separador,
                ft.Container(height=10),
                self.lbl_saludo,
                self.lbl_reloj,
                ft.Text(
                    "UAdeO · Unidad Regional Culiacán",
                    size=12,
                    color=ft.Colors.with_opacity(0.55, BLANCO),
                    text_align=ft.TextAlign.CENTER,
                    italic=True,
                ),
                ft.Container(height=20),
                mic_area,
                ft.Container(height=10),
                self.lbl_estado_inicio,
                ft.Container(height=28),
                chips,
                ft.Container(height=20),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            scroll=ft.ScrollMode.HIDDEN,
        )

        self.vista_inicio = ft.Container(
            content=contenido,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(0.2, -1),
                end=ft.Alignment(-0.2, 1),
                colors=[TINTO_OSC, TINTO, "#A82B48"],
            ),
            alignment=ft.Alignment(0, 0),
            expand=True,
            visible=False,
        )

    # ── Vista chat ────────────────────────────────────────────────────────────

    def _construir_vista_chat(self):
        self.lbl_estado_chat = ft.Text(
            "", color=GRIS, size=12, italic=True,
            text_align=ft.TextAlign.CENTER,
        )

        self.chat_list = ft.ListView(
            expand=True,
            spacing=10,
            padding=ft.padding.symmetric(horizontal=18, vertical=16),
            auto_scroll=True,
        )

        self.btn_mic_chat = ft.IconButton(
            icon=ft.Icons.MIC_ROUNDED,
            icon_color=BLANCO,
            icon_size=20,
            tooltip="Hablar",
            style=ft.ButtonStyle(
                bgcolor={"": TINTO, "hovered": ORO},
                shape=ft.CircleBorder(),
                padding=10,
                overlay_color=ft.Colors.with_opacity(0.18, BLANCO),
                elevation={"": 2, "hovered": 4, "pressed": 0},
                shadow_color=ft.Colors.with_opacity(0.25, TINTO),
            ),
            on_click=lambda _: self._mic_chat(),
        )

        self.campo_texto = ft.TextField(
            hint_text="Escribe tu pregunta...",
            hint_style=ft.TextStyle(color=GRIS_MED, size=14),
            expand=True,
            border_radius=26,
            border_color="transparent",
            focused_border_color=TINTO,
            bgcolor=GRIS_SUAVE,
            focused_bgcolor=GRIS_SUAVE,
            cursor_color=TINTO,
            content_padding=ft.padding.symmetric(horizontal=20, vertical=14),
            text_size=14,
            text_style=ft.TextStyle(color=NEGRO),
            on_submit=lambda _: self._enviar_texto(),
        )

        btn_enviar = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=BLANCO,
            icon_size=20,
            tooltip="Enviar",
            style=ft.ButtonStyle(
                bgcolor={"": TINTO, "hovered": TINTO_OSC},
                shape=ft.CircleBorder(),
                padding=10,
                overlay_color=ft.Colors.with_opacity(0.18, BLANCO),
                elevation={"": 2, "hovered": 4, "pressed": 0},
                shadow_color=ft.Colors.with_opacity(0.25, TINTO),
            ),
            on_click=lambda _: self._enviar_texto(),
        )

        barra_estado = ft.Container(
            content=self.lbl_estado_chat,
            alignment=ft.Alignment(0, 0),
            height=18,
        )

        pie = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self.btn_mic_chat,
                            self.campo_texto,
                            btn_enviar,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    barra_estado,
                ],
                spacing=4,
            ),
            bgcolor=SUPERFICIE,
            padding=ft.padding.only(left=14, right=14, top=12, bottom=12),
            shadow=ft.BoxShadow(
                blur_radius=20,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.10, NEGRO),
                offset=ft.Offset(0, -4),
            ),
        )

        self.vista_chat = ft.Container(
            content=ft.Column(
                controls=[self.chat_list, pie],
                spacing=0,
                expand=True,
            ),
            bgcolor=FONDO_CHAT,
            expand=True,
            visible=False,
        )

    # ── Diálogo PIN ───────────────────────────────────────────────────────────

    def _construir_dialogo_pin(self):
        self.campo_pin = ft.TextField(
            label="PIN de administrador",
            password=True,
            can_reveal_password=True,
            width=280,
            border_color=GRIS_MED,
            focused_border_color=TINTO,
            label_style=ft.TextStyle(color=GRIS),
            cursor_color=TINTO,
            border_radius=12,
            on_submit=lambda _: self._verificar_pin(),
        )
        self.lbl_pin_error = ft.Text("", color=ERROR, size=12)

        self.dlg_pin = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.LOCK_ROUNDED, color=BLANCO, size=18
                        ),
                        width=34, height=34,
                        bgcolor=TINTO,
                        border_radius=17,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text(
                        "  Acceso Administrador",
                        weight=ft.FontWeight.BOLD,
                        color=NEGRO,
                        size=16,
                    ),
                ],
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Ingresa el PIN para continuar.",
                        color=GRIS,
                        size=13,
                    ),
                    ft.Container(height=8),
                    self.campo_pin,
                    self.lbl_pin_error,
                ],
                tight=True,
                spacing=6,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancelar", color=GRIS),
                    on_click=lambda _: self._cerrar_pin(),
                ),
                ft.ElevatedButton(
                    content="Entrar",
                    color=BLANCO,
                    bgcolor=TINTO,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                        overlay_color=ft.Colors.with_opacity(0.15, BLANCO),
                    ),
                    on_click=lambda _: self._verificar_pin(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=18),
        )

    # ── Panel de admin ────────────────────────────────────────────────────────

    def _construir_panel_admin(self):
        # ── Pestaña General ───────────────────────────────────────────────────
        self.lbl_stats      = ft.Text("", size=13, color=NEGRO)
        self.lbl_sys_status = ft.Text("", size=13, color=NEGRO)

        tab_general = ft.Column(
            controls=[
                self._tarjeta("Estadísticas de uso", self.lbl_stats,
                              ft.Icons.BAR_CHART_ROUNDED, ORO),
                self._tarjeta("Estado del sistema", self.lbl_sys_status,
                              ft.Icons.MEMORY_ROUNDED, EXITO),
                ft.Divider(color=GRIS_SUAVE, height=18),
                self._boton_admin(
                    "Limpiar todas las conversaciones",
                    ft.Icons.DELETE_SWEEP_ROUNDED,
                    ERROR,
                    lambda _: self._admin_limpiar_bd(),
                ),
                self._boton_admin(
                    "Reconstruir índice RAG",
                    ft.Icons.REFRESH_ROUNDED,
                    GRIS,
                    lambda _: self._admin_rebuild_rag(),
                ),
                self._boton_admin(
                    "Salir del modo kiosco",
                    ft.Icons.FULLSCREEN_EXIT_ROUNDED,
                    ORO,
                    lambda _: self._admin_salir_kiosco(),
                    texto_color=NEGRO,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            height=360,
        )

        # ── Pestaña Diagnóstico ───────────────────────────────────────────────
        self.bar_mic = ft.ProgressBar(
            value=0, color=TINTO, bgcolor=GRIS_SUAVE,
            expand=True, height=12, border_radius=6,
        )
        self.lbl_mic_nivel = ft.Text(
            "Nivel: —  (umbral: 0.015)", size=12, color=GRIS
        )
        self.btn_mic_test = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=16),
                    ft.Text("Iniciar prueba de micrófono", size=13),
                ],
                spacing=6, tight=True,
            ),
            color=BLANCO, bgcolor=TINTO,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=lambda _: self._toggle_mic_test(),
        )

        self.lbl_ping = ft.Text("", size=13)
        self.btn_ping = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WIFI_ROUNDED, size=16),
                    ft.Text("Probar conexión OpenAI", size=13),
                ],
                spacing=6, tight=True,
            ),
            color=BLANCO, bgcolor=TINTO,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=lambda _: self._test_openai(),
        )

        self.lista_logs = ft.ListView(spacing=4, height=110, auto_scroll=True)

        tab_diagnostico = ft.Column(
            controls=[
                self._tarjeta(
                    "Micrófono en vivo",
                    ft.Column([
                        self.bar_mic,
                        self.lbl_mic_nivel,
                        self.btn_mic_test,
                    ], spacing=8),
                    ft.Icons.MIC_ROUNDED, TINTO,
                ),
                self._tarjeta(
                    "Conexión OpenAI",
                    ft.Column([self.btn_ping, self.lbl_ping], spacing=8),
                    ft.Icons.CLOUD_ROUNDED, "#0EA5E9",
                ),
                self._tarjeta(
                    "Registro de errores",
                    self.lista_logs,
                    ft.Icons.BUG_REPORT_ROUNDED, ERROR,
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            height=360,
        )

        # ── Pestaña Ajustes ───────────────────────────────────────────────────
        self.lbl_umbral_val = ft.Text(
            f"{self.voz_umbral:.3f}",
            size=14, weight=ft.FontWeight.BOLD, color=TINTO,
        )
        self.slider_umbral = ft.Slider(
            min=0.005, max=0.10, divisions=19,
            value=self.voz_umbral,
            active_color=TINTO,
            inactive_color=GRIS_SUAVE,
            thumb_color=TINTO,
            expand=True,
            on_change=lambda e: self._preview_umbral(e.control.value),
            on_change_end=lambda e: self._guardar_umbral(e.control.value),
        )

        VOCES = [
            ("ash",     "Ash     — neutral, claro (predeterminado)"),
            ("alloy",   "Alloy   — neutro, equilibrado"),
            ("ballad",  "Ballad  — cálido, expresivo"),
            ("coral",   "Coral   — cálido, amigable"),
            ("echo",    "Echo    — masculino, suave"),
            ("fable",   "Fable   — acento británico"),
            ("nova",    "Nova    — femenino, animado"),
            ("onyx",    "Onyx    — masculino, profundo"),
            ("sage",    "Sage    — cálido, sereno"),
            ("shimmer", "Shimmer — femenino, suave"),
        ]
        self.dropdown_voz = ft.Dropdown(
            value=self.voz_tts,
            label="Voz del asistente",
            options=[ft.DropdownOption(key=k, text=t) for k, t in VOCES],
            border_color=GRIS_MED,
            focused_border_color=TINTO,
            border_radius=12,
            on_select=lambda e: self._guardar_voz(e.control.value),
        )

        self.campo_pin_nuevo   = ft.TextField(
            label="Nuevo PIN", password=True, can_reveal_password=True,
            border_color=GRIS_MED, focused_border_color=TINTO,
            cursor_color=TINTO, width=185, border_radius=12,
        )
        self.campo_pin_confirm = ft.TextField(
            label="Confirmar PIN", password=True, can_reveal_password=True,
            border_color=GRIS_MED, focused_border_color=TINTO,
            cursor_color=TINTO, width=185, border_radius=12,
        )
        self.lbl_pin_msg = ft.Text("", size=12)

        self.lista_conv = ft.ListView(spacing=6, height=160, auto_scroll=False)

        tab_ajustes = ft.Column(
            controls=[
                self._tarjeta(
                    "Voz del asistente",
                    self.dropdown_voz,
                    ft.Icons.RECORD_VOICE_OVER_ROUNDED, ORO,
                ),
                self._tarjeta(
                    "Umbral de detección de voz",
                    ft.Column([
                        ft.Row([
                            ft.Text("0.005", size=11, color=GRIS),
                            self.slider_umbral,
                            ft.Text("0.100", size=11, color=GRIS),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                        ft.Row([
                            ft.Text("Valor actual:", size=12, color=GRIS),
                            self.lbl_umbral_val,
                            ft.Text("(se guarda al soltar)",
                                    size=11, color=GRIS, italic=True),
                        ], spacing=8),
                    ], spacing=6),
                    ft.Icons.TUNE_ROUNDED, GRIS,
                ),
                self._tarjeta(
                    "Cambiar PIN de administrador",
                    ft.Column([
                        ft.Row([
                            self.campo_pin_nuevo,
                            self.campo_pin_confirm,
                        ], spacing=10),
                        ft.ElevatedButton(
                            content="Guardar nuevo PIN",
                            color=BLANCO, bgcolor=TINTO,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=10)
                            ),
                            on_click=lambda _: self._guardar_pin(),
                        ),
                        self.lbl_pin_msg,
                    ], spacing=8),
                    ft.Icons.LOCK_ROUNDED, TINTO,
                ),
                self._tarjeta(
                    "Últimas conversaciones",
                    self.lista_conv,
                    ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, "#0EA5E9",
                ),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            height=360,
        )

        # ── Barra de pestañas manual ──────────────────────────────────────────
        self._admin_tab_idx  = 0
        self._admin_panels   = [
            ft.Container(content=tab_general,     visible=True,  padding=ft.padding.only(top=8)),
            ft.Container(content=tab_diagnostico, visible=False, padding=ft.padding.only(top=8)),
            ft.Container(content=tab_ajustes,     visible=False, padding=ft.padding.only(top=8)),
        ]
        self._tab_textos = [
            ft.Text("General",     size=13, color=TINTO, weight=ft.FontWeight.W_600),
            ft.Text("Diagnóstico", size=13, color=GRIS),
            ft.Text("Ajustes",     size=13, color=GRIS),
        ]
        self._tab_indicadores = [
            ft.Container(height=2.5, bgcolor=TINTO, border_radius=1),
            ft.Container(height=2.5, bgcolor="transparent"),
            ft.Container(height=2.5, bgcolor="transparent"),
        ]

        def _btn_tab(idx):
            return ft.Column(
                controls=[
                    ft.TextButton(
                        content=self._tab_textos[idx],
                        style=ft.ButtonStyle(
                            overlay_color=ft.Colors.with_opacity(0.07, TINTO),
                            padding=ft.padding.symmetric(horizontal=18, vertical=8),
                        ),
                        on_click=lambda _, i=idx: self._switch_admin_tab(i),
                    ),
                    self._tab_indicadores[idx],
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )

        barra_tabs = ft.Container(
            content=ft.Row(
                controls=[_btn_tab(0), _btn_tab(1), _btn_tab(2)],
                spacing=0,
            ),
            border=ft.border.only(
                bottom=ft.BorderSide(1, GRIS_SUAVE)
            ),
        )

        titulo_dlg = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.ADMIN_PANEL_SETTINGS_ROUNDED,
                        color=BLANCO, size=18,
                    ),
                    width=34, height=34,
                    bgcolor=TINTO,
                    border_radius=17,
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            "Panel de Administrador",
                            weight=ft.FontWeight.BOLD,
                            color=NEGRO, size=15,
                        ),
                        ft.Text(
                            "Lince Interactivo — UAdeO",
                            size=10, color=GRIS,
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            spacing=10,
        )

        self.dlg_admin = ft.AlertDialog(
            modal=True,
            title=titulo_dlg,
            content=ft.Column(
                controls=[barra_tabs, *self._admin_panels],
                spacing=0,
                width=490,
                height=450,
                scroll=ft.ScrollMode.HIDDEN,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cerrar", color=GRIS),
                    on_click=lambda _: self._cerrar_admin(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=18),
        )

    def _tarjeta(
        self,
        titulo: str,
        contenido,
        icono=None,
        color_icono: str = GRIS,
    ) -> ft.Container:
        encabezado_controls = []
        if icono:
            encabezado_controls.append(
                ft.Icon(icono, size=14, color=color_icono)
            )
        encabezado_controls.append(
            ft.Text(
                titulo,
                weight=ft.FontWeight.W_600,
                color=NEGRO,
                size=12,
            )
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(encabezado_controls, spacing=6),
                    ft.Divider(height=8, color=GRIS_SUAVE),
                    contenido
                    if isinstance(contenido, ft.Control)
                    else ft.Text(str(contenido)),
                ],
                spacing=4,
            ),
            bgcolor=SUPERFICIE,
            border_radius=12,
            border=ft.border.all(1, GRIS_SUAVE),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            shadow=ft.BoxShadow(
                blur_radius=6,
                color=ft.Colors.with_opacity(0.05, NEGRO),
                offset=ft.Offset(0, 2),
            ),
        )

    def _boton_admin(
        self,
        etiqueta: str,
        icono,
        bgcolor: str,
        on_click,
        texto_color: str = BLANCO,
    ) -> ft.ElevatedButton:
        return ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(icono, size=16, color=texto_color),
                    ft.Text(etiqueta, size=13, color=texto_color),
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=bgcolor,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                overlay_color=ft.Colors.with_opacity(0.15, texto_color),
                elevation={"": 1, "hovered": 3},
            ),
            on_click=on_click,
        )

    # ── Lógica admin ──────────────────────────────────────────────────────────

    def _log_error(self, fuente: str, error: str):
        ts      = time.strftime("%H:%M:%S")
        entrada = f"[{ts}] {fuente}: {error}"
        self._error_logs.append(entrada)
        if len(self._error_logs) > 50:
            self._error_logs.pop(0)

    def _refrescar_logs(self):
        self.lista_logs.controls.clear()
        if not self._error_logs:
            self.lista_logs.controls.append(
                ft.Text("Sin errores registrados.", color=GRIS, size=12, italic=True)
            )
        else:
            for entrada in reversed(self._error_logs[-20:]):
                self.lista_logs.controls.append(
                    ft.Text(entrada, size=11, color=ERROR, selectable=True)
                )

    def _toggle_mic_test(self):
        if self._mic_test_activo:
            self._mic_test_activo = False
            self.btn_mic_test.content = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=16),
                    ft.Text("Iniciar prueba de micrófono", size=13),
                ],
                spacing=6, tight=True,
            )
            self.btn_mic_test.bgcolor = TINTO
            self.bar_mic.value        = 0
            self.lbl_mic_nivel.value  = "Nivel: —"
            self.page.update()
        else:
            if self.grabando:
                self.lbl_mic_nivel.value = "Micrófono en uso por el asistente."
                self.page.update()
                return
            self._mic_test_activo = True
            self.btn_mic_test.content = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.STOP_ROUNDED, size=16),
                    ft.Text("Detener prueba", size=13),
                ],
                spacing=6, tight=True,
            )
            self.btn_mic_test.bgcolor = ERROR
            self.page.update()
            threading.Thread(target=self._run_mic_test, daemon=True).start()

    def _run_mic_test(self):
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
                while self._mic_test_activo and self.dlg_admin.open:
                    datos, _   = stream.read(int(SAMPLE_RATE * 0.05))
                    volumen    = float(np.sqrt(np.mean(datos**2)))
                    nivel_norm = min(volumen / 0.10, 1.0)
                    self.bar_mic.value       = nivel_norm
                    self.lbl_mic_nivel.value = (
                        f"Nivel: {volumen:.4f}   "
                        f"{'VOZ DETECTADA' if volumen > self.voz_umbral else 'Silencio'}   "
                        f"(umbral: {self.voz_umbral:.3f})"
                    )
                    self.page.update()
        except Exception as e:
            self._log_error("MicTest", str(e))
        finally:
            self._mic_test_activo = False
            self.bar_mic.value    = 0
            self.btn_mic_test.content = ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=16),
                    ft.Text("Iniciar prueba de micrófono", size=13),
                ],
                spacing=6, tight=True,
            )
            self.btn_mic_test.bgcolor = TINTO

    def _test_openai(self):
        self.lbl_ping.value    = "Probando conexión..."
        self.lbl_ping.color    = GRIS
        self.btn_ping.disabled = True
        self.page.update()
        threading.Thread(target=self._run_ping, daemon=True).start()

    def _run_ping(self):
        inicio = time.time()
        try:
            self.cliente.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            ms = int((time.time() - inicio) * 1000)
            self.lbl_ping.value = f"Conexión exitosa — {ms} ms"
            self.lbl_ping.color = EXITO
        except Exception as e:
            self.lbl_ping.value = f"Error: {e}"
            self.lbl_ping.color = ERROR
            self._log_error("PingOpenAI", str(e))
        finally:
            self.btn_ping.disabled = False
            self.page.update()

    def _cfg_leer(self, clave: str, defecto, tipo=str):
        try:
            row = self.db.execute(
                "SELECT valor FROM config WHERE clave=?", (clave,)
            ).fetchone()
            return tipo(row[0]) if row else defecto
        except Exception:
            return defecto

    def _cfg_guardar(self, clave: str, valor):
        self.db.execute(
            "INSERT INTO config (clave, valor) VALUES (?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, str(valor)),
        )
        self.db.commit()

    def _guardar_voz(self, voz: str):
        if not voz:
            return
        self.voz_tts = voz
        self._cfg_guardar("voz_tts", voz)

    def _preview_umbral(self, valor: float):
        self.lbl_umbral_val.value = f"{valor:.3f}"
        self.page.update()

    def _guardar_umbral(self, valor: float):
        self.voz_umbral = round(valor, 3)
        self.lbl_umbral_val.value = f"{self.voz_umbral:.3f}"
        self._cfg_guardar("voz_umbral", self.voz_umbral)
        self.page.update()

    def _guardar_pin(self):
        nuevo    = (self.campo_pin_nuevo.value   or "").strip()
        confirma = (self.campo_pin_confirm.value or "").strip()
        if not nuevo:
            self.lbl_pin_msg.value = "Escribe el nuevo PIN."
            self.lbl_pin_msg.color = ERROR
        elif not nuevo.isdigit():
            self.lbl_pin_msg.value = "El PIN solo puede contener números."
            self.lbl_pin_msg.color = ERROR
        elif len(nuevo) < 4:
            self.lbl_pin_msg.value = "El PIN debe tener al menos 4 dígitos."
            self.lbl_pin_msg.color = ERROR
        elif nuevo != confirma:
            self.lbl_pin_msg.value = "Los PIN no coinciden."
            self.lbl_pin_msg.color = ERROR
        else:
            self.admin_pin = nuevo
            self._cfg_guardar("admin_pin", nuevo)
            self.campo_pin_nuevo.value   = ""
            self.campo_pin_confirm.value = ""
            self.lbl_pin_msg.value = "PIN actualizado correctamente."
            self.lbl_pin_msg.color = EXITO
        self.page.update()

    def _cargar_conversaciones(self):
        self.lista_conv.controls.clear()
        try:
            filas = self.db.execute("""
                SELECT role, content, ts, session_id
                FROM conversaciones
                ORDER BY id DESC
                LIMIT 40
            """).fetchall()

            if not filas:
                self.lista_conv.controls.append(
                    ft.Text(
                        "Sin conversaciones registradas.",
                        color=GRIS, size=12, italic=True,
                    )
                )
            else:
                sesion_actual = None
                for role, content, ts, sid in filas:
                    if sid != sesion_actual:
                        sesion_actual = sid
                        self.lista_conv.controls.append(
                            ft.Container(
                                content=ft.Text(
                                    f"Sesión {sid[:8]}…  {ts[:16]}",
                                    size=10, color=GRIS, italic=True,
                                ),
                                padding=ft.padding.only(top=6),
                            )
                        )
                    es_usuario = role == "user"
                    self.lista_conv.controls.append(
                        ft.Container(
                            content=ft.Text(
                                content,
                                size=12,
                                color=BLANCO if es_usuario else NEGRO,
                                selectable=True,
                            ),
                            bgcolor=TINTO if es_usuario else GRIS_SUAVE,
                            border_radius=8,
                            padding=ft.padding.symmetric(
                                horizontal=10, vertical=6
                            ),
                        )
                    )
        except Exception as e:
            self._log_error("CargarConv", str(e))

    def _switch_admin_tab(self, idx: int):
        for i, (panel, txt, ind) in enumerate(
            zip(self._admin_panels, self._tab_textos, self._tab_indicadores)
        ):
            activo        = i == idx
            panel.visible = activo
            txt.color     = TINTO if activo else GRIS
            txt.weight    = ft.FontWeight.W_600 if activo else ft.FontWeight.NORMAL
            ind.bgcolor   = TINTO if activo else "transparent"
        self._admin_tab_idx = idx
        self.page.update()

    def _tap_logo(self):
        self._admin_taps += 1
        if self._admin_tap_timer:
            self._admin_tap_timer.cancel()
        if self._admin_taps >= ADMIN_TAPS_REQ:
            self._admin_taps = 0
            self._abrir_pin()
        else:
            self._admin_tap_timer = threading.Timer(2.5, self._reset_taps)
            self._admin_tap_timer.start()

    def _reset_taps(self):
        self._admin_taps = 0

    def _abrir_pin(self):
        self.campo_pin.value     = ""
        self.lbl_pin_error.value = ""
        self.dlg_pin.open        = True
        self.page.update()

    def _cerrar_pin(self):
        self.dlg_pin.open = False
        self.page.update()

    def _verificar_pin(self):
        if self.campo_pin.value == self.admin_pin:
            self.dlg_pin.open = False
            self._abrir_admin()
        else:
            self.lbl_pin_error.value = "PIN incorrecto. Intenta de nuevo."
            self.campo_pin.value     = ""
            self.page.update()

    def _abrir_admin(self):
        self._actualizar_stats()
        self._refrescar_logs()
        self._cargar_conversaciones()
        self.slider_umbral.value  = self.voz_umbral
        self.lbl_umbral_val.value = f"{self.voz_umbral:.3f}"
        self.dropdown_voz.value   = self.voz_tts
        self.lbl_ping.value       = ""
        self.lbl_pin_msg.value    = ""
        self.dlg_admin.open       = True
        self.page.update()

    def _cerrar_admin(self):
        self._mic_test_activo = False
        self.dlg_admin.open   = False
        self.page.update()

    def _actualizar_stats(self):
        try:
            cur = self.db.execute(
                "SELECT COUNT(DISTINCT session_id), COUNT(*) FROM conversaciones"
            )
            sesiones, mensajes = cur.fetchone()
            cur2 = self.db.execute(
                "SELECT COUNT(DISTINCT session_id) FROM conversaciones "
                "WHERE ts >= date('now')"
            )
            sesiones_hoy = cur2.fetchone()[0]
            self.lbl_stats.value = (
                f"Hoy: {sesiones_hoy} sesiones   ·   "
                f"Total: {sesiones} sesiones   ·   "
                f"{mensajes} mensajes"
            )
        except Exception:
            self.lbl_stats.value = "No se pudieron cargar las estadísticas."

        rag_st = (
            "Disponible"
            if (self.rag and self.rag.disponible)
            else "No disponible"
        )
        mon_st = monitoring.estado()
        self.lbl_sys_status.value = f"RAG: {rag_st}   ·   {mon_st}"

    def _admin_limpiar_bd(self):
        try:
            self.db.execute("DELETE FROM conversaciones")
            self.db.commit()
            self.historial = []
            self.chat_list.controls.clear()
            self._actualizar_stats()
            self.page.update()
        except Exception as e:
            self.lbl_stats.value = f"Error al limpiar: {e}"
            self.page.update()

    def _admin_rebuild_rag(self):
        def _rebuild():
            try:
                if self.rag:
                    self.rag.reconstruir()
                    self._actualizar_stats()
                    self.page.update()
            except Exception:
                pass
        threading.Thread(target=_rebuild, daemon=True).start()

    def _admin_salir_kiosco(self):
        self.dlg_admin.open            = False
        self.page.window.full_screen   = False
        self.page.window.always_on_top = False
        self.page.window.movable       = True
        self.page.window.resizable     = True
        self.page.update()

    # ── Navegación ────────────────────────────────────────────────────────────

    def _mostrar_inicio(self):
        self.btn_nueva_sesion.visible = False
        self.vista_chat.visible       = False
        self.vista_inicio.visible     = True
        self._set_estado("Toca el micrófono para hablar")
        self.page.update()

    def _mostrar_chat(self):
        self.btn_nueva_sesion.visible = True
        self.vista_inicio.visible     = False
        self.vista_chat.visible       = True
        self.page.update()

    def _nueva_sesion(self):
        threading.Thread(
            target=self._limpiar_sesion_db,
            args=(self.session_id,),
            daemon=True,
        ).start()
        self.historial  = []
        self.session_id = str(uuid.uuid4())
        self.chat_list.controls.clear()
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
        self._set_mic_activo(True)
        self._set_estado("Habla ahora...")
        threading.Thread(
            target=self._transcribir_audio, args=(desde_inicio,), daemon=True
        ).start()

    def _set_mic_activo(self, activo: bool):
        if activo:
            # Inicio: botón blanco → ORO  /  Chat: botón tinto → ORO
            self.btn_mic_inicio.icon_color = NEGRO
            self.btn_mic_inicio.style.bgcolor = {"": ORO, "hovered": ORO}
            self.btn_mic_chat.style.bgcolor   = {"": ORO, "hovered": ORO}
            self.ring_pulso.opacity = 0.0
            self.ring_oro.opacity   = 0.0
        else:
            self.btn_mic_inicio.icon_color = TINTO
            self.btn_mic_inicio.style.bgcolor = {"": BLANCO, "hovered": ORO_SUAVE}
            self.btn_mic_chat.style.bgcolor   = {"": TINTO, "hovered": ORO}
        self.page.update()

    def _transcribir_audio(self, desde_inicio: bool):
        try:
            audio = self._capturar_audio()
            if audio is None:
                self._restaurar_microfono()
                self._set_estado("No se detectó voz. Intenta de nuevo.")
                return
            self._set_estado("Procesando...")
            audio.name = "audio.wav"
            resultado  = self.cliente.audio.transcriptions.create(
                model="whisper-1", file=audio, language="es",
                prompt="UAdeO Culiacán: kardex, credencial, beca, carrera, matrícula.",
            )
            texto = resultado.text.strip()
            if texto:
                self._restaurar_microfono()
                self._procesar(texto, desde_inicio)
            else:
                self._restaurar_microfono()
                self._set_estado("No te entendí. Intenta de nuevo.")
        except Exception as e:
            self._log_error("Microfono", str(e))
            self._restaurar_microfono()
            self._set_estado(f"Error de micrófono: {e}")

    def _capturar_audio(self) -> io.BytesIO | None:
        frames: list      = []
        hablando          = False
        contador_silencio = 0
        contador_espera   = 0
        duracion_chunk    = 0.1
        max_silencio      = int(SILENCIO_SEG / duracion_chunk)
        max_espera        = int(ESPERA_MAX_SEG / duracion_chunk)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
            while True:
                datos, _ = stream.read(int(SAMPLE_RATE * duracion_chunk))
                volumen  = float(np.sqrt(np.mean(datos**2)))
                if volumen > self.voz_umbral:
                    hablando          = True
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

        audio  = np.concatenate(frames)
        buffer = io.BytesIO()
        wavfile.write(buffer, SAMPLE_RATE, (audio * 32767).astype(np.int16))
        buffer.seek(0)
        return buffer

    # ── Procesamiento del chat ────────────────────────────────────────────────

    def _pregunta_rapida(self, texto: str):
        self._procesar(texto, desde_inicio=True)

    def _enviar_texto(self):
        texto = (self.campo_texto.value or "").strip()
        if texto and not self.procesando:
            self.campo_texto.value = ""
            self.page.update()
            self._procesar(texto, desde_inicio=False)

    def _procesar(self, texto: str, desde_inicio: bool):
        if desde_inicio:
            self._mostrar_chat()
        self.procesando = True
        self.ultimo_uso = time.time()
        self._agregar_burbuja(texto, "user")
        self._set_estado("Lince está pensando...")
        threading.Thread(
            target=self._responder, args=(texto,), daemon=True
        ).start()

    def _responder(self, texto: str):
        try:
            self.historial.append({"role": "user", "content": texto})

            if self.rag and self.rag.disponible:
                contexto_conv = " ".join(
                    m["content"] for m in self.historial[-6:] if m["role"] == "user"
                )
                contexto = self.rag.buscar(f"{contexto_conv} {texto}".strip())
                prompt   = get_system_prompt_con_contexto(contexto)
            else:
                prompt = self.prompt

            txt_ref = self._agregar_burbuja("▌", "bot")

            with monitoring.TraceLlamada(self.session_id, texto) as trace:
                stream = self.cliente.chat.completions.create(
                    model=OPENAI_MODEL,
                    temperature=0.7,
                    max_tokens=450,
                    messages=[{"role": "system", "content": prompt}]
                    + self.historial[-20:],
                    stream=True,
                    stream_options={"include_usage": True},
                )
                acumulado      = ""
                tokens_entrada = 0
                tokens_salida  = 0

                for chunk in stream:
                    if chunk.usage:
                        tokens_entrada = chunk.usage.prompt_tokens    or 0
                        tokens_salida  = chunk.usage.completion_tokens or 0
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        acumulado += delta.content
                        txt_ref.value = acumulado + "▌"
                        self.page.update()

                txt_ref.value = acumulado
                self.page.update()
                respuesta = acumulado

                trace.registrar_respuesta(
                    respuesta,
                    tokens_entrada=tokens_entrada,
                    tokens_salida =tokens_salida,
                )

            self.historial.append({"role": "assistant", "content": respuesta})
            threading.Thread(
                target=self._guardar_mensajes,
                args=(self.session_id, texto, respuesta),
                daemon=True,
            ).start()
            self._set_estado("Hablando...")
            threading.Thread(
                target=self._reproducir_voz, args=(respuesta,), daemon=True
            ).start()
        except Exception as e:
            self._log_error("Responder", str(e))
            self._agregar_burbuja("Hubo un error. Por favor intenta de nuevo.", "bot")
            self._set_estado("")
            self.procesando = False

    def _reproducir_voz(self, texto: str):
        path = None
        try:
            audio_mp3 = self.cliente.audio.speech.create(
                model="tts-1",
                voice=self.voz_tts,
                input=texto,
                response_format="mp3",
                speed=1.2,
            ).read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                f.write(audio_mp3)
                path = f.name
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
            self._set_estado("")
            self.procesando = False

    # ── Base de datos ─────────────────────────────────────────────────────────

    def _guardar_mensajes(self, session_id: str, texto: str, respuesta: str):
        self.db.executemany(
            "INSERT INTO conversaciones (session_id, role, content) VALUES (?,?,?)",
            [(session_id, "user", texto), (session_id, "assistant", respuesta)],
        )
        self.db.commit()

    def _limpiar_sesion_db(self, session_id: str):
        self.db.execute(
            "DELETE FROM conversaciones WHERE session_id=?", (session_id,)
        )
        self.db.commit()

    # ── Helpers de UI ─────────────────────────────────────────────────────────

    def _agregar_burbuja(self, texto: str, rol: str):
        es_usuario = rol == "user"
        hora       = time.strftime("%H:%M")

        cuerpo = ft.Text(
            texto,
            size=14,
            color=BLANCO if es_usuario else NEGRO,
            selectable=True,
        )

        hora_label = ft.Text(
            hora,
            size=10,
            color=(
                ft.Colors.with_opacity(0.60, BLANCO)
                if es_usuario
                else ft.Colors.with_opacity(0.50, GRIS)
            ),
        )

        burbuja = ft.Container(
            content=ft.Column(
                controls=[cuerpo, hora_label],
                spacing=5,
                tight=True,
            ),
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=[TINTO, TINTO_OSC],
            )
            if es_usuario
            else None,
            bgcolor=None if es_usuario else SUPERFICIE,
            border_radius=ft.BorderRadius.only(
                top_left=18,
                top_right=18,
                bottom_left=4  if es_usuario else 18,
                bottom_right=18 if es_usuario else 4,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            expand=2,
            shadow=ft.BoxShadow(
                blur_radius=10,
                color=ft.Colors.with_opacity(0.12, NEGRO),
                offset=ft.Offset(0, 3),
            ),
        )

        espaciador = ft.Container(expand=1)

        fila = ft.Row(
            controls=(
                [espaciador, burbuja] if es_usuario else [burbuja, espaciador]
            ),
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        self.chat_list.controls.append(fila)
        self.page.update()
        return cuerpo

    def _set_estado(self, mensaje: str):
        self.lbl_estado_inicio.value = mensaje
        self.lbl_estado_chat.value   = mensaje
        self.page.update()

    def _restaurar_microfono(self):
        self._set_mic_activo(False)
        self.grabando = False

    # ── Animación de pantalla de inicio ──────────────────────────────────────

    def _iniciar_animacion(self):
        def _loop():
            toggle   = False
            seg_prev = -1
            while True:
                ahora = time.localtime()
                if ahora.tm_sec != seg_prev:
                    seg_prev = ahora.tm_sec
                    self.lbl_reloj.value  = time.strftime("%H:%M")
                    self.lbl_saludo.value = self._get_saludo()

                if self.vista_inicio.visible and not self.grabando and not self.procesando:
                    if toggle:
                        self.ring_pulso.opacity = 0.55
                        self.ring_pulso.scale   = 1.12
                        self.ring_oro.opacity   = 0.30
                        self.ring_oro.scale     = 1.08
                        self.btn_mic_inicio.scale = 1.06
                    else:
                        self.ring_pulso.opacity = 0.15
                        self.ring_pulso.scale   = 1.0
                        self.ring_oro.opacity   = 0.10
                        self.ring_oro.scale     = 1.0
                        self.btn_mic_inicio.scale = 1.0
                    toggle = not toggle

                try:
                    self.page.update()
                except Exception:
                    pass

                time.sleep(1.1)

        threading.Thread(target=_loop, daemon=True).start()

    # ── Vigilancia de inactividad ─────────────────────────────────────────────

    def _vigilar_inactividad(self):
        def _loop():
            while True:
                time.sleep(5)
                if (
                    time.time() - self.ultimo_uso > INACTIVIDAD_S
                    and self.vista_chat.visible
                    and not self.procesando
                ):
                    self._nueva_sesion()
        threading.Thread(target=_loop, daemon=True).start()


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main(page: ft.Page):
    LinceApp(page)


if __name__ == "__main__":
    try:
        ft.app(target=main)
    finally:
        monitoring.cerrar()
