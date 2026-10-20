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

def coste_ventas_real_por_categoria(ejercicio: int, mes_hasta: int) -> pd.DataFrame:
    """Coste de ventas real (cuentas 600 + 610) por mes y categoría, desde el libro diario."""
    diario = pd.read_csv(RUTA_DATOS / "diario.csv", dtype={"cuenta": str}, parse_dates=["fecha"])

    df = diario[
        diario.cuenta.isin(["600", "610"])
        & (diario.tipo_asiento != "REGULARIZACION")
        & (diario.ejercicio == ejercicio)
        & (diario.fecha.dt.month <= mes_hasta)
    ].copy()
    df["mes"] = df.fecha.dt.month
    df["coste_ventas"] = df.debe - df.haber

    return df.groupby(["mes", "categoria"], as_index=False).coste_ventas.sum()


def coste_ventas_presupuesto_por_categoria(mes_hasta: int) -> pd.DataFrame:
    """Coste de ventas presupuestado por mes y categoría, desde los drivers del presupuesto."""
    ppto = pd.read_csv(RUTA_DATOS / "presupuesto_2026_drivers_ventas.csv")
    ppto = ppto[ppto.mes <= mes_hasta]
    return ppto[["mes", "categoria", "coste_ventas"]].copy()

def personal_real_por_centro(ejercicio: int, mes_hasta: int) -> pd.DataFrame:
    """FTE-mes (plantilla) y coste de personal real (640 + 642) por centro de coste."""
    plantilla = pd.read_csv(RUTA_DATOS / "plantilla_real.csv")
    plantilla = plantilla[(plantilla.ejercicio == ejercicio) & (plantilla.mes <= mes_hasta)]
    fte = plantilla.groupby("centro_coste", as_index=False).fte.sum().rename(columns={"fte": "fte_meses"})

    diario = pd.read_csv(RUTA_DATOS / "diario.csv", dtype={"cuenta": str}, parse_dates=["fecha"])
    gasto = diario[
        diario.cuenta.isin(["640", "642"])
        & (diario.tipo_asiento != "REGULARIZACION")
        & (diario.ejercicio == ejercicio)
        & (diario.fecha.dt.month <= mes_hasta)
    ].copy()
    gasto["coste"] = gasto.debe - gasto.haber
    coste = gasto.groupby("centro_coste", as_index=False).coste.sum()

    return fte.merge(coste, on="centro_coste")


def personal_presupuesto_por_centro(mes_hasta: int) -> pd.DataFrame:
    """FTE-mes y coste de personal presupuestado (640 + 642) por centro de coste."""
    plantilla = pd.read_csv(RUTA_DATOS / "presupuesto_2026_plantilla.csv")
    plantilla = plantilla[plantilla.mes <= mes_hasta]
    fte = plantilla.groupby("centro_coste", as_index=False).fte.sum().rename(columns={"fte": "fte_meses"})

    ppto = pd.read_csv(RUTA_DATOS / "presupuesto_2026.csv", dtype={"cuenta": str})
    ppto = ppto[ppto.cuenta.isin(["640", "642"]) & (ppto.mes <= mes_hasta)]
    coste = ppto.groupby("centro_coste", as_index=False).importe.sum().rename(columns={"importe": "coste"})

    return fte.merge(coste, on="centro_coste")

CUENTAS_EXCLUIDAS_GASTOS = ["600", "610", "640", "642", "630"]   # ya analizadas aparte, o impuesto


def gastos_real_por_mes(ejercicio: int, mes_hasta: int) -> pd.DataFrame:
    """Resto de gastos reales (grupo 6) por mes, cuenta y centro de coste, desde el libro diario."""
    diario = pd.read_csv(RUTA_DATOS / "diario.csv", dtype={"cuenta": str}, parse_dates=["fecha"])
    df = diario[
        diario.cuenta.str.startswith("6")
        & ~diario.cuenta.isin(CUENTAS_EXCLUIDAS_GASTOS)
        & (diario.tipo_asiento != "REGULARIZACION")
        & (diario.ejercicio == ejercicio)
        & (diario.fecha.dt.month <= mes_hasta)
    ].copy()
    df["mes"] = df.fecha.dt.month
    df["importe"] = df.debe - df.haber
    return df.groupby(["mes", "cuenta", "centro_coste"], as_index=False).importe.sum()


def gastos_presupuesto_por_mes(mes_hasta: int) -> pd.DataFrame:
    """Resto de gastos presupuestados por mes, cuenta y centro de coste."""
    ppto = pd.read_csv(RUTA_DATOS / "presupuesto_2026.csv", dtype={"cuenta": str})
    ppto = ppto[
        ppto.cuenta.str.startswith("6")
        & ~ppto.cuenta.isin(CUENTAS_EXCLUIDAS_GASTOS)
        & (ppto.mes <= mes_hasta)
    ]
    return ppto.groupby(["mes", "cuenta", "centro_coste"], as_index=False).importe.sum()


def nombres_cuentas() -> dict:
    """Diccionario {cuenta: nombre} del plan de cuentas."""
    plan = pd.read_csv(RUTA_DATOS / "plan_cuentas.csv", dtype={"cuenta": str})
    return dict(zip(plan.cuenta, plan.nombre))


def ventas_mensuales(ejercicio: int, mes_hasta: int) -> pd.DataFrame:
    """Ventas reales y presupuestadas por mes: la 'actividad' que mueve los gastos variables."""
    r = ventas_reales_por_categoria(ejercicio, mes_hasta).groupby("mes", as_index=False).ventas.sum()
    p = ventas_presupuesto_por_categoria(mes_hasta).groupby("mes", as_index=False).ventas.sum()
    return r.merge(p, on="mes", suffixes=("_r", "_p")).rename(
        columns={"ventas_r": "actividad_r", "ventas_p": "actividad_p"})

def resultado_contable(ejercicio: int, mes_hasta: int) -> float:
    """Resultado antes de impuestos según el libro diario (ingresos - gastos, sin IS ni regularización).
    Es el control independiente: el motor tiene que explicar exactamente esta cifra."""
    diario = pd.read_csv(RUTA_DATOS / "diario.csv", dtype={"cuenta": str}, parse_dates=["fecha"])
    df = diario[
        diario.cuenta.str[0].isin(["6", "7"])
        & (diario.cuenta != "630")
        & (diario.tipo_asiento != "REGULARIZACION")
        & (diario.ejercicio == ejercicio)
        & (diario.fecha.dt.month <= mes_hasta)
    ]
    return float((df.haber - df.debe).sum())