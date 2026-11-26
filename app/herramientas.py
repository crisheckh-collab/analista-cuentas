"""Herramientas del agente analista.

Cada función decorada con @tool se convierte en una herramienta: el LLM lee el
docstring para saber cuándo usarla y qué argumentos pasarle. Si algo falla,
devuelven el error como texto para que el agente pueda corregirse.
"""

from langchain_core.tools import tool

from app import finanzas as fz


@tool
def ratios_empresa(empresa: str, ejercicio: int | None = None) -> str:
    """Calcula las cifras clave y TODOS los ratios financieros de una empresa en un
    ejercicio: margen bruto, margen EBITDA, margen neto, ROE, ROA, rotación de activos,
    liquidez, prueba ácida, endeudamiento, deuda neta/EBITDA, cobertura de intereses y
    payout. Si no se indica el ejercicio, usa el último disponible."""
    try:
        clave = fz.buscar_empresa(empresa)
        ejercicio = ejercicio or fz.ejercicios(clave)[-1]
        cuentas = fz.cuentas(clave, ejercicio)
        ratios = fz.calcular_ratios(clave, ejercicio)
    except ValueError as error:
        return f"Error: {error}"
    lineas = [f"{fz.nombre(clave)} ({fz.sector(clave)}), ejercicio {ejercicio}", "Cifras:"]
    lineas += [f"- {n}: {fz.formatear_importe(p, cuentas[p])}" for p, n in fz.PARTIDAS.items()]
    lineas.append("Ratios (con su valoración según la guía de ratios):")
    for k, r in fz.RATIOS.items():
        valoracion = fz.valorar(k, ratios[k])
        lineas.append(f"- {r.nombre} = {fz.formatear_ratio(k, ratios[k])}"
                      + (f" → {valoracion}" if valoracion else ""))
    return "\n".join(lineas)


@tool
def evolucion_empresa(empresa: str) -> str:
    """Compara los dos últimos ejercicios de una empresa: crecimiento de ingresos,
    EBITDA, beneficio, deuda... y cómo han cambiado todos sus ratios."""
    try:
        clave = fz.buscar_empresa(empresa)
    except ValueError as error:
        return f"Error: {error}"
    anios = fz.ejercicios(clave)
    if len(anios) < 2:
        return f"Solo hay datos de {anios} para {fz.nombre(clave)}."
    antes, ahora = anios[-2], anios[-1]
    c0, c1 = fz.cuentas(clave, antes), fz.cuentas(clave, ahora)
    r0, r1 = fz.calcular_ratios(clave, antes), fz.calcular_ratios(clave, ahora)

    lineas = [f"{fz.nombre(clave)}: evolución {antes} → {ahora}", "Cifras:"]
    for p, n in fz.PARTIDAS.items():
        lineas.append(f"- {n}: {fz.formatear_importe(p, c0[p])} → {fz.formatear_importe(p, c1[p])} "
                      f"({fz.formatear_variacion(fz.variacion(c0[p], c1[p]))})")
    lineas.append("Ratios:")
    for k, r in fz.RATIOS.items():
        cambio = ""
        if r0[k] is not None and r1[k] is not None:
            diferencia = r1[k] - r0[k]
            if r.unidad == "%":
                cambio = f" ({'+' if diferencia >= 0 else ''}{fz._es(diferencia * 100, 1)} p.p.)"
            else:
                cambio = f" ({'+' if diferencia >= 0 else ''}{fz._es(diferencia, 2)}x)"
        valoracion = fz.valorar(k, r1[k])
        lineas.append(f"- {r.nombre}: {fz.formatear_ratio(k, r0[k])} → "
                      f"{fz.formatear_ratio(k, r1[k])}{cambio}"
                      + (f"; en {ahora}, según la guía: {valoracion}" if valoracion else ""))
    return "\n".join(lineas)


@tool
def comparar_empresas(ratio: str, ejercicio: int | None = None) -> str:
    """Ordena todas las empresas de mayor a menor según un ratio en un ejercicio
    (por defecto, el último). ratio puede ser: margen_bruto, margen_ebitda,
    margen_neto, roe, roa, rotacion_activos, liquidez, prueba_acida, endeudamiento,
    deuda_neta_ebitda, cobertura_intereses o payout."""
    try:
        clave_ratio = fz.buscar_ratio(ratio)
        filas = []
        for clave in fz.empresas():
            anio = ejercicio or fz.ejercicios(clave)[-1]
            valor = fz.calcular_ratios(clave, anio)[clave_ratio]
            filas.append((valor, clave, anio))
    except ValueError as error:
        return f"Error: {error}"
    filas.sort(key=lambda f: float("-inf") if f[0] is None else f[0], reverse=True)
    r = fz.RATIOS[clave_ratio]
    lineas = [f"{r.nombre} [{r.formula}], de mayor a menor:"]
    for i, (v, c, a) in enumerate(filas, 1):
        valoracion = fz.valorar(clave_ratio, v)
        lineas.append(f"{i}. {fz.nombre(c)} ({fz.sector(c)}, {a}): "
                      f"{fz.formatear_ratio(clave_ratio, v)}"
                      + (f" → {valoracion}" if valoracion else ""))
    return "\n".join(lineas)


@tool
def variacion_porcentual(valor_inicial: float, valor_final: float) -> str:
    """Calcula la variación porcentual entre dos valores. Útil para escenarios
    ("si los ingresos bajaran a X...")."""
    resultado = fz.variacion(valor_inicial, valor_final)
    if resultado is None:
        return "Error: el valor inicial no puede ser 0."
    return f"De {valor_inicial} a {valor_final}: {fz.formatear_variacion(resultado)}"


HERRAMIENTAS_ANALISTA = [ratios_empresa, evolucion_empresa, comparar_empresas, variacion_porcentual]
