"""Prueba el servidor MCP sin LLM: lista sus herramientas y llama a cada una.

Uso:
    python probar_mcp.py
"""

import asyncio

from app.agentes import cargar_herramientas_mcp


def texto(resultado) -> str:
    """Las herramientas MCP devuelven bloques de contenido; nos quedamos con el texto."""
    if isinstance(resultado, str):
        return resultado
    return "\n".join(bloque["text"] for bloque in resultado if bloque.get("type") == "text")


async def main() -> None:
    herramientas = {h.name: h for h in await cargar_herramientas_mcp()}
    print("Herramientas:", list(herramientas))

    print("\n--- listar_empresas ---")
    print(texto(await herramientas["listar_empresas"].ainvoke({})))

    print("\n--- buscar_informes (Energía Meseta, riesgos) ---")
    print(texto(await herramientas["buscar_informes"].ainvoke(
        {"consulta": "principales riesgos", "empresa": "Energía Meseta", "k": 1})))

    print("\n--- cifras_empresa (Hoteles Brisa), primeras líneas ---")
    json_cifras = texto(await herramientas["cifras_empresa"].ainvoke({"empresa": "Hoteles Brisa"}))
    print("\n".join(json_cifras.splitlines()[:10]), "\n  ...")


if __name__ == "__main__":
    asyncio.run(main())
