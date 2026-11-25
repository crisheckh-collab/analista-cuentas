# Analista de cuentas anuales

Página web con un **equipo de agentes de IA** que analiza las cuentas anuales de tres empresas:
calcula sus ratios, explica por qué han cambiado con lo que dicen sus informes anuales, las compara
y redacta informes para un comité de inversiones.

Es mi proyecto propio a partir del patrón del manual (supervisor con LangGraph + RAG en ChromaDB
servido por MCP), aplicado a un problema de finanzas corporativas.

> Las tres empresas (Textil Atlántico, Energía Meseta y Hoteles Brisa) son **ficticias**, con cuentas
> inventadas pero coherentes entre sí (los tests lo comprueban). Así se evitan errores de datos y
> derechos de los informes reales. Es una herramienta educativa: no da recomendaciones de inversión.

## Qué hace

**Chat con el equipo de agentes.** Por ejemplo:

- «¿Está Hoteles Brisa en una situación financiera sana?»
- «¿Por qué bajó el beneficio de Energía Meseta en 2024?»
- «¿Qué empresa tuvo mayor margen EBITDA en 2024?»
- «Prepárame un informe para el comité sobre Textil Atlántico» (se descarga en `.md`)

**Panel de ratios.** Muestra:

- Las cifras clave de la empresa, con su variación anual.
- La tabla de los 12 ratios con su fórmula.
- Un gráfico que compara las tres empresas en el ratio que elijas.

Todo se calcula con Python, sin LLM.

## Arquitectura

```
                         ┌──────────────► 🧮 Analista ── herramientas Python ──► datos/empresas.json
                         │                  (ratios, evolución, rankings)
Usuario ─► 🧭 Supervisor ┤
           (LangGraph)   ├──────────────► 📚 Documentalista ──MCP──► servidor_mcp.py ──► ChromaDB ◄── ingesta ◄── docs/*.md
              ▲          │                  (informes anuales + guía de ratios)
              │          │
              └── cada especialista vuelve al supervisor
                         │
                         ├─ si pide un informe ─► 📝 Redactor ──► informe para el comité
                         └─ resto ──────────────► Responder ───► respuesta
```

| Agente | Qué hace | Herramientas |
|---|---|---|
| **Supervisor** | Decide quién actúa (salida estructurada con Pydantic) | — |
| **Analista** | Cifras y ratios exactos | `ratios_empresa`, `evolucion_empresa`, `comparar_empresas`, `variacion_porcentual` |
| **Documentalista** | Contexto, riesgos y cómo interpretar los ratios (RAG) | `buscar_informes` (vía MCP, con filtro por empresa) |
| **Redactor** | Informe ejecutivo con estructura fija | — |

### Decisiones de diseño

1. **Los números no los calcula el LLM.** Un LLM puede equivocarse al dividir. Los ratios se calculan
   en `app/finanzas.py`, que comprueban los tests. El LLM solo decide qué herramienta usar y
   cómo explicar el resultado.
2. **Datos estructurados y texto, separados.** Las cuentas están en JSON, para los cálculos y el
   panel. Las explicaciones están en Markdown, para el RAG. Cada fuente se usa para lo que sirve.
3. **RAG con metadatos.** Cada fragmento lleva su empresa en los metadatos, y `buscar_informes`
   puede filtrar por ella, para no mezclar los riesgos de una empresa con los de otra. Además, a
   cada fragmento se le antepone el título del informe, porque un trozo suelto («los gastos
   financieros subieron…») no dice de qué empresa es.
4. **La valoración tampoco la decide el LLM.** Los umbrales de `docs/guia_ratios.md` también están
   en código (`finanzas.UMBRALES`). Cada ratio sale de las herramientas ya valorado, por ejemplo
   «Deuda neta / EBITDA = 6,19x → muy elevada, por encima de 5». En las pruebas, cuando el LLM
   valoraba por su cuenta, se inventaba umbrales («> 1,5x es cómodo») o medias del sector. La guía
   sigue en el RAG para explicar el porqué de cada ratio.
5. **Tercer especialista (redactor) y ruta propia.** El grafo tiene dos salidas: `responder` para
   preguntas y `redactor` para informes.
6. **Garantías en código, no solo en el prompt.** El supervisor clasifica la pregunta
   (`necesita_contexto`), y el grafo impone dos reglas:
   - Cada especialista actúa como mucho una vez por pregunta, para que no haya bucles.
   - Si la pregunta pide valorar, explicar causas o un informe, no se puede responder ni redactar
     sin pasar por el documentalista.

   En las pruebas, el supervisor a veces se saltaba este paso aunque el prompt lo pedía.
7. **Robustez:**
   - Reintentos si Groq rechaza una respuesta mal formada (`tool_use_failed`), tanto en el
     supervisor como en los especialistas.
   - El cliente reintenta los errores 429.
   - `MAX_PASOS` pone un límite de seguridad.
