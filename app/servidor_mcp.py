"""Servidor MCP (FastMCP) con los informes anuales y las cuentas de las empresas.

Lo puede usar cualquier cliente MCP: nuestro agente, Claude Code, Claude Desktop...
Normalmente lo arranca el cliente; para lanzarlo a mano:
    python -m app.servidor_mcp
"""

import json

from fastmcp import FastMCP
from langchain_chroma import Chroma

from app import finanzas
from app.config import CARPETA_CHROMA, COLECCION, crear_embeddings

servidor = FastMCP("informes")

# Abrimos la base vectorial que creó la ingesta (no la volvemos a crear)
base = Chroma(
    collection_name=COLECCION,
    embedding_function=crear_embeddings(),
    persist_directory=str(CARPETA_CHROMA),
)


@servidor.tool
def buscar_informes(consulta: str, empresa: str = "", k: int = 3) -> str:
    """Busca en los informes anuales (estrategia, hechos relevantes, riesgos,
    dividendos, perspectivas) y en la guía de interpretación de ratios.

    empresa: nombre de la empresa para buscar solo en su informe (por ejemplo
    "Energía Meseta"), "general" para buscar solo en la guía de ratios, o vacío
    para buscar en todo. Devuelve los k fragmentos más parecidos (máximo 4).
    """
    k = max(1, min(k, 4))  # acota el texto devuelto: el LLM gratuito tiene límite de tokens
    filtro = None
    if empresa.strip():
        try:
            clave = "general" if empresa.strip().lower() == "general" else finanzas.buscar_empresa(empresa)
        except ValueError as error:
            return f"Error: {error}"
        filtro = {"empresa": clave}
    resultados = base.similarity_search(consulta, k=k, filter=filtro)
    if not resultados:
        return "No se han encontrado fragmentos."
    return "\n\n".join(
        f"[Fuente: {doc.metadata['fuente']}]\n{doc.page_content}" for doc in resultados
    )


@servidor.tool
def listar_empresas() -> str:
    """Lista las empresas disponibles, con su sector y los ejercicios con datos."""
    return "\n".join(
        f"- {finanzas.nombre(c)} ({finanzas.sector(c)}): ejercicios {finanzas.ejercicios(c)}"
        for c in finanzas.empresas()
    )


@servidor.tool
def cifras_empresa(empresa: str) -> str:
    """Devuelve en JSON las cuentas (millones de euros) y los ratios calculados de
    una empresa en todos sus ejercicios."""
    try:
        clave = finanzas.buscar_empresa(empresa)
    except ValueError as error:
        return f"Error: {error}"
    resultado = {
        "empresa": finanzas.nombre(clave),
        "sector": finanzas.sector(clave),
        "unidad": "millones de euros",
        "ejercicios": {
            anio: {
                "cuentas": finanzas.cuentas(clave, anio),
                "ratios": {k: round(v, 4) if v is not None else None
                           for k, v in finanzas.calcular_ratios(clave, anio).items()},
            }
            for anio in finanzas.ejercicios(clave)
        },
    }
    return json.dumps(resultado, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # stdio: el cliente habla con el servidor por la entrada y salida estándar
    servidor.run(transport="stdio", show_banner=False, log_level="WARNING")
