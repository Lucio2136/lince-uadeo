import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-4o-mini"

if not OPENAI_API_KEY:
    raise EnvironmentError("Falta la variable OPENAI_API_KEY en el archivo .env")
