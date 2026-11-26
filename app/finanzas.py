"""Cuentas de las empresas y cálculo de ratios.

Los ratios se calculan con Python, no con el LLM: así las cifras son exactas y se
pueden comprobar (ver tests/test_finanzas.py). Lo usan el agente analista, el
servidor MCP y el panel de la web.
"""

import json
import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Callable

from app.config import RUTA_DATOS


def _div(a: float, b: float) -> float | None:
    return None if not b else a / b


@dataclass(frozen=True)
class Ratio:
    nombre: str
    formula: str
    unidad: str  # "%" (porcentaje) o "x" (veces)
    calcular: Callable[[dict], float | None]


RATIOS: dict[str, Ratio] = {
    "margen_bruto": Ratio("Margen bruto", "(Ingresos − Coste de ventas) / Ingresos", "%",
                          lambda c: _div(c["ingresos"] - c["coste_ventas"], c["ingresos"])),
    "margen_ebitda": Ratio("Margen EBITDA", "EBITDA / Ingresos", "%",
                           lambda c: _div(c["ebitda"], c["ingresos"])),
    "margen_neto": Ratio("Margen neto", "Beneficio neto / Ingresos", "%",
                         lambda c: _div(c["beneficio_neto"], c["ingresos"])),
    "roe": Ratio("ROE", "Beneficio neto / Patrimonio neto", "%",
                 lambda c: _div(c["beneficio_neto"], c["patrimonio_neto"])),
    "roa": Ratio("ROA", "Beneficio neto / Activo total", "%",
                 lambda c: _div(c["beneficio_neto"], c["activo_total"])),
    "rotacion_activos": Ratio("Rotación de activos", "Ingresos / Activo total", "x",
                              lambda c: _div(c["ingresos"], c["activo_total"])),
    "liquidez": Ratio("Liquidez", "Activo corriente / Pasivo corriente", "x",
                      lambda c: _div(c["activo_corriente"], c["pasivo_corriente"])),
    "prueba_acida": Ratio("Prueba ácida", "(Activo corriente − Existencias) / Pasivo corriente", "x",
                          lambda c: _div(c["activo_corriente"] - c["existencias"],
                                         c["pasivo_corriente"])),
    "endeudamiento": Ratio("Endeudamiento", "Deuda financiera / Patrimonio neto", "x",
                           lambda c: _div(c["deuda_financiera"], c["patrimonio_neto"])),
    "deuda_neta_ebitda": Ratio("Deuda neta / EBITDA", "(Deuda financiera − Efectivo) / EBITDA", "x",
                               lambda c: _div(c["deuda_financiera"] - c["efectivo"], c["ebitda"])),
    "cobertura_intereses": Ratio("Cobertura de intereses", "EBIT / Gastos financieros", "x",
                                 lambda c: _div(c["ebit"], c["gastos_financieros"])),
    "payout": Ratio("Payout", "Dividendos / Beneficio neto", "%",
                    lambda c: _div(c["dividendos"], c["beneficio_neto"])),
}

PARTIDAS = {
    "ingresos": "Ingresos",
    "ebitda": "EBITDA",
    "ebit": "EBIT",
    "beneficio_neto": "Beneficio neto",
    "activo_total": "Activo total",
    "patrimonio_neto": "Patrimonio neto",
    "deuda_financiera": "Deuda financiera",
    "efectivo": "Efectivo",
    "dividendos": "Dividendos",
    "empleados": "Empleados",
}


# --- Datos ---

@cache
def _datos() -> dict:
    return json.loads(RUTA_DATOS.read_text(encoding="utf-8"))


def empresas() -> list[str]:
    return list(_datos()["empresas"])


def nombre(clave: str) -> str:
    return _datos()["empresas"][clave]["nombre"]


def sector(clave: str) -> str:
    return _datos()["empresas"][clave]["sector"]


def ejercicios(clave: str) -> list[int]:
    return sorted(int(a) for a in _datos()["empresas"][clave]["cuentas"])


def cuentas(clave: str, ejercicio: int) -> dict:
    try:
        return _datos()["empresas"][clave]["cuentas"][str(ejercicio)]
    except KeyError:
        raise ValueError(f"No hay datos de {nombre(clave)} en {ejercicio}. "
                         f"Ejercicios disponibles: {ejercicios(clave)}.") from None


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpio = sin_tildes.lower().replace("_", " ").replace(".", " ")
    return " ".join(p for p in limpio.split() if p not in {"s", "a", "sa"})


