"""
personal.py — Descomposición de la desviación de gastos de personal.

    Coste de personal = FTE-mes x Coste medio por FTE-mes

    Desviación = Efecto plantilla + Efecto coste medio
    Signo: positivo = favorable (gastamos menos de lo presupuestado)
"""
import pandas as pd


def descomponer_personal(real: pd.DataFrame, ppto: pd.DataFrame) -> pd.DataFrame:
    """
    real, ppto: DataFrames con columnas [centro_coste, fte_meses, coste] (agregados al periodo).
    Devuelve una fila por centro de coste con los dos efectos.
    """
    # --- Bloque 1: unir real y presupuesto ----------------------------------------
    df = real.merge(ppto, on="centro_coste", suffixes=("_r", "_p"), how="outer").fillna(0)

    # --- Bloque 2: coste medio por FTE-mes ------------------------------------------
    df["coste_fte_r"] = df.coste_r / df.fte_meses_r
    df["coste_fte_p"] = df.coste_p / df.fte_meses_p

    # --- Bloque 3: los dos efectos (signo: positivo = favorable) --------------------
    df["efecto_plantilla"] = -(df.fte_meses_r - df.fte_meses_p) * df.coste_fte_p
    df["efecto_coste_medio"] = -(df.coste_fte_r - df.coste_fte_p) * df.fte_meses_r

    df["desviacion_total"] = df.coste_p - df.coste_r

    # --- Bloque 4: control de cuadre --------------------------------------------------
    efectos = ["efecto_plantilla", "efecto_coste_medio"]
    descuadre = df[efectos].sum().sum() - df.desviacion_total.sum()
    assert abs(descuadre) < 0.01, f"Los efectos no cuadran con la desviación de personal: {descuadre:.2f} €"

    return df