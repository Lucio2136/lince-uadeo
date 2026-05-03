"""
Convierte plantilla_universidad.csv -> universidad.json
Corre este script cada vez que actualices el CSV con datos reales.
"""
import csv
import json
import os
import shutil
from datetime import datetime

BASE   = os.path.dirname(__file__)
CSV    = os.path.join(BASE, "plantilla_universidad.csv")
JSON   = os.path.join(BASE, "universidad.json")
INDICE = os.path.join(BASE, "faiss_index")


def convertir():
    if not os.path.exists(CSV):
        print(f"ERROR: No se encontró {CSV}")
        return

    with open(CSV, encoding="utf-8") as f:
        registros = [r for r in csv.DictReader(f) if any(v.strip() for v in r.values())]

    if not registros:
        print("ERROR: El CSV está vacío.")
        return

    # Backup del JSON anterior
    if os.path.exists(JSON):
        backup = JSON.replace(".json", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        shutil.copy(JSON, backup)
        print(f"Backup guardado: {os.path.basename(backup)}")

    with open(JSON, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)

    print(f"✅  {len(registros)} registros guardados en universidad.json")

    # Borrar índice RAG para forzar reconstrucción
    if os.path.exists(INDICE):
        shutil.rmtree(INDICE)
        print("🔄  Índice RAG eliminado — se reconstruirá al iniciar la app")

    print("\nListo. Reinicia lince_flet.py para aplicar los cambios.")


if __name__ == "__main__":
    convertir()
