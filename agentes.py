"""Agentes especialistas.

Agente = modelo + instrucciones (system prompt) + herramientas.
create_agent monta el bucle: pensar -> usar herramienta -> leer resultado -> responder.
"""

import sys

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import RAIZ
from app.herramientas import HERRAMIENTAS_ANALISTA


async def cargar_herramientas_mcp() -> list:
    """Arranca nuestro servidor MCP y convierte sus herramientas al formato LangChain."""
    cliente = MultiServerMCPClient(
        {
            "informes": {
                "transport": "stdio",
                "command": sys.executable,  # el mismo Python que ejecuta este programa
                "args": ["-m", "app.servidor_mcp"],
                "cwd": str(RAIZ),
            }
        }
    )
    return await cliente.get_tools()


PROMPT_DOCUMENTALISTA = """Eres el documentalista. Buscas en los informes anuales de las
empresas y en la guía de interpretación de ratios.
- Busca SIEMPRE con buscar_informes antes de responder. Si la pregunta es de una empresa
  concreta, pasa su nombre en el argumento empresa. Para saber cómo interpretar un ratio,
  busca con empresa="general".
- Haz como mucho 2 búsquedas (por ejemplo, una para el informe de la empresa y otra
  en la guía de ratios).
- Responde solo con lo que digan LITERALMENTE los documentos, de forma resumida (máximo
  12 líneas), citando el fichero de cada dato.
- No estimes, deduzcas ni calcules cifras, y no hagas tú la valoración final: las cifras
  las calcula el analista. Si citas un umbral de la guía, cópialo tal cual.
- Si no está en los documentos, dilo."""

PROMPT_ANALISTA = """Eres el analista financiero. Calculas ratios a partir de las cuentas.
- Usa SIEMPRE tus herramientas: nunca calcules de cabeza ni inventes cifras.
- ratios_empresa: foto de un año. evolucion_empresa: cambio entre los dos últimos años.
  comparar_empresas: ranking de todas las empresas en un ratio.
- Usa la herramienta que mejor encaje; normalmente basta con una.
- Devuelve SOLO las cifras relevantes para el encargo (no copies todos los ratios), con
  unidades, y comenta en pocas frases qué ha mejorado o empeorado.
- Algunos ratios salen de tus herramientas con una flecha y su valoración según la guía
  de ratios: cópiala tal cual SOLO en esos ratios. Si un ratio no trae valoración (por
  ejemplo, los márgenes, que dependen del sector), no le pongas ninguna. No inventes
  umbrales ni medias del sector."""


async def crear_especialistas(modelo, herramientas_mcp=None) -> dict:
    """Devuelve un diccionario {nombre: agente}."""
    if herramientas_mcp is None:
        herramientas_mcp = await cargar_herramientas_mcp()
    busqueda = [h for h in herramientas_mcp if h.name == "buscar_informes"]

    documentalista = create_agent(
        modelo, tools=busqueda, system_prompt=PROMPT_DOCUMENTALISTA, name="documentalista"
    )
    analista = create_agent(
        modelo, tools=HERRAMIENTAS_ANALISTA, system_prompt=PROMPT_ANALISTA, name="analista"
    )
    return {"documentalista": documentalista, "analista": analista}
