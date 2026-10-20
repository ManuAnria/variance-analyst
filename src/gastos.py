"""
gastos.py — Desviaciones del resto de gastos de explotación.

Sin driver de unidades o plantilla, el análisis consiste en:
  1) desviación acumulada por cuenta y centro de coste,
  2) presupuesto flexible para los gastos variables (p. ej. transporte = % de ventas),
  3) clasificación del patrón mensual: puntual, recurrente o de calendario,
  4) filtro de materialidad.

Signo: positivo = favorable (gastamos menos de lo presupuestado).
"""
import pandas as pd

UMBRAL_ABSOLUTO = 5_000          # € — a partir de aquí siempre se comenta
UMBRAL_RELATIVO = 0.10           # 10 % sobre presupuesto...
MINIMO_RELATIVO = 1_000          # ...siempre que supere 1.000 € (evita comentar 20 € que son un 50 %)
FACTOR_PUNTUAL = 3               # un mes es "puntual" si su desviación triplica la de un mes típico

CUENTAS_VARIABLES = {"624": "ventas"}   # cuenta -> actividad que la mueve


# --------------------------------------------------------------------------- #
# 1. Desviación mensual
# --------------------------------------------------------------------------- #
def desviacion_mensual(real: pd.DataFrame, ppto: pd.DataFrame) -> pd.DataFrame:
    """Una fila por mes, cuenta y centro de coste con real, presupuesto y desviación."""
    claves = ["mes", "cuenta", "centro_coste"]
    df = real.merge(ppto, on=claves, suffixes=("_r", "_p"), how="outer").fillna(0)
    df["desviacion"] = df.importe_p - df.importe_r
    return df


# --------------------------------------------------------------------------- #
# 2. Presupuesto flexible (solo gastos variables)
# --------------------------------------------------------------------------- #
def flexibilizar(grupo: pd.DataFrame, actividad: pd.DataFrame) -> pd.DataFrame:
    """
    Separa la desviación de un gasto variable en:
      - efecto actividad: el gasto se movió porque la actividad (ventas) fue distinta
      - efecto tarifa:    el gasto por euro de actividad fue distinto (precio, contrato...)
    actividad: DataFrame [mes, actividad_r, actividad_p]
    """
    df = grupo.merge(actividad, on="mes")
    df["tasa_p"] = df.importe_p / df.actividad_p
    df["tasa_r"] = df.importe_r / df.actividad_r
    df["ppto_flexible"] = df.actividad_r * df.tasa_p

    df["efecto_actividad"] = df.importe_p - df.ppto_flexible
    df["efecto_tarifa"] = df.ppto_flexible - df.importe_r
    return df


# --------------------------------------------------------------------------- #
# 3. Patrón mensual
# --------------------------------------------------------------------------- #
def mes_de_cambio(d: pd.Series) -> int:
    """Mes a partir del cual la desviación media cambia más respecto a los meses anteriores."""
    meses = list(d.index)
    if len(meses) < 3:
        return int(meses[0])
    saltos = {k: abs(d.loc[k:].mean() - d.loc[:k - 1].mean()) for k in meses[1:]}
    return int(max(saltos, key=saltos.get))


def clasificar_patron(d: pd.Series) -> tuple[str, int | None]:
    """
    d: desviación mensual (índice = mes). Devuelve (patrón, mes clave).
      - calendario: meses grandes de signo opuesto que casi se anulan en el acumulado
      - puntual:    un mes destaca muy por encima del resto
      - recurrente: desviación sostenida desde un mes de inicio
    """
    total, bruto = d.sum(), d.abs().sum()
    if bruto < 1:
        return "sin_desviacion", None

    if abs(total) < 0.25 * bruto and d.max() > 0 and d.min() < 0:
        return "calendario", int(d.abs().idxmax())

    mes_max = int(d.abs().idxmax())
    mes_tipico = d.drop(mes_max).abs().median()
    if abs(d[mes_max]) >= FACTOR_PUNTUAL * mes_tipico and abs(d[mes_max]) >= UMBRAL_ABSOLUTO:
        return "puntual", mes_max

    return "recurrente", mes_de_cambio(d)


# --------------------------------------------------------------------------- #
# 4. Análisis completo
# --------------------------------------------------------------------------- #
def es_material(desviacion: float, ppto: float, patron: str, bruto: float) -> bool:
    if abs(desviacion) >= UMBRAL_ABSOLUTO:
        return True
    if ppto and abs(desviacion / ppto) >= UMBRAL_RELATIVO and abs(desviacion) >= MINIMO_RELATIVO:
        return True
    return patron == "calendario" and bruto >= 2 * UMBRAL_ABSOLUTO


def analizar_gastos(real: pd.DataFrame, ppto: pd.DataFrame, nombres: dict,
                    actividad: pd.DataFrame | None = None) -> pd.DataFrame:
    """Desviación acumulada por cuenta y centro, con presupuesto flexible, patrón y materialidad."""
    mensual = desviacion_mensual(real, ppto)

    filas = []
    for (cuenta, cc), grupo in mensual.groupby(["cuenta", "centro_coste"]):
        fila = dict(cuenta=cuenta, nombre=nombres.get(cuenta, ""), centro_coste=cc,
                    real=grupo.importe_r.sum(), ppto=grupo.importe_p.sum())
        fila["desviacion"] = fila["ppto"] - fila["real"]
        fila["desviacion_pct"] = fila["desviacion"] / fila["ppto"] if fila["ppto"] else None
        serie_patron = grupo.set_index("mes").desviacion

        if cuenta in CUENTAS_VARIABLES and actividad is not None:
            flex = flexibilizar(grupo, actividad)
            fila["efecto_actividad"] = flex.efecto_actividad.sum()
            fila["efecto_tarifa"] = flex.efecto_tarifa.sum()
            serie_patron = flex.set_index("mes").efecto_tarifa

        fila["patron"], fila["mes_clave"] = clasificar_patron(serie_patron)
        fila["material"] = es_material(fila["desviacion"], fila["ppto"], fila["patron"],
                                       grupo.desviacion.abs().sum())
        filas.append(fila)

    resultado = pd.DataFrame(filas)

    descuadre = resultado.desviacion.sum() - (ppto.importe.sum() - real.importe.sum())
    assert abs(descuadre) < 0.01, f"Las desviaciones de gastos no cuadran: {descuadre:.2f} €"

    return resultado.sort_values("desviacion", key=abs, ascending=False).reset_index(drop=True)