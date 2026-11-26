"""Configuración común: rutas, modelo de lenguaje y modelo de embeddings."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings

# Lee las variables del fichero .env (por ejemplo, GROQ_API_KEY)
load_dotenv()

RAIZ = Path(__file__).parent.parent
CARPETA_DOCS = RAIZ / "docs"                 # informes anuales y guía de ratios (para el RAG)
RUTA_DATOS = RAIZ / "datos" / "empresas.json"  # cuentas numéricas (para los cálculos)
CARPETA_CHROMA = RAIZ / "chroma_db"          # donde ChromaDB guarda la base vectorial
COLECCION = "informes"

# Modelo de embeddings multilingüe que se ejecuta en tu ordenador (gratis, sin clave)
MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def crear_modelo():
    """LLM del plan gratuito de Groq.

    - max_retries: si Groq devuelve 429 (límite por minuto), el cliente espera y
      reintenta en vez de fallar.
    - reasoning_effort="low": gpt-oss "piensa" antes de responder y esos tokens cuentan
      para el límite gratuito (8.000 tokens/minuto). Con "low" piensa menos y va más rápido.
    """
    modelo = os.getenv("MODELO", "groq:openai/gpt-oss-120b")
    extra = {"reasoning_effort": "low"} if "gpt-oss" in modelo else {}
    return init_chat_model(modelo, max_retries=6, **extra)


class EmbeddingsLocales(Embeddings):
    """Convierte textos en vectores con fastembed (adaptado a la interfaz de LangChain)."""

    def __init__(self):
        from fastembed import TextEmbedding

        # La primera vez descarga el modelo (unos 220 MB) y lo guarda en caché
        self.modelo = TextEmbedding(MODELO_EMBEDDINGS)

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.modelo.embed(textos)]

    def embed_query(self, texto: str) -> list[float]:
        return self.embed_documents([texto])[0]


def crear_embeddings() -> Embeddings:
    return EmbeddingsLocales()
