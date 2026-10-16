"""
ventas.py — Descomposición de la desviación de ventas: volumen, mix y precio.

    Desviación total = Ventas reales - Ventas presupuestadas
                     = Efecto volumen + Efecto mix + Efecto precio   (cuadra exacto)
"""
import pandas as pd


def descomponer_ventas(real: pd.DataFrame, ppto: pd.DataFrame) -> pd.DataFrame:
    """
    real, ppto: DataFrames con columnas [categoria, unidades, ventas] (ya agregados al periodo).
    Devuelve una fila por categoría con los tres efectos.
    """
    # --- Bloque 1: unir real y presupuesto por categoría -------------------------
    df = real.merge(ppto, on="categoria", suffixes=("_r", "_p"), how="outer").fillna(0)

    # --- Bloque 2: precios medios ------------------------------------------------
    df["precio_r"] = df.ventas_r / df.unidades_r
    df["precio_p"] = df.ventas_p / df.unidades_p

    # --- Bloque 3: totales y mix (peso de cada categoría en las unidades) --------
    u_total_r = df.unidades_r.sum()
    u_total_p = df.unidades_p.sum()
    precio_medio_p = df.ventas_p.sum() / u_total_p

    df["mix_r"] = df.unidades_r / u_total_r
    df["mix_p"] = df.unidades_p / u_total_p

    # --- Bloque 4: los tres efectos ----------------------------------------------
    df["efecto_volumen"] = (u_total_r - u_total_p) * df.mix_p * precio_medio_p
    df["efecto_mix"] = (df.mix_r - df.mix_p) * u_total_r * df.precio_p
    df["efecto_precio"] = (df.precio_r - df.precio_p) * df.unidades_r

    df["desviacion_total"] = df.ventas_r - df.ventas_p

    # --- Bloque 5: control de cuadre -----------------------------------------------
    suma_efectos = df[["efecto_volumen", "efecto_mix", "efecto_precio"]].sum().sum()
    descuadre = suma_efectos - df.desviacion_total.sum()
    assert abs(descuadre) < 0.01, f"Los efectos no cuadran con la desviación: {descuadre:.2f} €"

    return df