def buscar_empresa(texto: str) -> str:
    """Devuelve la clave de una empresa a partir de un nombre aproximado
    ("Energía Meseta", "meseta", "energia_meseta"...)."""
    buscado = _normalizar(texto)
    for clave in empresas():
        if buscado and (buscado in _normalizar(nombre(clave)) or buscado == _normalizar(clave)):
            return clave
    disponibles = ", ".join(nombre(c) for c in empresas())
    raise ValueError(f"No conozco la empresa '{texto}'. Disponibles: {disponibles}.")


def buscar_ratio(texto: str) -> str:
    """Devuelve la clave de un ratio a partir de su clave o su nombre ("ROE", "margen ebitda"...)."""
    buscado = _normalizar(texto).replace("/", " ")
    buscado = " ".join(buscado.split())
    for clave, ratio in RATIOS.items():
        nombre_ratio = " ".join(_normalizar(ratio.nombre).replace("/", " ").split())
        if buscado in (_normalizar(clave), nombre_ratio):
            return clave
    raise ValueError(f"No conozco el ratio '{texto}'. Disponibles: {', '.join(RATIOS)}.")


# --- Cálculos ---

def calcular_ratios(clave: str, ejercicio: int) -> dict[str, float | None]:
    c = cuentas(clave, ejercicio)
    return {k: r.calcular(c) for k, r in RATIOS.items()}


def variacion(inicial: float, final: float) -> float | None:
    """Variación relativa (0,10 = +10 %)."""
    return None if not inicial else (final - inicial) / abs(inicial)


# --- Valoración según la guía de ratios (docs/guia_ratios.md) ---
# Los umbrales están escritos en código para que la valoración sea siempre la misma
# y no dependa de lo que "crea" el LLM. Formato: (límite superior, etiqueta).

UMBRALES: dict[str, list[tuple[float, str]]] = {
    "roe": [(0.05, "baja"), (0.08, "moderada, por debajo del coste del capital (8-10 %)"),
            (0.10, "en torno al coste del capital (8-10 %)"),
            (float("inf"), "alta, supera el coste del capital (8-10 %): crea valor")],
    "roa": [(0.05, "por debajo del 5 % (normal en empresas con muchos activos fijos)"),
            (float("inf"), "buena, por encima del 5 %")],
    "liquidez": [(1.0, "por debajo de 1: posibles tensiones (normal en hostelería y distribución)"),
                 (1.5, "adecuada, entre 1 y 1,5"), (float("inf"), "holgada, por encima de 1,5")],
    "prueba_acida": [(1.0, "por debajo de 1: ajustada"), (float("inf"), "cómoda, por encima de 1")],
    "endeudamiento": [(1.0, "conservador, por debajo de 1"), (2.0, "medio, entre 1 y 2"),
                      (float("inf"), "elevado, por encima de 2")],
    "deuda_neta_ebitda": [(0.0, "negativa: caja neta (más efectivo que deuda)"),
                          (2.0, "baja, por debajo de 2"), (3.5, "moderada, entre 2 y 3,5"),
                          (4.0, "moderada-alta, entre 3,5 y 4"),
                          (5.0, "elevada, por encima de 4 (en renovables se aceptan 4-5)"),
                          (float("inf"), "muy elevada, por encima de 5: riesgo de bajada de rating")],
    "cobertura_intereses": [(2.0, "ajustada, por debajo de 2"), (5.0, "aceptable, entre 2 y 5"),
                            (float("inf"), "cómoda, por encima de 5")],
    "payout": [(0.0001, "no reparte dividendo"), (0.30, "bajo, por debajo del 30 %"),
               (0.60, "sostenible, entre el 30 % y el 60 %"), (0.80, "alto, entre el 60 % y el 80 %"),
               (float("inf"), "muy alto, por encima del 80 %: puede no ser sostenible")],
}


def valorar(clave: str, valor: float | None) -> str | None:
    """Etiqueta de la guía de ratios para un valor, o None si el ratio no tiene umbral
    general (los márgenes dependen del sector)."""
    if valor is None or clave not in UMBRALES:
        return None
    return next(etiqueta for limite, etiqueta in UMBRALES[clave] if valor < limite)


# --- Formato (estilo español: coma decimal, punto de miles) ---

def _es(numero: float, decimales: int) -> str:
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def formatear_ratio(clave: str, valor: float | None) -> str:
    if valor is None:
        return "n/d"
    if RATIOS[clave].unidad == "%":
        return f"{_es(valor * 100, 1)} %"
    return f"{_es(valor, 2)}x"


def formatear_importe(partida: str, valor: float) -> str:
    if partida == "empleados":
        return _es(valor, 0)
    return f"{_es(valor, 0)} M€"


def formatear_variacion(valor: float | None) -> str:
    return "n/d" if valor is None else f"{'+' if valor >= 0 else ''}{_es(valor * 100, 1)} %"
