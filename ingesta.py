"""Ingesta: lee los informes, los trocea y los guarda en ChromaDB.

Se ejecuta una vez, y otra cada vez que cambien los documentos:
    python -m app.ingesta
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import finanzas
from app.config import CARPETA_CHROMA, CARPETA_DOCS, COLECCION, crear_embeddings


def cargar_documentos() -> list[Document]:
    """Lee cada .md de docs/ con sus metadatos.

    empresa: clave de la empresa si el fichero se llama como ella
    (energia_meseta.md -> "energia_meseta"); si no, "general" (guía de ratios).
    Permite al servidor MCP filtrar la búsqueda por empresa.
    """
    documentos = []
    for fichero in sorted(CARPETA_DOCS.glob("*.md")):
        texto = fichero.read_text(encoding="utf-8")
        titulo = texto.splitlines()[0].lstrip("# ").strip()
        empresa = fichero.stem if fichero.stem in finanzas.empresas() else "general"
        documentos.append(Document(
            page_content=texto,
            metadata={"fuente": fichero.name, "titulo": titulo, "empresa": empresa},
        ))
    return documentos


def trocear(documentos: list[Document]) -> list[Document]:
    """Parte los documentos en fragmentos de ~700 caracteres con 100 de solape.

    Un fragmento suelto ("los gastos financieros subieron...") no dice de qué
    empresa habla, así que se le antepone el título del documento. Así el
    embedding y el LLM saben siempre a quién se refiere.
    """
    troceador = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=100)
    fragmentos = troceador.split_documents(documentos)  # heredan los metadatos
    for f in fragmentos:
        f.page_content = f"[{f.metadata['titulo']}]\n{f.page_content}"
    return fragmentos


def indexar(embeddings=None) -> int:
    """Calcula el vector de cada fragmento y lo guarda en ChromaDB."""
    fragmentos = trocear(cargar_documentos())
    base = Chroma(
        collection_name=COLECCION,
        embedding_function=embeddings or crear_embeddings(),
        persist_directory=str(CARPETA_CHROMA),
    )
    base.reset_collection()  # empezamos de cero: no quedan fragmentos de versiones antiguas
    ids = [f"{f.metadata['fuente']}-{i}" for i, f in enumerate(fragmentos)]
    base.add_documents(fragmentos, ids=ids)
    return len(fragmentos)


if __name__ == "__main__":
    total = indexar()
    print(f"Guardados {total} fragmentos en {CARPETA_CHROMA}")
