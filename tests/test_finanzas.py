"""Pruebas de los cálculos financieros (sin LLM ni internet).

Uso:
    python -m pytest -q
"""

import pytest

from app import finanzas as fz
from app.herramientas import comparar_empresas, evolucion_empresa, ratios_empresa


def test_cuentas_coherentes():
    """EBIT = EBITDA - amortizaciones y beneficio = EBIT - intereses - impuestos."""
    for clave in fz.empresas():
        for anio in fz.ejercicios(clave):
            c = fz.cuentas(clave, anio)
            assert c["ebit"] == c["ebitda"] - c["amortizaciones"], (clave, anio)
            assert c["beneficio_neto"] == c["ebit"] - c["gastos_financieros"] - c["impuestos"]


def test_ratios_calculados_a_mano():
    r = fz.calcular_ratios("textil_atlantico", 2024)
    assert r["roe"] == pytest.approx(586 / 3200)
    assert r["margen_bruto"] == pytest.approx((4600 - 2000) / 4600)
    assert r["deuda_neta_ebitda"] == pytest.approx((380 - 1300) / 1200)  # caja neta: negativo

    r = fz.calcular_ratios("energia_meseta", 2024)
    assert r["margen_ebitda"] == pytest.approx(880 / 1650)
    assert r["deuda_neta_ebitda"] == pytest.approx((5800 - 350) / 880)
    assert r["cobertura_intereses"] == pytest.approx(410 / 230)
    assert r["payout"] == pytest.approx(120 / 135)

    r = fz.calcular_ratios("hoteles_brisa", 2023)
    assert r["liquidez"] == pytest.approx(420 / 610)
    assert r["payout"] == 0


def test_buscar_empresa_y_ratio():
    assert fz.buscar_empresa("Energía Meseta") == "energia_meseta"
    assert fz.buscar_empresa("energia_meseta") == "energia_meseta"
    assert fz.buscar_empresa("brisa") == "hoteles_brisa"
    assert fz.buscar_empresa("TEXTIL ATLANTICO S.A.") == "textil_atlantico"
    assert fz.buscar_ratio("ROE") == "roe"
    assert fz.buscar_ratio("Margen EBITDA") == "margen_ebitda"
    assert fz.buscar_ratio("deuda neta / EBITDA") == "deuda_neta_ebitda"
    with pytest.raises(ValueError):
        fz.buscar_empresa("Inditex")


def test_formato_espanol():
    assert fz.formatear_ratio("roe", 586 / 3200) == "18,3 %"
    assert fz.formatear_ratio("liquidez", 2600 / 1600) == "1,62x"
    assert fz.formatear_importe("ingresos", 4600) == "4.600 M€"
    assert fz.formatear_variacion(fz.variacion(4200, 4600)) == "+9,5 %"


def test_valoracion_segun_la_guia():
    # Umbrales de docs/guia_ratios.md
    assert fz.valorar("deuda_neta_ebitda", (1350 - 230) / 410).startswith("moderada")  # 2,73x
    assert fz.valorar("deuda_neta_ebitda", (5800 - 350) / 880).startswith("muy elevada")  # 6,19x
    assert fz.valorar("deuda_neta_ebitda", (380 - 1300) / 1200).startswith("negativa")  # caja neta
    assert fz.valorar("cobertura_intereses", 410 / 230).startswith("ajustada")  # 1,78x
    assert fz.valorar("cobertura_intereses", 260 / 55).startswith("aceptable")  # 4,73x
    assert fz.valorar("liquidez", 480 / 640).startswith("por debajo de 1")
    assert fz.valorar("payout", 120 / 135).startswith("muy alto")  # 89 %
    assert fz.valorar("payout", 0) == "no reparte dividendo"
    assert fz.valorar("roe", 586 / 3200).startswith("alta")
    assert fz.valorar("margen_bruto", 0.5) is None  # depende del sector: sin umbral


def test_herramientas_del_analista():
    assert "ROE = 18,3 %" in ratios_empresa.invoke({"empresa": "Textil Atlántico", "ejercicio": 2024})
    assert "Error" in ratios_empresa.invoke({"empresa": "Inditex"})
    assert "-45,6 %" in evolucion_empresa.invoke({"empresa": "Energía Meseta"})  # beneficio neto
    ranking = comparar_empresas.invoke({"ratio": "margen_ebitda"})
    assert ranking.index("Energía Meseta") < ranking.index("Hoteles Brisa") < ranking.index("Textil")
