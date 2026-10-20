"""
margen.py — Descomposición de la desviación de margen bruto.

    Margen bruto = Ventas - Coste de ventas

    Desviación de margen = Efecto volumen + Efecto mix + Efecto precio de venta + Efecto coste unitario

"""
import pandas as pd


def descomponer_margen(real: pd.DataFrame, ppto: pd.DataFrame) -> pd.DataFrame:
    """
    real, ppto: DataFrames con columnas [categoria, unidades, ventas, coste_ventas] (agregados al periodo).
    Devuelve una fila por categoría con los cuatro efectos sobre el margen.
    """
    # --- Bloque 1: unir y calcular margen ---------------------------------------
    df = real.merge(ppto, on="categoria", suffixes=("_r", "_p"), how="outer").fillna(0)
    df["margen_r"] = df.ventas_r - df.coste_ventas_r
    df["margen_p"] = df.ventas_p - df.coste_ventas_p

    # --- Bloque 2: magnitudes unitarias ----------------------------------------
    df["precio_r"] = df.ventas_r / df.unidades_r
    df["precio_p"] = df.ventas_p / df.unidades_p
    df["coste_u_r"] = df.coste_ventas_r / df.unidades_r
    df["coste_u_p"] = df.coste_ventas_p / df.unidades_p
    df["margen_u_p"] = df.margen_p / df.unidades_p

    # --- Bloque 3: totales y mix ------------------------------------------------
    u_total_r = df.unidades_r.sum()
    u_total_p = df.unidades_p.sum()
    margen_medio_p = df.margen_p.sum() / u_total_p

    df["mix_r"] = df.unidades_r / u_total_r
    df["mix_p"] = df.unidades_p / u_total_p

    # --- Bloque 4: los cuatro efectos --------------------------------------------
    df["efecto_volumen"] = (u_total_r - u_total_p) * df.mix_p * margen_medio_p
    df["efecto_mix"] = (df.mix_r - df.mix_p) * u_total_r * df.margen_u_p
    df["efecto_precio"] = (df.precio_r - df.precio_p) * df.unidades_r
    df["efecto_coste"] = -(df.coste_u_r - df.coste_u_p) * df.unidades_r

    df["desviacion_total"] = df.margen_r - df.margen_p

    # --- Bloque 5: control de cuadre ----------------------------------------------
    efectos = ["efecto_volumen", "efecto_mix", "efecto_precio", "efecto_coste"]
    descuadre = df[efectos].sum().sum() - df.desviacion_total.sum()
    assert abs(descuadre) < 0.01, f"Los efectos no cuadran con la desviación de margen: {descuadre:.2f} €"

    return df