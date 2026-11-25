"""Interfaz web del analista de cuentas anuales (Streamlit).

Dos vistas:
- Chat con el equipo de agentes (supervisor + analista + documentalista + redactor).
- Panel de ratios: cifras y gráficos calculados directamente con Python, sin LLM.

Uso:
    streamlit run app_web.py
"""

import asyncio
import queue
import threading

import pandas as pd
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from app import finanzas as fz
from app.config import CARPETA_CHROMA, CARPETA_DOCS
from app.grafo import construir_grafo

st.set_page_config(page_title="Analista de cuentas", page_icon="📈", layout="wide")

EJEMPLOS = [
    "¿Está Hoteles Brisa en una situación financiera sana?",
    "¿Por qué bajó el beneficio de Energía Meseta en 2024?",
    "¿Qué empresa es más rentable para el accionista en 2024?",
    "Prepárame un informe para el comité sobre Textil Atlántico.",
]
ICONOS = {"supervisor": "🧭", "documentalista": "📚", "analista": "🧮", "redactor": "📝"}


# --- Motor: el grafo vive en un bucle asyncio propio, en un hilo aparte ---
# Streamlit vuelve a ejecutar el script en cada interacción; con cache_resource
# el grafo (y el servidor MCP) se construyen una sola vez.

@st.cache_resource(show_spinner="Arrancando agentes y servidor MCP...")
def motor():
    bucle = asyncio.new_event_loop()
    threading.Thread(target=bucle.run_forever, daemon=True).start()
    grafo = asyncio.run_coroutine_threadsafe(construir_grafo(), bucle).result()
    return bucle, grafo


async def _ejecutar(grafo, mensajes, cola: queue.Queue):
    """Recorre el grafo y va metiendo cada paso en la cola."""
    try:
        async for paso in grafo.astream({"messages": mensajes}, stream_mode="updates"):
            for nodo, cambios in paso.items():
                cola.put((nodo, cambios))
    except Exception as error:  # se muestra en la interfaz
        cola.put(("error", error))
    finally:
        cola.put(None)


def describir(nodo: str, cambios: dict) -> str:
    if nodo == "supervisor":
        siguiente = cambios["siguiente"]
        if siguiente == "FIN":
            return "🧭 **Supervisor**: ya hay información suficiente."
        return f"🧭 **Supervisor** → {ICONOS.get(siguiente, '➡️')} *{siguiente}*: {cambios['tarea']}"
    _, _, texto = cambios["hallazgos"][-1].partition("] ")
    return f"{ICONOS.get(nodo, '•')} **{nodo.capitalize()}**:\n\n{texto}"


# --- Vista 1: chat ---

