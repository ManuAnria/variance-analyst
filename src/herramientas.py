"""
herramientas.py — Consultas que el modelo puede pedir para investigar una desviación (drill-down).

Cada herramienta es una función de Python normal que devuelve un diccionario pequeño
(el modelo tiene una memoria de trabajo limitada: nada de tablas de 500 filas).
HERRAMIENTAS describe cada función para el modelo: nombre, para qué sirve y qué parámetros acepta.

El modelo NO accede a los datos: pide una consulta, el código la ejecuta y le devuelve el resultado.
"""
import pandas as pd

from carga import RUTA_DATOS

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
CATEGORIAS = {"PAP": "Papel y cuadernos", "ESC": "Material escolar", "OFI": "Material de oficina",
              "TEC": "Tecnología educativa", "LIB": "Libros"}
EJERCICIO = 2026
UMBRAL_ANOMALIA_PCT = 20      # un mes con el coste unitario un 20 % por encima del presupuesto es anómalo


def _euros(x) -> int:
    return int(round(float(x)))


# --------------------------------------------------------------------------- #
# 1. Ventas por cliente frente al año anterior
# --------------------------------------------------------------------------- #
def ventas_por_cliente(mes_desde: int, mes_hasta: int, n: int = 5) -> dict:
    """Clientes con mayor variación de ventas frente a los mismos meses del año anterior."""
    fact = pd.read_csv(RUTA_DATOS / "facturas_emitidas.csv", parse_dates=["fecha"])
    clientes = pd.read_csv(RUTA_DATOS / "clientes.csv")[["cliente_id", "nombre", "tipo"]]

    fact = fact[fact.fecha.dt.month.between(mes_desde, mes_hasta)]
    fact["anio"] = fact.fecha.dt.year
    tabla = (fact.pivot_table(index="cliente_id", columns="anio", values="base_imponible", aggfunc="sum")
                 .reindex(columns=[EJERCICIO - 1, EJERCICIO]).fillna(0))
    tabla.columns = ["ventas_anio_anterior", "ventas_anio_actual"]
    tabla["variacion"] = tabla.ventas_anio_actual - tabla.ventas_anio_anterior

    # Último mes con compras en el año actual (detecta clientes que han dejado de comprar)
    ultimo = fact[fact.anio == EJERCICIO].groupby("cliente_id").fecha.max().dt.month
    tabla = tabla.join(ultimo.rename("ultimo_mes_con_compras")).reset_index().merge(clientes, on="cliente_id")
    tabla = tabla.reindex(tabla.variacion.abs().sort_values(ascending=False).index).head(n)

    def situacion(ultimo) -> str:
        """Lectura ya interpretada: el modelo no tiene que deducirla del último mes de compra."""
        if pd.isna(ultimo):
            return f"sin compras en todo el periodo consultado"
        if int(ultimo) < mes_hasta:
            return f"sin compras desde {MESES[int(ultimo) + 1]} (última compra en {MESES[int(ultimo)]})"
        return "compra con normalidad"

    return {
        "consulta": f"Ventas por cliente, {MESES[mes_desde]}-{MESES[mes_hasta]}: {EJERCICIO} frente a {EJERCICIO - 1}",
        "nota": "El presupuesto asumía que todos los clientes de 2025 seguían comprando (+6 %).",
        "clientes": [
            {"cliente": r.nombre, "tipo": r.tipo,
             "ventas_anio_anterior": _euros(r.ventas_anio_anterior),
             "ventas_anio_actual": _euros(r.ventas_anio_actual),
             "variacion": _euros(r.variacion),
             "situacion": situacion(r.ultimo_mes_con_compras)}
            for r in tabla.itertuples()],
    }


# --------------------------------------------------------------------------- #
# 2. Coste unitario mes a mes de una categoría
# --------------------------------------------------------------------------- #
def coste_unitario_mensual(categoria: str, mes_hasta: int = 9) -> dict:
    """Coste de ventas por unidad, real frente a presupuesto, mes a mes."""
    import carga
    unidades = carga.ventas_reales_por_categoria(EJERCICIO, mes_hasta)
    coste = carga.coste_ventas_real_por_categoria(EJERCICIO, mes_hasta)
    ppto = pd.read_csv(RUTA_DATOS / "presupuesto_2026_drivers_ventas.csv")

    df = unidades.merge(coste, on=["mes", "categoria"])
    df = df[df.categoria == categoria].merge(ppto[ppto.categoria == categoria][["mes", "coste_unitario"]], on="mes")
    df["coste_unitario_real"] = df.coste_ventas / df.unidades

    df["diferencia_pct"] = (df.coste_unitario_real / df.coste_unitario - 1) * 100
    anomalos = df[df.diferencia_pct > UMBRAL_ANOMALIA_PCT]

    resultado = {
        "consulta": f"Coste unitario de {CATEGORIAS.get(categoria, categoria)}, enero-{MESES[mes_hasta]} {EJERCICIO}",
        "meses": [{"mes": MESES[int(r.mes)], "coste_unitario_real": round(r.coste_unitario_real, 2),
                   "coste_unitario_presupuesto": round(r.coste_unitario, 2),
                   "diferencia_pct": round(r.diferencia_pct, 1)}
                  for r in df.itertuples()],
    }
    # Pista para el agente: si hay meses anómalos, cuál es el siguiente paso de la investigación
    if len(anomalos):
        mes = int(anomalos.mes.iloc[0])
        resultado["meses_anomalos"] = [MESES[int(m)] for m in anomalos.mes]
        resultado["siguiente_paso"] = (f"El coste de {MESES[mes]} es anómalo. Antes de concluir, llama a "
                                       f"facturas_compra(categoria='{categoria}', mes={mes}) para revisar sus facturas.")
    return resultado