8. **Prompts contra alucinaciones.** El documentalista no puede estimar cifras. Si hay
   contradicciones, mandan las cifras del analista.

## Estructura

| Fichero | Qué hace |
|---|---|
| `datos/empresas.json` | Cuentas de 2023 y 2024 de las tres empresas |
| `docs/*.md` | Informes anuales (uno por empresa) y guía de interpretación de ratios |
| `app/config.py` | Rutas, LLM (Groq) y embeddings locales (fastembed) |
| `app/finanzas.py` | Ratios, búsqueda de empresas y formato español (sin LLM) |
| `app/herramientas.py` | Herramientas del analista |
| `app/ingesta.py` | Trocea los informes (700/100) con metadatos y los guarda en ChromaDB |
| `app/servidor_mcp.py` | Servidor MCP: `buscar_informes`, `listar_empresas`, `cifras_empresa` |
| `app/agentes.py` | Documentalista y analista (`create_agent`) |
| `app/grafo.py` | Grafo de LangGraph: supervisor, especialistas, redactor y respuesta |
| `app_web.py` | **Página web** (Streamlit): chat y panel de ratios |
| `main.py` | Preguntar desde la consola |
| `probar_mcp.py` | Probar el servidor MCP sin LLM |
| `probar_preguntas.py` | Batería de 7 preguntas → `resultados.md` |
| `tests/test_finanzas.py` | Tests de los cálculos (pytest) |

## Puesta en marcha (Windows, PowerShell)

> ⚠️ **Si la carpeta está en OneDrive, crea el entorno virtual fuera de OneDrive.** La protección de
> OneDrive de la universidad pone en cuarentena algunos ficheros de las librerías (por ejemplo de
> `langsmith`) y Python falla con `ModuleNotFoundError`.

```powershell
python -m venv $HOME\venvs\analista-cuentas      # entorno fuera de OneDrive
& $HOME\venvs\analista-cuentas\Scripts\Activate.ps1
pip install -r requirements.txt
```

(Si la carpeta no está en OneDrive, vale el `python -m venv .venv` de siempre.)

Copia `.env.example` como `.env` y pon tu clave gratuita de Groq (https://console.groq.com/keys):

```
GROQ_API_KEY=gsk_...
MODELO=groq:openai/gpt-oss-120b
```

Después:

```powershell
$env:PYTHONUTF8=1
python -m pytest -q                  # 1. tests de cálculos y valoraciones (6 passed)
python -m app.ingesta                # 2. RAG: docs -> ChromaDB (23 fragmentos)
python probar_mcp.py                 # 3. servidor MCP sin LLM
python main.py "¿Por qué bajó el beneficio de Energía Meseta en 2024?"
streamlit run app_web.py             # 4. página web en http://localhost:8501
python probar_preguntas.py           # 5. batería de pruebas -> resultados.md
```

## Extra: el servidor MCP desde Claude Code

El mismo servidor sirve a cualquier cliente MCP. Desde la carpeta del proyecto:

```powershell
$p = (Get-Location).Path
$py = "$HOME\venvs\analista-cuentas\Scripts\python.exe"
claude mcp add --env "PYTHONPATH=$p" --env PYTHONUTF8=1 --transport stdio informes -- $py -m app.servidor_mcp
claude mcp list        # informes: ... - √ Connected
```

Así, Claude Code puede buscar en los informes (`buscar_informes`) y leer las cuentas con sus ratios
(`cifras_empresa`).

## Limitaciones

- **Plan gratuito de Groq:** 8.000 tokens por minuto y 200.000 tokens al día con
  `openai/gpt-oss-120b`.
  - Una pregunta con varios agentes consume entre 10.000 y 20.000 tokens y tarda entre 30 y 90
    segundos, porque el cliente espera cuando se alcanza el límite por minuto.
  - Con el límite diario caben unas 10-15 preguntas complejas.
  - Para reducir el consumo, gpt-oss trabaja con `reasoning_effort="low"`, las búsquedas devuelven
    como mucho 3-4 fragmentos y los especialistas resumen lo que encuentran.
- **gpt-oss-20b no es recomendable.** Tiene su propia cuota y sirve de reserva poniendo
  `MODELO=groq:openai/gpt-oss-20b`, pero en las pruebas se inventaba cifras y dejaba respuestas
  vacías.
- **Datos limitados:** son tres empresas ficticias con dos ejercicios. Para usar empresas reales
  basta con añadir sus cuentas a `datos/empresas.json` y su informe a `docs/` (con el mismo nombre
  que la clave), y repetir la ingesta.

## Resultados

En `resultados.md` está la batería de 7 preguntas:

- Solo el analista.
- Una comparativa entre empresas.
- Solo el documentalista.
- Dos preguntas que combinan analista y documentalista.
- Un informe del redactor.
- Una pregunta fuera de tema.
