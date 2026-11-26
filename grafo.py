"""Orquestación con LangGraph: un supervisor reparte el trabajo entre especialistas.

INICIO -> supervisor -> (documentalista | analista) -> supervisor -> ...
       -> redactor (si se pide un informe) -> FIN
       -> responder (resto de preguntas)   -> FIN
"""

import operator
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field

from app import finanzas
from app.agentes import crear_especialistas
from app.config import crear_modelo

MAX_PASOS = 5  # límite de seguridad para que el supervisor no entre en bucle
INTENTOS = 3  # reintentos de un especialista si el LLM genera mal una llamada a herramienta


class Estado(MessagesState):
    """Estado compartido del grafo. La clave "messages" ya viene de MessagesState."""

    siguiente: str  # a quién le toca actuar
    tarea: str  # encargo para ese especialista
    hallazgos: Annotated[list[str], operator.add]  # se acumulan, no se sustituyen
    necesita_contexto: bool  # la pregunta pide valorar/explicar: hace falta el documentalista


class Decision(BaseModel):
    """Respuesta estructurada del supervisor."""

    siguiente: Literal["documentalista", "analista", "redactor", "FIN"] = Field(
        description="Quién actúa ahora. redactor solo para informes; FIN para responder ya."
    )
    tarea: str = Field(description="Encargo completo para ese especialista, con empresas y años. "
                                   "Vacío si FIN.")
    necesita_contexto: bool = Field(
        description="True si la pregunta pide valorar la situación de una empresa, explicar "
                    "causas, comparar en calidad o un informe (hace falta el contexto de los "
                    "informes anuales). False si solo pide un dato o un ratio, o no es del tema."
    )


PROMPT_SUPERVISOR = """Eres el supervisor de un equipo de análisis de cuentas anuales.
No respondes al usuario: decides qué especialista actúa.

Empresas disponibles (ficticias): {empresas}. Ejercicios: 2023 y 2024.

- analista: calcula cifras y ratios exactos a partir de las cuentas (rentabilidad,
  márgenes, liquidez, endeudamiento, dividendos), su evolución y rankings entre empresas.
- documentalista: busca en los informes anuales (estrategia, hechos relevantes, riesgos,
  dividendos, perspectivas) y en la guía que explica cómo interpretar cada ratio.
- redactor: redacta un informe ejecutivo para un comité. Úsalo SOLO si el usuario pide
  un informe, nota o resumen para un comité, y como ÚLTIMO paso, cuando ya tengas
  cifras del analista y contexto del documentalista.

Pautas:
- Cifras o ratios -> analista. Causas, contexto, riesgos o planes -> documentalista.
- Valoraciones ("¿está sana?", "¿por qué ha bajado?", "¿cuál es mejor?") -> primero el
  analista (sus ratios ya vienen valorados según la guía) y DESPUÉS el documentalista,
  pidiéndole el contexto del informe que explica esas cifras (hechos relevantes, riesgos,
  planes).
- Encargos concretos y breves: nombra siempre la empresa y el año, y no pidas "todo".

Información recogida hasta ahora:
{hallazgos}

Reglas para decidir:
- Cada especialista actúa UNA sola vez por pregunta: pídele todo lo necesario de golpe.
- Si ya hay información suficiente, responde FIN (o redactor si se pidió un informe).
- Si la pregunta no trata de estas empresas ni de análisis financiero, responde FIN."""

PROMPT_RESPUESTA = """Eres un analista financiero que explica cuentas anuales con claridad.
Responde usando SOLO esta información y di de dónde sale cada dato (informe o cálculo):

{hallazgos}

- Da las cifras con unidades e interpreta los ratios (bueno o malo, mejor o peor que el
  año anterior), relacionándolos con el contexto de los informes cuando lo haya.
- Las cifras y ratios del analista son exactos: si otra parte los contradice, manda el
  analista. Para decir si un ratio es alto o bajo usa solo las valoraciones de la guía
  de ratios que aparezcan arriba (las incluye el analista junto a cada ratio); no inventes
  medias del sector ni otros umbrales.
- Fuentes: "cálculo del analista" para cifras y ratios, y el nombre del fichero
  (por ejemplo hoteles_brisa.md) para lo que venga de los informes.
- Sé conciso (unas 250 palabras como máximo): empieza con la respuesta directa en una
  frase, luego viñetas o una tabla pequeña con lo esencial. No repitas todos los ratios.
- Es un análisis educativo de empresas ficticias: no recomiendes comprar ni vender.
- Markdown sencillo, sin fórmulas LaTeX.
- Si la pregunta no trata de estas empresas ni de análisis financiero, di amablemente
  que solo puedes ayudar con eso. Si falta información, dilo."""

