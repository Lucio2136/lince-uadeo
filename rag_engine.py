from __future__ import annotations
import json
import os

_BASE = os.path.dirname(__file__)
_INDEX_PATH = os.path.join(_BASE, "faiss_index")
_DOCS_PATH  = os.path.join(_BASE, "documentos")


class RAGEngine:
    """
    Motor de recuperación semántica sobre la base de conocimiento de la universidad.
    Fuentes: universidad.json + PDFs en la carpeta documentos/
    """

    def __init__(self, api_key: str):
        from langchain_openai import OpenAIEmbeddings
        self._embeddings = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
        self._store = None
        self._inicializar()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _inicializar(self):
        from langchain_community.vectorstores import FAISS

        if os.path.exists(_INDEX_PATH):
            try:
                self._store = FAISS.load_local(
                    _INDEX_PATH, self._embeddings, allow_dangerous_deserialization=True
                )
                return
            except Exception:
                pass  # índice corrupto → reconstruir

        docs = self._cargar_todos_los_documentos()
        if docs:
            self._store = FAISS.from_documents(docs, self._embeddings)
            self._store.save_local(_INDEX_PATH)

    def _cargar_todos_los_documentos(self) -> list:
        docs = []
        docs.extend(self._cargar_json())
        docs.extend(self._cargar_pdfs())
        return docs

    # ── Fuentes de conocimiento ───────────────────────────────────────────────

    def _cargar_json(self) -> list:
        from langchain_core.documents import Document

        path = os.path.join(_BASE, "universidad.json")
        try:
            with open(path, encoding="utf-8") as f:
                datos = json.load(f)
        except FileNotFoundError:
            return []

        docs = []
        for reg in datos:
            texto = (
                f"Tema: {reg.get('Tema', '')}\n"
                f"Departamento: {reg.get('Departamento', '')}\n"
                f"Categoría: {reg.get('Categoria', '')}\n"
                f"Información: {reg.get('Informacion_Completa', '')}"
            )
            if reg.get("Pregunta_Frecuente"):
                texto += f"\nPreguntas frecuentes: {reg['Pregunta_Frecuente']}"
            if reg.get("Contacto"):
                texto += f"\nContacto: {reg['Contacto']}"
            docs.append(Document(
                page_content=texto,
                metadata={"fuente": "universidad.json", "tema": reg.get("Tema", "")},
            ))
        return docs

    def _cargar_pdfs(self) -> list:
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        if not os.path.exists(_DOCS_PATH):
            return []

        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        docs = []

        for archivo in os.listdir(_DOCS_PATH):
            if not archivo.lower().endswith(".pdf"):
                continue
            ruta = os.path.join(_DOCS_PATH, archivo)
            try:
                paginas = PyPDFLoader(ruta).load()
                fragmentos = splitter.split_documents(paginas)
                for frag in fragmentos:
                    frag.metadata["fuente"] = archivo
                docs.extend(fragmentos)
            except Exception as e:
                print(f"[RAG] No se pudo cargar {archivo}: {e}")

        return docs

    # ── Búsqueda ──────────────────────────────────────────────────────────────

    def buscar(self, query: str, k: int = 4) -> str:
        """
        Devuelve los k fragmentos más relevantes.
        query puede incluir el contexto reciente de la conversación.
        """
        if not self._store:
            return ""
        resultados = self._store.similarity_search(query, k=k)
        return "\n\n".join(doc.page_content for doc in resultados)

    # ── Mantenimiento ─────────────────────────────────────────────────────────

    def reconstruir(self):
        """Fuerza la reconstrucción del índice (útil al agregar nuevos PDFs)."""
        import shutil
        if os.path.exists(_INDEX_PATH):
            shutil.rmtree(_INDEX_PATH)
        self._store = None
        self._inicializar()

    @property
    def disponible(self) -> bool:
        return self._store is not None
