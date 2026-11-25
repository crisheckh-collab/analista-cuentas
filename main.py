"""Preguntar al analista desde la consola.

Uso:
    python main.py "¿Por qué bajó el beneficio de Energía Meseta en 2024?"
"""

import asyncio
import sys

from langchain_core.messages import HumanMessage

from app.grafo import construir_grafo


async def main(pregunta: str) -> None:
    grafo = await construir_grafo()
    # stream_mode="updates": muestra lo que hace cada nodo según se ejecuta
    async for paso in grafo.astream({"messages": [HumanMessage(pregunta)]},
                                    stream_mode="updates"):
        for nodo, cambios in paso.items():
            if nodo == "supervisor":
                print(f"\n[supervisor] -> {cambios['siguiente']}: {cambios['tarea']}")
            elif nodo in ("responder", "redactor"):
                print(f"\n=== Respuesta ({nodo}) ===\n{cambios['messages'][-1].text}")
            else:
                print(f"\n{cambios['hallazgos'][-1]}")


if __name__ == "__main__":
    pregunta = " ".join(sys.argv[1:]) or "¿Está Hoteles Brisa en una situación financiera sana?"
    asyncio.run(main(pregunta))