# --------------------------------------------------------------------------- #
# 3. Facturas de compra contabilizadas en un mes
# --------------------------------------------------------------------------- #
def facturas_compra(categoria: str, mes: int, n: int = 5) -> dict:
    """Mayores facturas de compra de una categoría contabilizadas en un mes, con su fecha de factura."""
    cab = pd.read_csv(RUTA_DATOS / "facturas_recibidas.csv", parse_dates=["fecha_factura", "fecha_registro"])
    lin = pd.read_csv(RUTA_DATOS / "facturas_recibidas_lineas.csv")
    prov = pd.read_csv(RUTA_DATOS / "proveedores.csv")[["proveedor_id", "nombre"]]

    df = lin[lin.categoria == categoria].merge(cab, on="factura_id").merge(prov, on="proveedor_id")
    df = df[(df.fecha_registro.dt.year == EJERCICIO) & (df.fecha_registro.dt.month == mes)]
    df = df.sort_values("base", ascending=False).head(n)

    # Lectura interpretada: facturas de un ejercicio anterior contabilizadas en este (posible error de corte)
    fuera_de_periodo = df[df.fecha_factura.dt.year < EJERCICIO]
    alerta = ([f"La factura {r.factura_id} tiene fecha {r.fecha_factura.strftime('%d/%m/%Y')} (ejercicio "
               f"{r.fecha_factura.year}) pero se contabilizó el {r.fecha_registro.strftime('%d/%m/%Y')}: "
               f"posible error de corte de operaciones." for r in fuera_de_periodo.itertuples()])

    return {
        "alertas": alerta or ["Ninguna factura de otro ejercicio."],
        "consulta": f"Facturas de compra de {CATEGORIAS.get(categoria, categoria)} contabilizadas en {MESES[mes]} {EJERCICIO}",
        "facturas": [{"factura": r.factura_id, "proveedor": r.nombre,
                      "fecha_factura": r.fecha_factura.strftime("%d/%m/%Y"),
                      "fecha_contabilizacion": r.fecha_registro.strftime("%d/%m/%Y"),
                      "base": _euros(r.base)}
                     for r in df.itertuples()],
    }


# --------------------------------------------------------------------------- #
# Descripción para el modelo y ejecución
# --------------------------------------------------------------------------- #
_CATEGORIA = {"type": "string", "enum": list(CATEGORIAS),
              "description": "Código de categoría: " + ", ".join(f"{k} = {v}" for k, v in CATEGORIAS.items())}
_MES = {"type": "integer", "minimum": 1, "maximum": 9, "description": "Mes (1 = enero ... 9 = septiembre)"}

HERRAMIENTAS = [
    {"name": "ventas_por_cliente",
     "description": "Clientes con mayor variación de ventas entre dos meses del año actual frente a los mismos "
                    "meses del año anterior. Indica también el último mes en que cada cliente compró. "
                    "Úsala para investigar desviaciones de volumen de ventas.",
     "input_schema": {"type": "object", "properties": {"mes_desde": _MES, "mes_hasta": _MES},
                      "required": ["mes_desde", "mes_hasta"]}},
    {"name": "coste_unitario_mensual",
     "description": "Coste unitario de compra real y presupuestado, mes a mes, de una categoría. "
                    "Úsala para ver desde cuándo sube un coste o si un mes es anómalo.",
     "input_schema": {"type": "object", "properties": {"categoria": _CATEGORIA}, "required": ["categoria"]}},
    {"name": "facturas_compra",
     "description": "Mayores facturas de compra de una categoría contabilizadas en un mes, con su fecha de "
                    "factura y su fecha de contabilización. Úsala para revisar un mes con un coste anómalo.",
     "input_schema": {"type": "object", "properties": {"categoria": _CATEGORIA, "mes": _MES},
                      "required": ["categoria", "mes"]}},
]

_FUNCIONES = {"ventas_por_cliente": ventas_por_cliente,
              "coste_unitario_mensual": coste_unitario_mensual,
              "facturas_compra": facturas_compra}


def ejecutar(nombre: str, argumentos: dict) -> dict:
    """Ejecuta la herramienta pedida por el modelo. Los errores se devuelven como texto, no rompen el programa."""
    if nombre not in _FUNCIONES:
        return {"error": f"La herramienta '{nombre}' no existe. Disponibles: {list(_FUNCIONES)}"}
    try:
        return _FUNCIONES[nombre](**argumentos)
    except Exception as e:                      # argumentos mal formados, categoría inexistente...
        return {"error": f"{type(e).__name__}: {e}"}
