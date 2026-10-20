"""
hechos.py — Ensambla el paquete de hechos que recibirá el LLM.

Ejecuta los cuatro análisis (ventas, margen, personal, gastos), comprueba que juntos
explican el resultado completo de la contabilidad y guarda todo en un JSON.

El LLM solo podrá citar cifras que estén en este paquete.

Uso:  python hechos.py        -> salidas/hechos_desviaciones.json
"""
import json
from pathlib import Path

import pandas as pd

import carga
from gastos import analizar_gastos
from margen import descomponer_margen
from personal import descomponer_personal
from ventas import descomponer_ventas

RUTA_SALIDAS = Path(__file__).resolve().parent.parent / "salidas"
NOMBRES_CATEGORIAS = {"PAP": "Papel y cuadernos", "ESC": "Material escolar", "OFI": "Material de oficina",
                      "TEC": "Tecnología educativa", "LIB": "Libros"}
NOMBRES_CENTROS = {"COM": "Comercial", "LOG": "Logística", "ADM": "Administración", "DIR": "Dirección"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def euros(x) -> int:
    """Redondea a euros enteros: el LLM no necesita céntimos y así es más fácil validar sus cifras."""
    return int(round(float(x)))


def pct(x) -> float | None:
    """Porcentaje con un decimal (0.0743 -> 7.4)."""
    return None if x is None or pd.isna(x) else round(float(x) * 100, 1)


def tabla(df: pd.DataFrame, clave: str, nombres: dict, columnas: list[str]) -> list[dict]:
    """Convierte un DataFrame de resultados en una lista de diccionarios con importes en euros."""
    filas = []
    for _, r in df.iterrows():
        fila = {clave: r[clave], "nombre": nombres.get(r[clave], r[clave])}
        fila.update({c: euros(r[c]) for c in columnas})
        filas.append(fila)
    return filas


def gastos_materiales(gastos: pd.DataFrame) -> list[dict]:
    """Solo las partidas materiales; los gastos variables llevan además su presupuesto flexible."""
    filas = []
    for _, r in gastos[gastos.material].iterrows():
        fila = {"cuenta": r.cuenta, "nombre": r.nombre,
                "centro_coste": NOMBRES_CENTROS.get(r.centro_coste, r.centro_coste),
                "real": euros(r.real), "presupuesto": euros(r.ppto), "desviacion": euros(r.desviacion),
                "desviacion_pct": pct(r.desviacion_pct), "patron": r.patron, "mes_clave": int(r.mes_clave)}
        if pd.notna(r.get("efecto_tarifa")):
            fila["efecto_actividad"] = euros(r.efecto_actividad)
            fila["efecto_tarifa"] = euros(r.efecto_tarifa)
        filas.append(fila)
    return filas


# --------------------------------------------------------------------------- #
# Ensamblaje
# --------------------------------------------------------------------------- #
def construir_hechos(ejercicio: int, mes_hasta: int) -> dict:
    # --- 1. Datos de entrada, agregados al periodo -------------------------------
    v_r = carga.ventas_reales_por_categoria(ejercicio, mes_hasta).groupby("categoria", as_index=False)[["unidades", "ventas"]].sum()
    v_p = carga.ventas_presupuesto_por_categoria(mes_hasta).groupby("categoria", as_index=False)[["unidades", "ventas"]].sum()
    c_r = carga.coste_ventas_real_por_categoria(ejercicio, mes_hasta).groupby("categoria", as_index=False).coste_ventas.sum()
    c_p = carga.coste_ventas_presupuesto_por_categoria(mes_hasta).groupby("categoria", as_index=False).coste_ventas.sum()
    g_r = carga.gastos_real_por_mes(ejercicio, mes_hasta)
    g_p = carga.gastos_presupuesto_por_mes(mes_hasta)

    # --- 2. Los cuatro análisis ----------------------------------------------------
    ventas = descomponer_ventas(v_r, v_p)
    margen = descomponer_margen(v_r.merge(c_r), v_p.merge(c_p))
    personal = descomponer_personal(carga.personal_real_por_centro(ejercicio, mes_hasta),
                                    carga.personal_presupuesto_por_centro(mes_hasta))
    gastos = analizar_gastos(g_r, g_p, carga.nombres_cuentas(), carga.ventas_mensuales(ejercicio, mes_hasta))

    # --- 3. Cuenta de resultados resumida -------------------------------------------
    resumen = {
        "ventas":              (ventas.ventas_r.sum(), ventas.ventas_p.sum()),
        "margen_bruto":        (margen.margen_r.sum(), margen.margen_p.sum()),
        "gastos_personal":     (personal.coste_r.sum(), personal.coste_p.sum()),
        "otros_gastos":        (gastos.real.sum(), gastos.ppto.sum()),
    }
    res_r = resumen["margen_bruto"][0] - resumen["gastos_personal"][0] - resumen["otros_gastos"][0]
    res_p = resumen["margen_bruto"][1] - resumen["gastos_personal"][1] - resumen["otros_gastos"][1]
    resumen["resultado_antes_impuestos"] = (res_r, res_p)

    # --- 4. Control: el resultado del motor debe coincidir con la contabilidad --------
    res_contable = carga.resultado_contable(ejercicio, mes_hasta)
    assert abs(res_r - res_contable) < 1, \
        f"El motor no explica el resultado contable: {res_r:,.2f} vs {res_contable:,.2f}"

    # --- 5. Paquete de hechos ------------------------------------------------------------
    es_gasto = {"gastos_personal", "otros_gastos"}
    return {
        "empresa": "Grafilia Distribución S.L.",
        "periodo": {"ejercicio": ejercicio, "desde_mes": 1, "hasta_mes": mes_hasta},
        "convencion_signos": "Desviación positiva = favorable; negativa = desfavorable.",

        "cuenta_resultados": [
            {"partida": k, "real": euros(r), "presupuesto": euros(p),
             "desviacion": euros((p - r) if k in es_gasto else (r - p)),
             "desviacion_pct": pct(((p - r) if k in es_gasto else (r - p)) / p)}
            for k, (r, p) in resumen.items()
        ],
        "margen_bruto_pct": {"real": pct(resumen["margen_bruto"][0] / resumen["ventas"][0]),
                             "presupuesto": pct(resumen["margen_bruto"][1] / resumen["ventas"][1])},

        "ventas_por_categoria": tabla(ventas, "categoria", NOMBRES_CATEGORIAS,
            ["unidades_r", "unidades_p", "ventas_r", "ventas_p",
             "efecto_volumen", "efecto_mix", "efecto_precio", "desviacion_total"]),

        "margen_por_categoria": tabla(margen, "categoria", NOMBRES_CATEGORIAS,
            ["margen_r", "margen_p", "efecto_volumen", "efecto_mix",
             "efecto_precio", "efecto_coste", "desviacion_total"]),

        "personal_por_centro": tabla(personal, "centro_coste", NOMBRES_CENTROS,
            ["fte_meses_r", "fte_meses_p", "coste_r", "coste_p",
             "efecto_plantilla", "efecto_coste_medio", "desviacion_total"]),

        "otros_gastos_materiales": gastos_materiales(gastos),
        "otros_gastos_no_materiales": {
            "numero_partidas": int((~gastos.material).sum()),
            "desviacion_conjunta": euros(gastos[~gastos.material].desviacion.sum()),
        },
    }


def guardar_hechos(hechos: dict, nombre: str = "hechos_desviaciones.json") -> Path:
    RUTA_SALIDAS.mkdir(exist_ok=True)
    ruta = RUTA_SALIDAS / nombre
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(hechos, f, ensure_ascii=False, indent=2)
    return ruta


if __name__ == "__main__":
    h = construir_hechos(2026, 9)
    print(f"Hechos guardados en {guardar_hechos(h)}")