#  Lince Interactivo — UAdeO Culiacán

Asistente virtual de escritorio para la Universidad Autónoma de Occidente. Responde preguntas de estudiantes por voz y texto usando inteligencia artificial.

---

## ¿Qué hace?

- Escucha la voz del estudiante con el micrófono
- Transcribe y entiende la pregunta con IA
- Responde en texto y en voz
- Guarda el historial de conversaciones localmente
- Se reinicia solo por inactividad (modo kiosco)

---

## Requisitos

**Hardware**
- Computadora con Windows 10 u 11
- Micrófono conectado
- Bocinas o audífonos conectados
- Conexión a internet

**Software**
- Python 3.11 o superior → [descargar aquí](https://www.python.org/downloads/)
  - Al instalar, marcar la opción **"Add Python to PATH"**

---

## Instalación paso a paso

### 1. Descargar el proyecto

```bash
git clone https://github.com/Lucio2136/lince-uadeo.git
cd lince-uadeo
```

O descarga el ZIP desde GitHub y extrae la carpeta.

### 2. Instalar dependencias

Abre una terminal en la carpeta del proyecto y ejecuta:

```bash
pip install -r requirements_desktop.txt
```

### 3. Configurar credenciales

Crea un archivo llamado `.env` en la carpeta del proyecto con el siguiente contenido:

```
OPENAI_API_KEY=solicitar_al_administrador
```

> Solicita la clave al administrador del proyecto antes de instalar.

### 4. Agregar la base de conocimiento (opcional)

Si tienes el archivo `universidad.json` con la información de la universidad, colócalo en la misma carpeta del proyecto. Si no existe, el bot igual funciona pero sin datos específicos de la universidad.

Para generar el `universidad.json` desde la plantilla CSV:

```bash
python -c "import pandas as pd, json; df = pd.read_csv('plantilla_universidad.csv'); df.to_json('universidad.json', orient='records', force_ascii=False, indent=2)"
```

---

## Cómo ejecutar

### Modo normal (desarrollo)

```bash
python lince_app.py
```

### Modo kiosco (instalación en universidad)

Doble clic en el archivo `KIOSCO.bat`

> En modo kiosco la pantalla es completa y el bot se reinicia automáticamente si se cierra.

---

## Cómo cerrar el bot en modo kiosco

```
Ctrl + Alt + Supr → Administrador de tareas → finalizar python
```

---

## Estructura del proyecto

```
lince-uadeo/
├── lince_app.py              # Aplicación principal
├── universidad_info.py       # Sistema de conocimiento
├── config.py                 # Configuración y credenciales
├── universidad.json          # Base de conocimiento (tú lo generas)
├── plantilla_universidad.csv # Plantilla para capturar información
├── requirements_desktop.txt  # Dependencias
├── KIOSCO.bat                # Arranque automático para kiosco
└── .env                      # API Key (no se sube a GitHub)
```

---

## Inicio automático al encender la PC

1. Presiona `Win + R` y escribe `shell:startup`
2. Copia un acceso directo de `KIOSCO.bat` en esa carpeta
3. Listo, el bot arranca solo cada vez que se enciende la computadora

---

## Tecnologías

| Tecnología | Uso |
|---|---|
| Python 3.11 | Lenguaje principal |
| OpenAI Whisper | Voz a texto |
| OpenAI GPT-4o-mini | Generación de respuestas |
| OpenAI TTS | Texto a voz |
| CustomTkinter | Interfaz gráfica |
| SQLite | Historial de conversaciones local |
| Pygame | Reproducción de audio |

---

## Problemas comunes

**Error: `No module named 'customtkinter'`**
```bash
pip install -r requirements_desktop.txt
```

**Error: `OPENAI_API_KEY not found`**
Verifica que el archivo `.env` existe y tiene el formato correcto.

**No se escucha el micrófono**
Verifica en Configuración de Windows → Sonido → que el micrófono esté habilitado y sea el dispositivo predeterminado.

**La ventana no abre**
Asegúrate de tener Python agregado al PATH. Desinstala y vuelve a instalar Python marcando esa opción.
