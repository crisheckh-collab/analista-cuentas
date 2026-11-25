"""Batería de pruebas: lanza varias preguntas y guarda la traza en resultados.md.

Cubre los caminos del grafo: solo analista, solo documentalista, los dos,
el redactor de informes y una pregunta fuera de tema.

Uso:
    python probar_preguntas.py
"""

import asyncio
import os
import time
from datetime import datetime

from langchain_core.messages import HumanMessage

from app.config import RAIZ
from app.grafo import construir_grafo

PREGUNTAS = [
    ("Solo analista", "¿Cuál fue el ROE de Textil Atlántico en 2024?"),
    ("Solo analista (comparativa)", "¿Qué empresa tuvo mayor margen EBITDA en 2024?"),
    ("Solo documentalista", "¿Qué riesgos menciona Energía Meseta en su informe?"),
    ("Analista + documentalista", "¿Por qué bajó el beneficio de Energía Meseta en 2024?"),
    ("Analista + documentalista (valoración)",
     "¿Está Hoteles Brisa en una situación financiera sana?"),
    ("Redactor", "Prepárame un informe para el comité sobre Textil Atlántico."),
    ("Fuera de tema", "¿Quién ganó el Mundial de fútbol de 2010?"),
]


async def una_pregunta(grafo, pregunta: str) -> tuple[list[str], str]:
    pasos, respuesta = [], ""
    async for paso in grafo.astream({"messages": [HumanMessage(pregunta)]}, stream_mode="updates"):
        for nodo, cambios in paso.items():
            if nodo == "supervisor":
                if cambios["siguiente"] == "FIN":
                    pasos.append("**supervisor** → FIN")
                else:
                    pasos.append(f"**supervisor** → {cambios['siguiente']}: {cambios['tarea']}")
            elif nodo in ("responder", "redactor"):
                respuesta = cambios["messages"][-1].text
                if nodo == "redactor":
                    pasos.append("**redactor**: informe redactado")
            else:
                texto = cambios["hallazgos"][-1].split("] ", 1)[-1]
                resumen = " ".join(texto.split())[:300]
                pasos.append(f"**{nodo}**: {resumen}{'…' if len(texto) > 300 else ''}")
    return pasos, respuesta


async def main() -> None:
    grafo = await construir_grafo()
    lineas = [
        "# Resultados de las pruebas",
        "",
        f"Fecha: {datetime.now():%d/%m/%Y %H:%M} · Modelo: `{os.getenv('MODELO')}`",
        "",
        "Las trazas de los especialistas se recortan a 300 caracteres.",
        "",
    ]
    for i, (tipo, pregunta) in enumerate(PREGUNTAS, 1):
        print(f"[{i}/{len(PREGUNTAS)}] {pregunta}", flush=True)
        inicio = time.perf_counter()
        try:
            pasos, respuesta = await una_pregunta(grafo, pregunta)
        except Exception as error:
            pasos, respuesta = [], f"ERROR: {error}"
        segundos = time.perf_counter() - inicio
        lineas += [f"## {i}. {pregunta}", "", f"*Caso: {tipo} · {segundos:.0f} s*", "",
                   "**Traza:**", ""]
        lineas += [f"{n}. {p}" for n, p in enumerate(pasos, 1)]
        lineas += ["", "**Respuesta:**", "", respuesta, "", "---", ""]
        await asyncio.sleep(20)  # margen para el límite por minuto de Groq

    destino = RAIZ / "resultados.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nGuardado en {destino}")


if __name__ == "__main__":
    asyncio.run(main())