def vista_chat(ver_pasos: bool) -> None:
    st.title("📈 Analista de cuentas anuales")
    st.caption("Pregunta por la rentabilidad, la deuda o los riesgos de las empresas, "
               "compáralas o pide un informe para el comité.")

    if "historial" not in st.session_state:
        st.session_state.historial = []  # dicts: rol, texto, pasos, informe

    for i, msg in enumerate(st.session_state.historial):
        with st.chat_message(msg["rol"]):
            if msg.get("pasos") and ver_pasos:
                with st.expander("Cómo se ha resuelto", expanded=False):
                    for linea in msg["pasos"]:
                        st.markdown(linea)
            st.markdown(msg["texto"])
            if msg.get("informe"):
                st.download_button("⬇️ Descargar informe (.md)", msg["texto"],
                                   file_name="informe_comite.md", key=f"descarga_{i}")

    pregunta = st.chat_input("Escribe tu pregunta...") or st.session_state.pop("pendiente", None)
    if not st.session_state.historial and not pregunta:
        st.write("**Prueba con:**")
        columnas = st.columns(2)
        for i, ejemplo in enumerate(EJEMPLOS):
            if columnas[i % 2].button(ejemplo, use_container_width=True):
                st.session_state.pendiente = ejemplo  # se procesa tras recargar, sin botones
                st.rerun()

    if not pregunta:
        return

    st.session_state.historial.append({"rol": "user", "texto": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    # Memoria: se pasan los últimos mensajes para entender preguntas de seguimiento
    mensajes = [
        HumanMessage(m["texto"]) if m["rol"] == "user" else AIMessage(m["texto"])
        for m in st.session_state.historial[-6:]
    ]

    with st.chat_message("assistant"):
        bucle, grafo = motor()
        cola: queue.Queue = queue.Queue()
        asyncio.run_coroutine_threadsafe(_ejecutar(grafo, mensajes, cola), bucle)

        pasos, respuesta, informe = [], None, False
        with st.status("Analizando...", expanded=ver_pasos) as estado:
            while (item := cola.get()) is not None:
                nodo, cambios = item
                if nodo == "error":
                    respuesta = f"⚠️ Error: `{cambios}`"
                    if "429" in str(cambios) or "rate" in str(cambios).lower():
                        respuesta += "\n\nLímite de Groq: espera un minuto y repite la pregunta."
                elif nodo in ("responder", "redactor"):
                    respuesta = cambios["messages"][-1].text
                    informe = nodo == "redactor"
                    if informe:
                        pasos.append("📝 **Redactor**: informe para el comité redactado.")
                        st.markdown(pasos[-1])
                else:
                    pasos.append(describir(nodo, cambios))
                    st.markdown(pasos[-1])
            estado.update(label="Resuelto", state="complete", expanded=False)

        st.markdown(respuesta or "No he obtenido respuesta.")
        if informe:
            st.download_button("⬇️ Descargar informe (.md)", respuesta,
                               file_name="informe_comite.md", key="descarga_nueva")
    st.session_state.historial.append(
        {"rol": "assistant", "texto": respuesta or "", "pasos": pasos, "informe": informe}
    )


# --- Vista 2: panel de ratios (sin LLM) ---

def _valor_grafico(clave_ratio: str, valor: float | None) -> float | None:
    if valor is None:
        return None
    return round(valor * 100, 2) if fz.RATIOS[clave_ratio].unidad == "%" else round(valor, 2)


def vista_panel() -> None:
    st.title("📊 Panel de ratios")
    st.caption("Calculado directamente a partir de las cuentas (datos/empresas.json), sin LLM. "
               "Importes en millones de euros.")

    col_empresa, col_anio = st.columns([3, 1])
    clave = col_empresa.selectbox("Empresa", fz.empresas(), format_func=fz.nombre)
    anios = fz.ejercicios(clave)
    anio = col_anio.selectbox("Ejercicio", anios[::-1])
    anterior = anio - 1 if anio - 1 in anios else None
    cuentas = fz.cuentas(clave, anio)
    st.markdown(f"**{fz.nombre(clave)}** · {fz.sector(clave)}")

    # Cifras clave con variación frente al año anterior
    columnas = st.columns(4)
    for col, partida in zip(columnas, ["ingresos", "ebitda", "beneficio_neto", "deuda_financiera"]):
        delta = None
        if anterior:
            delta = fz.formatear_variacion(
                fz.variacion(fz.cuentas(clave, anterior)[partida], cuentas[partida]))
        col.metric(f"{fz.PARTIDAS[partida]} (M€)", fz._es(cuentas[partida], 0), delta,
                   delta_color="inverse" if partida == "deuda_financiera" else "normal")

    # Ratios de la empresa en todos sus ejercicios
    st.subheader("Ratios de la empresa")
    tabla = pd.DataFrame(
        {str(a): {r.nombre: fz.formatear_ratio(k, v)
                  for (k, r), v in zip(fz.RATIOS.items(), fz.calcular_ratios(clave, a).values())}
         for a in anios}
    )
    ratios_anio = fz.calcular_ratios(clave, anio)
    tabla[f"Valoración {anio} (guía)"] = [fz.valorar(k, ratios_anio[k]) or "depende del sector"
                                         for k in fz.RATIOS]
    tabla["Fórmula"] = [r.formula for r in fz.RATIOS.values()]
    st.table(tabla)

    # Comparativa de un ratio entre empresas
    st.subheader("Comparativa entre empresas")
    clave_ratio = st.selectbox("Ratio", list(fz.RATIOS), index=list(fz.RATIOS).index("roe"),
                               format_func=lambda k: fz.RATIOS[k].nombre)
    ratio = fz.RATIOS[clave_ratio]
    datos = pd.DataFrame(
        {str(a): {fz.nombre(c): _valor_grafico(clave_ratio, fz.calcular_ratios(c, a)[clave_ratio])
                  for c in fz.empresas()}
         for a in anios}
    )
    unidad = "%" if ratio.unidad == "%" else "veces"
    # Barras horizontales: los nombres de las empresas se leen enteros
    st.bar_chart(datos, stack=False, horizontal=True, x_label=f"{ratio.nombre} ({unidad})",
                 y_label="", height=320)
    st.caption(f"{ratio.nombre} = {ratio.formula}. La interpretación de cada ratio está en "
               "docs/guia_ratios.md (pregúntale al chat).")


# --- Barra lateral y navegación ---

with st.sidebar:
    st.header("📈 Analista de cuentas")
    vista = st.radio("Vista", ["💬 Chat con el analista", "📊 Panel de ratios"],
                     label_visibility="collapsed")
    st.caption("Supervisor (LangGraph) + analista (ratios) + documentalista (RAG con "
               "ChromaDB vía MCP) + redactor de informes.")
    st.subheader("Empresas (ficticias)")
    for c in fz.empresas():
        st.markdown(f"- **{fz.nombre(c)}** · {fz.sector(c)}")
    st.subheader("Documentos")
    for fichero in sorted(CARPETA_DOCS.glob("*.md")):
        st.markdown(f"- `{fichero.name}`")
    if not CARPETA_CHROMA.exists():
        st.warning("No existe chroma_db/. Ejecuta `python -m app.ingesta`.")
    ver_pasos = st.toggle("Mostrar razonamiento de los agentes", value=True)
    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state.historial = []
        st.rerun()

if vista.startswith("💬"):
    vista_chat(ver_pasos)
else:
    vista_panel()
