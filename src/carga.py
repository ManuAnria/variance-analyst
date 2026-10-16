"""
carga.py — Lectura de datos reales y presupuestados.

Hoy lee los CSV; más adelante se cambia por consultas a Postgres
sin tocar el resto del proyecto (el motor solo ve DataFrames).
"""

from pathlib import Path

import pandas as pd

RUTA_DATOS = Path(__file__).resolve().parent.parent / "datos"

def ventas_reales_por_categoria(ejercicio: int, mes_hasta: int) -> pd.DataFrame:
    """Unidades y ventas reales por mes y categoría, desde el libro de facturas emitidas."""
    cab = pd.read_csv(RUTA_DATOS / "facturas_emitidas.csv", parse_dates=["fecha"])
    lin = pd.read_csv(RUTA_DATOS / "facturas_emitidas_lineas.csv")

    df = lin.merge(cab[["factura_id", "fecha"]], on="factura_id")
    df = df[(df.fecha.dt.year == ejercicio) & (df.fecha.dt.month <= mes_hasta)]
    df["mes"] = df.fecha.dt.month

    return (df.groupby(["mes", "categoria"], as_index=False)
              .agg(unidades=("unidades", "sum"), ventas=("base", "sum")))

def ventas_presupuesto_por_categoria(mes_hasta: int) -> pd.DataFrame:
    """Unidades y ventas presupuestadas por mes y categoría, desde los drivers del presupuesto."""
    ppto = pd.read_csv(RUTA_DATOS / "presupuesto_2026_drivers_ventas.csv")
    ppto = ppto[ppto.mes <= mes_hasta]
    return ppto[["mes", "categoria", "unidades", "ventas"]].copy()