PROMPT_REDACTOR = """Eres el redactor de informes para el comité de inversiones.
Encargo: {tarea}

Usa SOLO esta información (no inventes cifras):

{hallazgos}

Escribe un informe ejecutivo en Markdown con esta estructura:

## Informe: <empresa o empresas>
**Resumen:** tres frases con la idea principal.
### Cifras clave
Tabla con las magnitudes y ratios más relevantes (año anterior, año actual y variación).
### Fortalezas
### Debilidades y riesgos
### Conclusión
Valoración equilibrada de la situación financiera, sin recomendar comprar ni vender.

*Fuentes:* ficheros de los informes y cálculos del analista.
Sin fórmulas LaTeX."""


def _texto(estado: Estado) -> str:
    return "\n\n".join(estado.get("hallazgos", [])) or "Ninguna todavía."


async def _con_reintentos(ejecutable, entrada):
    """Llama al LLM (o a un agente) y repite si Groq rechaza la respuesta por estar mal
    formada (tool_use_failed): nombre de herramienta mal escrito, JSON roto, o no
    respetar la salida estructurada. Es un fallo puntual del modelo, no del programa."""
    for intento in range(INTENTOS):
        try:
            return await ejecutable.ainvoke(entrada)
        except Exception as error:
            if "tool_use_failed" not in str(error) or intento == INTENTOS - 1:
                raise


async def construir_grafo(modelo=None, herramientas_mcp=None):
    modelo = modelo or crear_modelo()
    especialistas = await crear_especialistas(modelo, herramientas_mcp)
    decisor = modelo.with_structured_output(Decision)  # responde con el esquema Decision
    lista_empresas = ", ".join(finanzas.nombre(c) for c in finanzas.empresas())

    # --- Nodos: reciben el estado y devuelven solo lo que cambian ---

    async def supervisor(estado: Estado) -> dict:
        if len(estado.get("hallazgos", [])) >= MAX_PASOS:
            return {"siguiente": "FIN", "tarea": ""}
        prompt = PROMPT_SUPERVISOR.format(empresas=lista_empresas, hallazgos=_texto(estado))
        decision = await _con_reintentos(decisor, [SystemMessage(prompt), *estado["messages"]])
        hallazgos = estado.get("hallazgos", [])
        ya_actuaron = {h[1:].split("]")[0] for h in hallazgos}
        # La clasificación se fija en la primera decisión y se mantiene
        necesita_contexto = (estado["necesita_contexto"] if hallazgos
                             else decision.necesita_contexto)
        siguiente, tarea = decision.siguiente, decision.tarea

        # Garantías en código (no solo en el prompt), porque el LLM no siempre las cumple:
        # 1) Cada especialista actúa una vez. Si repite, ya tiene esa información.
        if siguiente in ya_actuaron:
            siguiente, tarea = "FIN", ""
        # 2) Valoraciones, causas e informes necesitan el contexto de los informes anuales:
        #    no se responde ni se redacta sin haber pasado por el documentalista.
        if (siguiente in ("FIN", "redactor") and necesita_contexto and hallazgos
                and "documentalista" not in ya_actuaron):
            pregunta = estado["messages"][-1].text
            siguiente = "documentalista"
            tarea = ("Busca en el informe anual el contexto que explica las cifras (hechos "
                     f"relevantes, riesgos, dividendos y perspectivas) para responder a: {pregunta}")
        return {"siguiente": siguiente, "tarea": tarea, "necesita_contexto": necesita_contexto}

    def crear_nodo(nombre: str):
        async def nodo(estado: Estado) -> dict:
            # El especialista solo recibe su encargo, no toda la conversación
            entrada = {"messages": [HumanMessage(estado["tarea"])]}
            resultado = await _con_reintentos(especialistas[nombre], entrada)
            return {"hallazgos": [f"[{nombre}] {resultado['messages'][-1].text}"]}

        return nodo

    async def redactor(estado: Estado) -> dict:
        prompt = PROMPT_REDACTOR.format(tarea=estado["tarea"], hallazgos=_texto(estado))
        informe = await modelo.ainvoke([SystemMessage(prompt), *estado["messages"]])
        return {"messages": [informe]}

    async def responder(estado: Estado) -> dict:
        prompt = PROMPT_RESPUESTA.format(hallazgos=_texto(estado))
        respuesta = await modelo.ainvoke([SystemMessage(prompt), *estado["messages"]])
        return {"messages": [respuesta]}

    # --- Grafo: nodos y aristas ---

    grafo = StateGraph(Estado)
    grafo.add_node("supervisor", supervisor)
    grafo.add_node("redactor", redactor)
    grafo.add_node("responder", responder)
    for nombre in especialistas:
        grafo.add_node(nombre, crear_nodo(nombre))
        grafo.add_edge(nombre, "supervisor")  # cada especialista vuelve al supervisor

    grafo.add_edge(START, "supervisor")
    # Arista condicional: el destino depende de estado["siguiente"]
    rutas = {"documentalista": "documentalista", "analista": "analista",
             "redactor": "redactor", "FIN": "responder"}
    grafo.add_conditional_edges("supervisor", lambda estado: estado["siguiente"], rutas)
    grafo.add_edge("redactor", END)
    grafo.add_edge("responder", END)
    return grafo.compile()
