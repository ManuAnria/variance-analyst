"""
hechos.py — Ensambla el paquete de hechos que recibirá el LLM.  (v3)

Ejecuta los cuatro análisis (ventas, margen, personal, gastos), comprueba que juntos
explican el resultado completo de la contabilidad y guarda todo en un JSON.

v2: el motor INTERPRETA cada cifra (favorable/desfavorable, por encima/por debajo del
presupuesto, lectura de la plantilla y del patrón) para que el modelo no tenga que
deducirlo de los signos. Incluye el puente del resultado: los principales impulsores
de la desviación, ordenados por importe.

v3: los importes del puente van también ya escritos ("importe_texto": "69.083 €"),
y cada impulsor lleva su tipo y su objeto para medir si el informe lo menciona.

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
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

UMBRAL_EN_LINEA = 500        # € — por debajo, una desviación se considera "en línea"
UMBRAL_PUENTE = 10_000       # € — impulsores del resultado que se muestran por separado


# --------------------------------------------------------------------------- #
# Utilidades de formato e interpretación
# --------------------------------------------------------------------------- #
def euros(x) -> int:
    """Redondea a euros enteros: el LLM no necesita céntimos y así es más fácil validar sus cifras."""
    return int(round(float(x)))


def euros_texto(x) -> str:
    """Importe ya escrito en formato español y sin signo: -69083.4 -> '69.083 €'.
    El modelo solo tiene que copiarlo, no formatearlo."""
    return f"{abs(euros(x)):,} €".replace(",", ".")


def pct(x) -> float | None:
    """Porcentaje con un decimal (0.0743 -> 7.4)."""
    return None if x is None or pd.isna(x) else round(float(x) * 100, 1)


def valoracion(desviacion: float) -> str:
    """Convención del motor: positivo = favorable."""
    if abs(desviacion) < UMBRAL_EN_LINEA:
        return "en línea con el presupuesto"
    return "favorable" if desviacion > 0 else "desfavorable"


def comparacion(real: float, ppto: float) -> str:
    """Dirección del importe real frente al presupuesto, sin ambigüedad de signos."""
    if abs(real - ppto) < UMBRAL_EN_LINEA:
        return "en línea con el presupuesto"
    return "por encima del presupuesto" if real > ppto else "por debajo del presupuesto"


def lectura_plantilla(diferencia: float) -> str:
    d = int(round(diferencia))
    if d == 0:
        return "misma plantilla que el presupuesto"
    return f"{abs(d)} FTE-mes {'más' if d > 0 else 'menos'} que el presupuesto"


def lectura_patron(patron: str, mes_clave, mes_origen) -> str:
    # pandas guarda los meses como decimales (8.0) si la columna tiene huecos: se pasan a entero
    mes_clave = int(mes_clave) if pd.notna(mes_clave) else None
    mes_origen = int(mes_origen) if pd.notna(mes_origen) else None
    if patron == "puntual":
        return f"gasto extraordinario concentrado en {MESES[mes_clave]}"
    if patron == "recurrente":
        return f"desviación sostenida desde {MESES[mes_clave]}"
    if patron == "calendario":
        return f"gasto presupuestado en {MESES[mes_origen]} y ejecutado en {MESES[mes_clave]}"
    return "sin desviación"


def tabla(df: pd.DataFrame, clave: str, nombres: dict, columnas: list[str]) -> list[dict]:
    """Convierte un resultado por categoría o centro en filas con importes en euros y su valoración."""
    filas = []
    for _, r in df.iterrows():
        fila = {clave: r[clave], "nombre": nombres.get(r[clave], r[clave])}
        fila.update({c: euros(r[c]) for c in columnas})
        fila["valoracion"] = valoracion(r["desviacion_total"])
        filas.append(fila)
    return filas


# --------------------------------------------------------------------------- #
# Bloques del paquete
# --------------------------------------------------------------------------- #
def personal_por_centro(personal: pd.DataFrame) -> list[dict]:
    filas = tabla(personal, "centro_coste", NOMBRES_CENTROS,
                  ["fte_meses_r", "fte_meses_p", "coste_r", "coste_p",
                   "efecto_plantilla", "efecto_coste_medio", "desviacion_total"])
    for fila, (_, r) in zip(filas, personal.iterrows()):
        fila["lectura_plantilla"] = lectura_plantilla(r.fte_meses_r - r.fte_meses_p)
        fila["comparacion"] = comparacion(r.coste_r, r.coste_p)
    return filas


def gastos_materiales(gastos: pd.DataFrame) -> list[dict]:
    """Solo las partidas materiales; los gastos variables llevan además su presupuesto flexible."""
    filas = []
    for _, r in gastos[gastos.material].iterrows():
        fila = {"cuenta": r.cuenta, "nombre": r.nombre,
                "centro_coste": NOMBRES_CENTROS.get(r.centro_coste, r.centro_coste),
                "real": euros(r.real), "presupuesto": euros(r.ppto), "desviacion": euros(r.desviacion),
                "variacion_pct": abs(pct(r.desviacion_pct)),
                "valoracion": valoracion(r.desviacion), "comparacion": comparacion(r.real, r.ppto),
                "patron": r.patron, "lectura_patron": lectura_patron(r.patron, r.mes_clave, r.mes_origen)}
        if pd.notna(r.get("efecto_tarifa")):
            fila["efecto_actividad"] = euros(r.efecto_actividad)
            fila["efecto_tarifa"] = euros(r.efecto_tarifa)
            fila["lectura_flexible"] = (
                f"efecto actividad {valoracion(r.efecto_actividad)} (las ventas fueron "
                f"{'inferiores' if r.efecto_actividad > 0 else 'superiores'} a lo presupuestado); "
                f"efecto tarifa {valoracion(r.efecto_tarifa)} (el coste por euro vendido fue "
                f"{'superior' if r.efecto_tarifa < 0 else 'inferior'} al presupuestado)")
        filas.append(fila)
    return filas


def puente_resultado(margen, personal, gastos, desviacion_resultado: float) -> dict:
    """
    Todos los efectos que explican la desviación del resultado, del mayor al menor.
    Los de importe >= UMBRAL_PUENTE se muestran uno a uno; el resto se agrupa.
    Cada efecto lleva su tipo y su objeto (categoría, centro o cuenta) para que el
    validador pueda comprobar si el informe lo menciona.
    """
    # (concepto, importe, tipo, objeto)
    efectos = [("Volumen total de unidades vendidas (margen)", margen.efecto_volumen.sum(), "volumen", None)]
    for _, r in margen.iterrows():
        cat = NOMBRES_CATEGORIAS[r.categoria]
        efectos += [(f"Mix de ventas: {cat}", r.efecto_mix, "mix", cat),
                    (f"Precio de venta: {cat}", r.efecto_precio, "precio", cat),
                    (f"Coste unitario de compra: {cat}", r.efecto_coste, "coste_unitario", cat)]
    for _, r in personal.iterrows():
        centro = NOMBRES_CENTROS[r.centro_coste]
        efectos += [(f"Plantilla {centro} ({lectura_plantilla(r.fte_meses_r - r.fte_meses_p)})",
                     r.efecto_plantilla, "plantilla", centro),
                    (f"Coste medio por persona: {centro}", r.efecto_coste_medio, "coste_medio", centro)]
    for _, r in gastos.iterrows():
        nombre = f"{r.nombre} ({NOMBRES_CENTROS.get(r.centro_coste, r.centro_coste)})"
        if pd.notna(r.get("efecto_tarifa")):
            efectos += [(f"{nombre}: tarifa por euro vendido", r.efecto_tarifa, "tarifa", r.nombre),
                        (f"{nombre}: nivel de actividad", r.efecto_actividad, "actividad", r.nombre)]
        else:
            efectos.append((nombre, r.desviacion, "gasto", r.nombre))

    efectos.sort(key=lambda e: abs(e[1]), reverse=True)
    principales = [e for e in efectos if abs(e[1]) >= UMBRAL_PUENTE]
    resto = [e for e in efectos if abs(e[1]) < UMBRAL_PUENTE]

    # Control: los efectos del puente suman exactamente la desviación del resultado
    assert abs(sum(e[1] for e in efectos) - desviacion_resultado) < 1, "El puente del resultado no cuadra"

    importe_resto = sum(e[1] for e in resto)
    return {
        "desviacion_resultado": euros(desviacion_resultado),
        "desviacion_resultado_texto": euros_texto(desviacion_resultado),
        "principales_impulsores": [
            {"concepto": c, "importe": euros(i), "importe_texto": euros_texto(i),
             "valoracion": valoracion(i), "tipo": t, "objeto": o}
            for c, i, t, o in principales],
        "resto": {"numero_efectos": len(resto), "importe": euros(importe_resto),
                  "importe_texto": euros_texto(importe_resto), "valoracion": valoracion(importe_resto)},
    }


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
    cuenta_resultados = []
    for partida, (r, p) in resumen.items():
        desv = (p - r) if partida in es_gasto else (r - p)
        cuenta_resultados.append({
            "partida": partida, "real": euros(r), "presupuesto": euros(p), "desviacion": euros(desv),
            "variacion_pct": abs(pct(desv / p)), "valoracion": valoracion(desv), "comparacion": comparacion(r, p)})

    return {
        "empresa": "Grafilia Distribución S.L.",
        "periodo": f"enero a {MESES[mes_hasta]} de {ejercicio}",
        "convencion": "Desviación e importes de efectos: positivo = favorable, negativo = desfavorable. "
                      "Usa siempre los campos 'valoracion' y 'comparacion'; no deduzcas nada del signo.",

        "cuenta_resultados": cuenta_resultados,
        "margen_bruto_pct": {"real": pct(resumen["margen_bruto"][0] / resumen["ventas"][0]),
                             "presupuesto": pct(resumen["margen_bruto"][1] / resumen["ventas"][1])},

        "puente_resultado": puente_resultado(margen, personal, gastos, res_r - res_p),

        "ventas_por_categoria": tabla(ventas, "categoria", NOMBRES_CATEGORIAS,
            ["unidades_r", "unidades_p", "ventas_r", "ventas_p",
             "efecto_volumen", "efecto_mix", "efecto_precio", "desviacion_total"]),

        "margen_por_categoria": tabla(margen, "categoria", NOMBRES_CATEGORIAS,
            ["margen_r", "margen_p", "efecto_volumen", "efecto_mix",
             "efecto_precio", "efecto_coste", "desviacion_total"]),

        "personal_por_centro": personal_por_centro(personal),

        "otros_gastos_materiales": gastos_materiales(gastos),
        "otros_gastos_no_materiales": {
            "numero_partidas": int((~gastos.material).sum()),
            "desviacion_conjunta": euros(gastos[~gastos.material].desviacion.sum()),
            "valoracion": valoracion(gastos[~gastos.material].desviacion.sum()),
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
