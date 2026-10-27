#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_contabilidad.py
=======================
Contabilidad sintética de una distribuidora mayorista española (EMPRESA FICTICIA).

  - PGC 2007, partida doble, IVA español (21 % / 4 %, intracomunitarias, ISP, importación)
  - Ejercicio 2025 completo + 2026 hasta el cierre de septiembre
  - Presupuesto 2026 construido por drivers (unidades, precio, coste, plantilla)
  - Desviaciones con causa conocida y errores de IVA sembrados (ground truth aparte)

Uso:   python generar_contabilidad.py          -> genera ./datos/
Reproducible: misma SEED = mismos datos.
"""
import calendar
import json
import os
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

SEED = 2026
rng = np.random.default_rng(SEED)
OUT = "datos"
GT = os.path.join(OUT, "ground_truth")
START, END = date(2025, 1, 1), date(2026, 9, 30)
MONTHS = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 10)]

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def r2(x):
    return float(np.round(float(x) + 1e-9, 2))

def last_day(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])

def bday_fwd(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def bday_back(d):
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def last_bday(y, m):
    return bday_back(last_day(y, m))

def rand_bday(y, m, lo=1, hi=None):
    hi = hi or calendar.monthrange(y, m)[1]
    days = [date(y, m, d) for d in range(lo, hi + 1) if date(y, m, d).weekday() < 5]
    return days[int(rng.integers(len(days)))]

def add_months(y, m, k):
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1

def qtr(d):
    return (d.month - 1) // 3 + 1

# --- identificadores fiscales con dígito de control válido -------------------
_used_ids = set()

def cif(letter="B"):
    while True:
        prov = rng.choice(["08", "17", "25", "43", "46", "03", "12", "50", "30", "28"])
        d = [int(prov[0]), int(prov[1])] + [int(x) for x in rng.integers(0, 10, 5)]
        a = d[1] + d[3] + d[5]
        b = sum(sum(divmod(2 * d[i], 10)) for i in (0, 2, 4, 6))
        ctrl = (10 - (a + b) % 10) % 10
        s = f"{letter}{''.join(map(str, d))}{ctrl}"
        if s not in _used_ids:
            _used_ids.add(s)
            return s

def vat_pt():
    d = [int(rng.integers(5, 6))] + [int(x) for x in rng.integers(0, 10, 7)]
    s = sum(d[i] * (9 - i) for i in range(8))
    c = 11 - s % 11
    c = 0 if c >= 10 else c
    return "PT" + "".join(map(str, d)) + str(c)

def vat_fr():
    siren = int(rng.integers(300000000, 999999999))
    key = (12 + 3 * (siren % 97)) % 97
    return f"FR{key:02d}{siren}"

def vat_de():
    return "DE" + "".join(map(str, rng.integers(0, 10, 9)))

def vat_it():
    return "IT" + "".join(map(str, rng.integers(0, 10, 11)))

# ----------------------------------------------------------------------------
# Maestros
# ----------------------------------------------------------------------------
EMPRESA = dict(nombre="Grafilia Distribución S.L.", nif=cif("B"),
               actividad="Comercio al por mayor de papelería, material escolar, "
                         "oficina, tecnología educativa y libros",
               domicilio="Polígono industrial (ficticio), Barcelona",
               nota="Empresa y terceros ficticios generados por generar_contabilidad.py")

# cuenta, nombre, naturaleza (A activo, P pasivo, PN patrimonio, G gasto, I ingreso), epígrafe PyG, orden PyG
PLAN = [
    ("100", "Capital social", "PN", None, None),
    ("112", "Reserva legal", "PN", None, None),
    ("113", "Reservas voluntarias", "PN", None, None),
    ("129", "Resultado del ejercicio", "PN", None, None),
    ("170", "Deudas a largo plazo con entidades de crédito", "P", None, None),
    ("213", "Maquinaria", "A", None, None),
    ("216", "Mobiliario", "A", None, None),
    ("217", "Equipos para procesos de información", "A", None, None),
    ("218", "Elementos de transporte", "A", None, None),
    ("2813", "Amortización acumulada de maquinaria", "A", None, None),
    ("2816", "Amortización acumulada de mobiliario", "A", None, None),
    ("2817", "Amortización acumulada de equipos informáticos", "A", None, None),
    ("2818", "Amortización acumulada de elementos de transporte", "A", None, None),
    ("300", "Mercaderías", "A", None, None),
    ("400", "Proveedores", "P", None, None),
    ("410", "Acreedores por prestaciones de servicios", "P", None, None),
    ("430", "Clientes", "A", None, None),
    ("465", "Remuneraciones pendientes de pago", "P", None, None),
    ("4700", "Hacienda Pública, deudora por IVA", "A", None, None),
    ("472", "Hacienda Pública, IVA soportado", "A", None, None),
    ("4750", "Hacienda Pública, acreedora por IVA", "P", None, None),
    ("4751", "Hacienda Pública, acreedora por retenciones practicadas", "P", None, None),
    ("4752", "Hacienda Pública, acreedora por impuesto sobre sociedades", "P", None, None),
    ("476", "Organismos de la Seguridad Social, acreedores", "P", None, None),
    ("477", "Hacienda Pública, IVA repercutido", "P", None, None),
    ("480", "Gastos anticipados", "A", None, None),
    ("520", "Deudas a corto plazo con entidades de crédito", "P", None, None),
    ("523", "Proveedores de inmovilizado a corto plazo", "P", None, None),
    ("5201", "Deudas a corto plazo por crédito dispuesto", "P", None, None),
    ("572", "Bancos e instituciones de crédito c/c vista, euros", "A", None, None),
    ("600", "Compras de mercaderías", "G", "4. Aprovisionamientos", 4),
    ("610", "Variación de existencias de mercaderías", "G", "4. Aprovisionamientos", 4),
    ("621", "Arrendamientos y cánones", "G", "7. Otros gastos de explotación", 7),
    ("622", "Reparaciones y conservación", "G", "7. Otros gastos de explotación", 7),
    ("623", "Servicios de profesionales independientes", "G", "7. Otros gastos de explotación", 7),
    ("624", "Transportes", "G", "7. Otros gastos de explotación", 7),
    ("625", "Primas de seguros", "G", "7. Otros gastos de explotación", 7),
    ("626", "Servicios bancarios y similares", "G", "7. Otros gastos de explotación", 7),
    ("627", "Publicidad, propaganda y relaciones públicas", "G", "7. Otros gastos de explotación", 7),
    ("628", "Suministros", "G", "7. Otros gastos de explotación", 7),
    ("629", "Otros servicios", "G", "7. Otros gastos de explotación", 7),
    ("631", "Otros tributos", "G", "7. Otros gastos de explotación", 7),
    ("640", "Sueldos y salarios", "G", "6. Gastos de personal", 6),
    ("642", "Seguridad Social a cargo de la empresa", "G", "6. Gastos de personal", 6),
    ("662", "Intereses de deudas", "G", "13. Gastos financieros", 13),
    ("681", "Amortización del inmovilizado material", "G", "8. Amortización del inmovilizado", 8),
    ("630", "Impuesto sobre beneficios", "G", "17. Impuestos sobre beneficios", 17),
    ("700", "Ventas de mercaderías", "I", "1. Importe neto de la cifra de negocios", 1),
]
PLAN_NAMES = {p[0]: p[1] for p in PLAN}

CENTROS = [("COM", "Comercial"), ("LOG", "Logística y almacén"),
           ("ADM", "Administración y finanzas"), ("DIR", "Dirección")]

CATS = ["PAP", "ESC", "OFI", "TEC", "LIB"]
CAT_INFO = {
    "PAP": dict(nombre="Papel y cuadernos", iva=21, precio=4.50, coste=3.20),
    "ESC": dict(nombre="Material escolar", iva=21, precio=2.80, coste=1.70),
    "OFI": dict(nombre="Material de oficina y archivo", iva=21, precio=6.00, coste=4.05),
    "TEC": dict(nombre="Tecnología educativa y consumibles", iva=21, precio=46.0, coste=38.5),
    "LIB": dict(nombre="Libros y material didáctico", iva=4, precio=18.0, coste=13.5),
}
SEAS_RAW = {
    "PAP": [1.10, 0.90, 0.90, 0.85, 0.85, 0.80, 1.00, 1.50, 1.60, 0.90, 0.85, 0.75],
    "ESC": [0.80, 0.60, 0.60, 0.60, 0.60, 0.70, 1.30, 2.20, 2.30, 0.70, 0.60, 0.50],
    "OFI": [1.15, 1.05, 1.05, 1.00, 1.00, 0.95, 0.80, 0.60, 1.15, 1.10, 1.10, 1.05],
    "TEC": [0.90, 0.80, 0.80, 0.80, 0.80, 0.80, 0.90, 1.30, 1.50, 1.00, 1.30, 1.10],
    "LIB": [0.40, 0.30, 0.30, 0.30, 0.40, 0.90, 2.00, 2.80, 2.60, 0.60, 0.40, 0.30],
}
SEAS = {c: np.array(v) / np.sum(v) * 12 for c, v in SEAS_RAW.items()}

TIPOS = {
    "Cadena de papelerías": dict(pref=[.32, .33, .17, .10, .08], dias=90),
    "Papelería": dict(pref=[.30, .36, .14, .08, .12], dias=60),
    "Librería": dict(pref=[.14, .20, .05, .04, .57], dias=60),
    "Centro educativo": dict(pref=[.28, .30, .04, .28, .10], dias=30),
    "Empresa (oficinas)": dict(pref=[.42, .02, .38, .18, .00], dias=60),
    "Distribuidor UE": dict(pref=[.36, .36, .20, .08, .00], dias=30),
}
APELLIDOS = ["Ferrer", "Soler", "Vidal", "Puig", "Serra", "Navarro", "Molina", "Ortega",
             "Castell", "Roca", "Pons", "Bosch", "Prat", "Garriga", "Riera", "Marín", "Gil",
             "Lozano", "Cano", "Ibáñez", "Sanz", "Romero", "Font", "Valls", "Llobet", "Comas"]
CIUDADES = ["Sabadell", "Terrassa", "Mataró", "Reus", "Lleida", "Girona", "Manresa",
            "Granollers", "Igualada", "Vic", "Castelló", "Gandia", "Valencia", "Alzira",
            "Huesca", "Zaragoza", "Tarragona", "Figueres", "Vilanova", "Elx", "Murcia", "Alacant"]

clients = []

def add_client(cid, nombre, tipo, pais, nif, nif_iva, rev, desc, dias=None, moroso=False):
    pref = np.array(TIPOS[tipo]["pref"])
    base_units = {}
    for i, c in enumerate(CATS):
        base_units[c] = rev * pref[i] / (CAT_INFO[c]["precio"] * (1 - desc))
    clients.append(dict(cliente_id=cid, nombre=nombre, tipo=tipo, pais=pais, nif=nif,
                        nif_iva=nif_iva, ventas_objetivo_2025=rev, descuento=desc,
                        dias_pago=dias or TIPOS[tipo]["dias"], moroso=moroso,
                        base_units=base_units, g26=float(rng.normal(1.0, 0.04))))

add_client("C001", "Papelerías Mediterráneo S.A.", "Cadena de papelerías", "ES", cif("A"), None, 1_100_000, 0.12)
add_client("C002", "Grupo Escolar Levante S.L.", "Cadena de papelerías", "ES", cif(), None, 650_000, 0.10)

tipos_resto = (["Papelería"] * 16 + ["Librería"] * 6 + ["Centro educativo"] * 9 + ["Empresa (oficinas)"] * 7)
w = np.sort(rng.lognormal(0, 0.8, len(tipos_resto)))[::-1]
w = w / w.sum() * 6_900_000
w = np.minimum(w, 480_000); w = w / w.sum() * 6_900_000
rng.shuffle(tipos_resto)
used_names = set()
moroso_ids = set(rng.choice(range(10, 38), 2, replace=False).tolist())
for k, tipo in enumerate(tipos_resto):
    while True:
        ap, ci = rng.choice(APELLIDOS), rng.choice(CIUDADES)
        nombre = {"Papelería": f"Papelería {ap} S.L.", "Librería": f"Librería {ap} {ci} S.L.",
                  "Centro educativo": f"Colegio {ci} {ap} S.Coop.",
                  "Empresa (oficinas)": f"{ap} Consultores {ci} S.L."}[tipo]
        if nombre not in used_names:
            used_names.add(nombre); break
    rev = float(w[k])
    desc = float(np.clip(rev / 480_000 * 0.08 + rng.normal(0, 0.01), 0, 0.09))
    add_client(f"C{k + 3:03d}", nombre, tipo, "ES", cif("F" if tipo == "Centro educativo" else "B"),
               None, rev, round(desc, 3), moroso=(k in moroso_ids))

add_client("C041", "Papelaria Douro Lda", "Distribuidor UE", "PT", None, vat_pt(), 120_000, 0.05)
add_client("C042", "Escritório Lisboa Lda", "Distribuidor UE", "PT", None, vat_pt(), 90_000, 0.04)
add_client("C043", "Papelaria Minho Lda", "Distribuidor UE", "PT", None, vat_pt(), 60_000, 0.03)
add_client("C044", "Bureau Midi SARL", "Distribuidor UE", "FR", None, vat_fr(), 50_000, 0.03)
# ERROR SEMBRADO E2: cliente UE sin NIF-IVA (no puede facturarse como entrega intracomunitaria exenta)
add_client("C045", "Fournitures Lyonnaises SARL", "Distribuidor UE", "FR", None, "", 30_000, 0.02)
CL = {c["cliente_id"]: c for c in clients}

SUPPLIERS = [
    # id, nombre, pais, nif, tipo, regimen, actividad, cuenta, dias, categoria, cuota_cat
    ("P01", "Papierwerke Rhein GmbH", "DE", vat_de(), "MERCADERIAS", "ADQ_INTRACOM", "Fabricante de papel y cuadernos", "400", 30, "PAP", 0.75),
    ("P02", "Papeles Industriales Segre S.L.", "ES", cif(), "MERCADERIAS", "INTERIOR", "Fabricante de papel", "400", 60, "PAP", 0.25),
    ("P03", "Scrittura Lombarda S.r.l.", "IT", vat_it(), "MERCADERIAS", "ADQ_INTRACOM", "Fabricante de material de escritura", "400", 30, "ESC", 0.50),
    ("P04", "Ningbo Bright Stationery Co. Ltd", "CN", "CN-9133" + "".join(map(str, rng.integers(0, 10, 12))), "MERCADERIAS", "IMPORTACION", "Fabricante de material escolar", "400", 15, "ESC", 0.30),
    ("P05", "Manualidades Ebro S.L.", "ES", cif(), "MERCADERIAS", "INTERIOR", "Material de manualidades", "400", 60, "ESC", 0.20),
    ("P06", "Ofiarchivo Levante S.L.", "ES", cif(), "MERCADERIAS", "INTERIOR", "Material de oficina y archivo", "400", 60, "OFI", 1.00),
    ("P07", "TecnoMayor Iberia S.L.", "ES", cif(), "MERCADERIAS", "ISP_INTERIOR", "Mayorista de tablets, portátiles y smartphones", "400", 45, "TEC", 0.70),
    ("P08", "Consumibles Atlántico S.L.", "ES", cif(), "MERCADERIAS", "INTERIOR", "Tóner, cartuchos y calculadoras", "400", 60, "TEC", 0.30),
    ("P09", "Editorial Didáctica Meseta S.A.", "ES", cif("A"), "MERCADERIAS", "INTERIOR", "Editorial de libros de texto", "400", 60, "LIB", 1.00),
    ("A01", "Inmobiliaria Polígono Sur S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Arrendamiento de nave industrial", "410", 0, None, None),
    ("A02", "Transportes Rápidos Delta S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Transporte y paquetería", "410", 30, None, None),
    ("A03", "Aseguradora Norte Seguros S.A.", "ES", cif("A"), "ACREEDOR", "EXENTO", "Seguros (exento art. 20.Uno.16º LIVA)", "410", 0, None, None),
    ("A04", "Energía Mediterránea S.A.", "ES", cif("A"), "ACREEDOR", "INTERIOR", "Suministro eléctrico", "410", 0, None, None),
    ("A05", "Conecta Telecom S.A.", "ES", cif("A"), "ACREEDOR", "INTERIOR", "Telecomunicaciones", "410", 0, None, None),
    ("A06", "Laura Pérez Ruiz (asesora fiscal y laboral)", "ES", "%08dX" % int(rng.integers(10_000_000, 99_999_999)), "ACREEDOR", "INTERIOR", "Asesoría fiscal y laboral (profesional, retención 15 %)", "410", 15, None, None),
    ("A07", "Mantenimientos Industriales Garraf S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Mantenimiento de carretillas y almacén", "410", 30, None, None),
    ("A08", "Impulso Creativo S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Agencia de publicidad", "410", 30, None, None),
    ("A09", "Restaurante Casa Ferran S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Restauración (comidas con clientes)", "410", 0, None, None),
    ("A10", "Aduanas y Tránsitos Port S.L.", "ES", cif(), "ACREEDOR", "INTERIOR", "Transitario y representante aduanero", "410", 15, None, None),
    ("A11", "Sistemas Informáticos Garbí S.L.", "ES", cif(), "INMOVILIZADO", "INTERIOR", "Venta de equipos informáticos", "523", 30, None, None),
]
SUP = {s[0]: dict(zip(["proveedor_id", "nombre", "pais", "nif", "tipo", "regimen_iva", "actividad",
                       "cuenta", "dias_pago", "categoria", "cuota_categoria"], s)) for s in SUPPLIERS}
SUP_BY_CAT = defaultdict(list)
for s in SUP.values():
    if s["categoria"]:
        SUP_BY_CAT[s["categoria"]].append(s)

# ----------------------------------------------------------------------------
# Motor de asientos
# ----------------------------------------------------------------------------
entries = []
_seq = [0]

def add(fecha, tipo, doc, concepto, lines, usuario="sistema", fecha_contab=None, prio=5):
    lines = [l for l in lines if r2(l.get("debe", 0)) != 0 or r2(l.get("haber", 0)) != 0]
    td = r2(sum(r2(l.get("debe", 0)) for l in lines))
    th = r2(sum(r2(l.get("haber", 0)) for l in lines))
    assert abs(td - th) < 0.005, f"Asiento descuadrado {doc} {concepto}: {td} vs {th}"
    _seq[0] += 1
    entries.append(dict(fecha=fecha, tipo=tipo, doc=doc, concepto=concepto, lines=lines,
                        usuario=usuario, fecha_contab=fecha_contab or fecha, prio=prio, seq=_seq[0]))

def D(cuenta, imp, tercero=None, cc=None, cat=None):
    return dict(cuenta=cuenta, debe=r2(imp), haber=0.0, tercero=tercero, cc=cc, cat=cat)

def H(cuenta, imp, tercero=None, cc=None, cat=None):
    return dict(cuenta=cuenta, debe=0.0, haber=r2(imp), tercero=tercero, cc=cc, cat=cat)

# ----------------------------------------------------------------------------
# Factores de precio / coste (drivers reales)
# ----------------------------------------------------------------------------
def price_factor(c, y, m):
    if y == 2025:
        return 1.0
    if c == "ESC" and m >= 7:          # S4: subida de tarifa escolar mayor que la presupuestada
        return 1.05
    return 1.025

def cost_factor(c, y, m):
    if y == 2025:
        return 1.0
    if c == "PAP" and m >= 4:          # S2: proveedor de papel sube precios
        return 1.09
    return 1.02

UNIT_COST = {(c, y, m): CAT_INFO[c]["coste"] * cost_factor(c, y, m) * (1 + rng.normal(0, 0.004))
             for c in CATS for (y, m) in MONTHS}

# ----------------------------------------------------------------------------
# VENTAS
# ----------------------------------------------------------------------------
sales = []
for (y, m) in MONTHS:
    for cl in clients:
        if cl["cliente_id"] == "C001" and (y, m) >= (2026, 6):   # S1: pérdida de cliente clave
            continue
        small = cl["ventas_objetivo_2025"] < 90_000
        if small and rng.random() < 0.08:
            continue
        units = {}
        for c in CATS:
            bu = cl["base_units"][c]
            if bu <= 0:
                continue
            u = bu / 12 * SEAS[c][m - 1]
            if y == 2026:
                u *= 1.06 * cl["g26"]
                if c == "TEC" and m >= 2:      # S3: plan de digitalización escolar -> más tablets
                    u *= 1.30
                if c == "PAP":
                    u *= 0.96
            u *= rng.lognormal(0, 0.12)
            u = int(round(u))
            if u > 0:
                units[c] = u
        if not units:
            continue
        n = int(np.clip(round(cl["ventas_objetivo_2025"] / 12 / 15_000 + rng.normal(0, 0.5)), 1, 8))
        dates = sorted(rand_bday(y, m) for _ in range(n))
        split = {c: rng.multinomial(u, rng.dirichlet(np.ones(n) * 2)) for c, u in units.items()}
        for k in range(n):
            lines = []
            for c in CATS:
                if c not in split or split[c][k] == 0:
                    continue
                uu = int(split[c][k])
                p = round(CAT_INFO[c]["precio"] * price_factor(c, y, m) * (1 - cl["descuento"])
                          * (1 + rng.normal(0, 0.01)), 3)
                base = r2(uu * p)
                tipo = 0 if cl["pais"] != "ES" else CAT_INFO[c]["iva"]
                lines.append(dict(categoria=c, unidades=uu, precio_unitario=p, base=base,
                                  tipo_iva=tipo, cuota=r2(base * tipo / 100)))
            if lines:
                sales.append(dict(fecha=dates[k], cliente_id=cl["cliente_id"], lineas=lines))

sales.sort(key=lambda s: (s["fecha"], s["cliente_id"]))
cnt = defaultdict(int)
for s in sales:
    y = s["fecha"].year
    cnt[y] += 1
    s["factura_id"] = f"FV{str(y)[2:]}-{cnt[y]:05d}"

# ERROR SEMBRADO E1: libros facturados al 21 % en lugar del 4 %
e1 = [s for s in sales if s["fecha"].year == 2026 and CL[s["cliente_id"]]["pais"] == "ES"
      and any(l["categoria"] == "LIB" for l in s["lineas"])]
e1 = [e1[i] for i in sorted(rng.choice(len(e1), 3, replace=False))]
GT_IVA = []
for s in e1:
    for l in s["lineas"]:
        if l["categoria"] == "LIB":
            l["tipo_iva"] = 21
            l["cuota"] = r2(l["base"] * 0.21)
    GT_IVA.append(dict(codigo="E1", documento=s["factura_id"], libro="emitidas",
                       descripcion="Línea de libros (LIB) facturada al 21 %; los libros tributan al 4 % (art. 91.Dos.1.2º LIVA)"))
for s in sales:
    if s["cliente_id"] == "C045":
        GT_IVA.append(dict(codigo="E2", documento=s["factura_id"], libro="emitidas",
                           descripcion="Entrega intracomunitaria exenta a cliente sin NIF-IVA válido: no cumple art. 25 LIVA; debió repercutirse IVA español"))

for s in sales:
    cl = CL[s["cliente_id"]]
    s["tipo_operacion"] = "INTERIOR" if cl["pais"] == "ES" else "ENTREGA_INTRACOM"
    s["base"] = r2(sum(l["base"] for l in s["lineas"]))
    s["cuota"] = r2(sum(l["cuota"] for l in s["lineas"]))
    s["total"] = r2(s["base"] + s["cuota"])
    s["vencimiento"] = s["fecha"] + timedelta(days=cl["dias_pago"])
    L = [D("430", s["total"], tercero=cl["cliente_id"])]
    for c in CATS:
        b = sum(l["base"] for l in s["lineas"] if l["categoria"] == c)
        if b:
            L.append(H("700", b, cc="COM", cat=c))
    if s["cuota"]:
        L.append(H("477", s["cuota"]))
    add(s["fecha"], "VENTA", s["factura_id"], f"Factura {s['factura_id']} {cl['nombre']}", L, "erp_ventas", prio=2)
    # cobro
    if cl["moroso"]:
        delay = int(rng.normal(40, 12))
    else:
        delay = int(rng.choice([0, 0, 0, 2, 3, 5, 8, 12, 20, 35], p=[.3, .15, .1, .1, .1, .08, .07, .05, .03, .02]))
    fc = bday_fwd(s["vencimiento"] + timedelta(days=max(delay, 0)))
    s["fecha_cobro"] = fc if fc <= END else None
    if s["fecha_cobro"]:
        add(fc, "COBRO", s["factura_id"], f"Cobro {s['factura_id']} {cl['nombre']}",
            [D("572", s["total"]), H("430", s["total"], tercero=cl["cliente_id"])], "tesoreria_auto", prio=6)

# ----------------------------------------------------------------------------
# COSTE DE VENTAS, EXISTENCIAS Y COMPRAS DE MERCADERÍAS
# ----------------------------------------------------------------------------
units_sold = defaultdict(float)
for s in sales:
    for l in s["lineas"]:
        units_sold[(l["categoria"], s["fecha"].year, s["fecha"].month)] += l["unidades"]

def expected_units(c, y, m):
    tot = 0.0
    for cl in clients:
        u = cl["base_units"][c] / 12 * SEAS[c][m - 1]
        tot += u * (1.06 if y >= 2026 else 1.0)
    return tot

COGS = {k: units_sold[k] * UNIT_COST[k] for k in UNIT_COST}
inv = {}
for c in CATS:
    inv[(c, 2024, 12)] = 1.4 * expected_units(c, 2025, 1) * CAT_INFO[c]["coste"]
purchases = {}
for (y, m) in MONTHS:
    ny, nm = add_months(y, m, 1)
    for c in CATS:
        py, pm = add_months(y, m, -1)
        beg = inv[(c, py, pm)]
        target = 1.4 * expected_units(c, ny, nm) * UNIT_COST[(c, y, m)]
        p = COGS[(c, y, m)] + target - beg
        p = max(p, 0.15 * COGS[(c, y, m)])
        purchases[(c, y, m)] = p
        inv[(c, y, m)] = beg + p - COGS[(c, y, m)]

recibidas = []
rcount = defaultdict(int)

def new_recibida(prov, fecha, lineas, tipo_op=None, deducible=True, ret_pct=0.0, num_prov=None,
                 usuario="conta_mgarcia", extra=None):
    s = SUP[prov]
    y = fecha.year
    rcount[y] += 1
    fid = f"FR{str(y)[2:]}-{rcount[y]:05d}"
    freg = fecha + timedelta(days=int(rng.integers(0, 4)))
    if freg > END or freg.month != fecha.month:   # cierre mensual: se contabiliza dentro de su mes
        freg = fecha
    f = dict(factura_id=fid, num_factura_proveedor=num_prov or f"{prov}-{y}{int(rng.integers(1000, 9999))}",
             fecha_factura=fecha, fecha_registro=freg, proveedor_id=prov,
             tipo_operacion=tipo_op or s["regimen_iva"], lineas=lineas, deducible=deducible,
             retencion_pct=ret_pct, usuario=usuario)
    if extra:
        f.update(extra)
    recibidas.append(f)
    return f

for (y, m) in MONTHS:
    for c in CATS:
        P = purchases[(c, y, m)]
        for s in SUP_BY_CAT[c]:
            amount = P * s["cuota_categoria"]
            n = int(rng.integers(1, 4))
            parts = rng.dirichlet(np.ones(n) * 3) * amount
            for part in parts:
                uc = UNIT_COST[(c, y, m)]
                uu = max(1, int(round(part / uc)))
                base = r2(uu * uc)
                tipo = CAT_INFO[c]["iva"]
                desc = {"PAP": "Papel y cuadernos", "ESC": "Material escolar", "OFI": "Material de oficina",
                        "TEC": "Tablets educativas" if s["proveedor_id"] == "P07" else "Tóner y consumibles",
                        "LIB": "Libros de texto"}[c]
                lin = [dict(cuenta="600", cc=None, cat=c, descripcion=desc, unidades=uu,
                            coste_unitario=round(uc, 4), base=base, tipo_iva=tipo, cuota=r2(base * tipo / 100))]
                fecha = rand_bday(y, m)
                f = new_recibida(s["proveedor_id"], fecha, lin, usuario="compras_lmartin")
                if s["regimen_iva"] == "IMPORTACION":
                    f["lineas"][0]["tipo_iva"] = 0
                    f["lineas"][0]["cuota"] = 0.0
                    fd = bday_fwd(fecha + timedelta(days=12))
                    if fd <= END:
                        hon = r2(rng.uniform(110, 160))
                        new_recibida("A10", fd, [dict(cuenta="623", cc="LOG", cat=None,
                                                      descripcion=f"Honorarios despacho aduanero ({f['factura_id']})",
                                                      unidades=None, coste_unitario=None, base=hon,
                                                      tipo_iva=21, cuota=r2(hon * 0.21))],
                                     tipo_op="DUA",
                                     extra=dict(base_importacion=base, cuota_importacion=r2(base * 0.21),
                                                ref_importacion=f["factura_id"]))

# ----------------------------------------------------------------------------
# GASTOS DE EXPLOTACIÓN (acreedores)
# ----------------------------------------------------------------------------
sales_base_month = defaultdict(float)
for s in sales:
    sales_base_month[(s["fecha"].year, s["fecha"].month)] += s["base"]

ELEC_SEAS = [1.2, 1.15, 1.0, 0.9, 0.85, 1.0, 1.15, 1.15, 0.95, 0.9, 1.0, 1.15]

def gl(cuenta, cc, desc, base, tipo=21):
    return dict(cuenta=cuenta, cc=cc, cat=None, descripcion=desc, unidades=None,
                coste_unitario=None, base=r2(base), tipo_iva=tipo, cuota=r2(r2(base) * tipo / 100))

for (y, m) in MONTHS:
    inf = 1.0 if y == 2025 else 1.03
    # alquiler nave (retención 19 %)
    new_recibida("A01", date(y, m, 1), [gl("621", "LOG", "Alquiler nave", 15_000 * inf)], ret_pct=19.0)
    # transporte: % sobre ventas; S6 nuevo contrato desde marzo 2026
    rate = 0.024 if (y, m) < (2026, 3) else 0.028
    new_recibida("A02", last_bday(y, m), [gl("624", "LOG", "Portes de distribución",
                                              sales_base_month[(y, m)] * rate * rng.normal(1, 0.03))])
    # electricidad
    eb = 2_800 * ELEC_SEAS[m - 1] * inf * rng.normal(1, 0.05)
    new_recibida("A04", rand_bday(y, m, 3, 10), [gl("628", "LOG", "Electricidad almacén", eb * 0.7),
                                                 gl("628", "ADM", "Electricidad oficinas", eb * 0.3)])
    # telecomunicaciones; E7: cuota mal tecleada en una factura
    f = new_recibida("A05", rand_bday(y, m, 1, 8), [gl("629", "ADM", "Telefonía e internet", 880 * inf)])
    if (y, m) == (2026, 2):
        f["lineas"][0]["cuota"] = r2(f["lineas"][0]["cuota"] + 10.0)
        GT_IVA.append(dict(codigo="E7", documento=f["factura_id"], libro="recibidas",
                           descripcion="Cuota de IVA no coincide con base x tipo (diferencia de 10,00 €, error de grabación)"))
    # asesoría (profesional, retención 15 %)
    new_recibida("A06", rand_bday(y, m, 1, 6), [gl("623", "ADM", "Asesoría fiscal y laboral", 2_200 * inf)], ret_pct=15.0)
    # reparaciones
    for _ in range(int(rng.poisson(1.0))):
        new_recibida("A07", rand_bday(y, m), [gl("622", "LOG", "Mantenimiento almacén", rng.uniform(250, 1_400))])
    if (y, m) == (2026, 2):  # S8: avería extraordinaria carretilla
        new_recibida("A07", date(2026, 2, 17), [gl("622", "LOG", "Reparación motor carretilla elevadora", 6_800)])
    # publicidad recurrente + campañas
    new_recibida("A08", rand_bday(y, m, 1, 10), [gl("627", "COM", "Marketing digital (fee mensual)", 3_500 * inf)])
    if (y, m) == (2025, 7):
        new_recibida("A08", date(2025, 7, 7), [gl("627", "COM", "Campaña vuelta al cole 2025", 15_000)])
    if (y, m) == (2026, 9):  # S7: campaña presupuestada en junio, ejecutada en septiembre
        new_recibida("A08", date(2026, 9, 8), [gl("627", "COM", "Campaña vuelta al cole 2026", 18_600)])
    # comidas con clientes (IVA NO deducible, art. 96.Uno.5º LIVA); E5 en dos facturas
    for k in range(int(rng.integers(1, 3))):
        f = new_recibida("A09", rand_bday(y, m), [gl("629", "COM", "Comida con cliente", rng.uniform(150, 450), 10)],
                         deducible=False)
        if (y, m) in [(2025, 10), (2026, 5)] and k == 0:
            f["deducible"] = True
            GT_IVA.append(dict(codigo="E5", documento=f["factura_id"], libro="recibidas",
                               descripcion="IVA de atenciones a clientes deducido; no es deducible (art. 96.Uno.5º LIVA)"))
    # seguro anual (exento) -> periodificación
    if m == 1:
        prima = 14_400 if y == 2025 else 15_120
        new_recibida("A03", date(y, 1, 10), [dict(cuenta="480", cc=None, cat=None, descripcion="Prima anual seguro multirriesgo y RC",
                                                  unidades=None, coste_unitario=None, base=prima, tipo_iva=0, cuota=0.0)],
                     tipo_op="EXENTA")

# inmovilizado: portátiles oficina (8.400 €, < 10.000 € -> sin ISP, IVA normal)
new_recibida("A11", date(2025, 9, 15), [gl("217", None, "6 portátiles para oficina", 8_400)])

# ERRORES SEMBRADOS en compras
p07 = [f for f in recibidas if f["proveedor_id"] == "P07"]
for f in [next(x for x in p07 if x["fecha_factura"] >= date(2025, 11, 1)),
          next(x for x in p07 if x["fecha_factura"] >= date(2026, 3, 1))]:
    f["tipo_operacion"] = "INTERIOR"   # E3: proveedor repercute IVA en lugar de aplicar ISP
    GT_IVA.append(dict(codigo="E3", documento=f["factura_id"], libro="recibidas",
                       descripcion="Compra de tablets a mayorista nacional con IVA repercutido; al ser la empresa revendedora procede inversión del sujeto pasivo (art. 84.Uno.2º.g LIVA)"))
e4 = next(f for f in recibidas if f["proveedor_id"] == "P03" and f["fecha_factura"] >= date(2026, 5, 1))
e4["sin_autorrepercusion"] = True
GT_IVA.append(dict(codigo="E4", documento=e4["factura_id"], libro="recibidas",
                   descripcion="Adquisición intracomunitaria sin autorrepercusión de IVA (falta 472/477) y omitida en el modelo 349"))
orig = next(f for f in recibidas if f["proveedor_id"] == "P06" and f["fecha_factura"] >= date(2025, 11, 1))
dup = json.loads(json.dumps(orig, default=str))
rcount[2025] += 1
dup.update(factura_id=f"FR25-{rcount[2025]:05d}", fecha_factura=orig["fecha_factura"],
           fecha_registro=orig["fecha_registro"] + timedelta(days=6), usuario="conta_temporal", duplicada=True,
           lineas=[dict(l) for l in orig["lineas"]])
recibidas.append(dup)
GT_IVA.append(dict(codigo="E6", documento=dup["factura_id"], libro="recibidas",
                   descripcion=f"Factura duplicada (mismo proveedor, número {orig['num_factura_proveedor']} e importe que {orig['factura_id']}); IVA deducido dos veces"))

# ERROR SEMBRADO S10 (corte de operaciones): factura de diciembre 2025 contabilizada en enero 2026
s10 = max((f for f in recibidas if f["proveedor_id"] == "P06" and f["fecha_factura"].year == 2025
           and f["fecha_factura"].month == 12 and not f.get("duplicada")), key=lambda f: f["fecha_factura"])
s10["fecha_registro"] = bday_fwd(date(2026, 1, 2))

# Contabilización de facturas recibidas + pagos
for f in recibidas:
    s = SUP[f["proveedor_id"]]
    op = f["tipo_operacion"]
    base = r2(sum(l["base"] for l in f["lineas"]))
    cuota = r2(sum(l["cuota"] for l in f["lineas"]))
    L = []
    if op in ("ADQ_INTRACOM", "ISP_INTERIOR", "IMPORTACION", "EXENTA"):
        repercutida_por_proveedor = 0.0
    else:
        repercutida_por_proveedor = cuota
    for l in f["lineas"]:
        imp = l["base"] + (l["cuota"] if (op == "INTERIOR" and not f["deducible"]) else 0)
        L.append(D(l["cuenta"], imp, cc=l["cc"], cat=l["cat"]))
    autorep = 0.0
    cuota_deducible = 0.0
    if op == "INTERIOR":
        cuota_deducible = cuota if f["deducible"] else 0.0
    elif op == "DUA":
        cuota_deducible = r2(cuota + f["cuota_importacion"])
        repercutida_por_proveedor = r2(cuota + f["cuota_importacion"])
    elif op in ("ADQ_INTRACOM", "ISP_INTERIOR"):
        autorep = 0.0 if f.get("sin_autorrepercusion") else cuota
        cuota_deducible = autorep
    if cuota_deducible:
        L.append(D("472", cuota_deducible))
    if autorep:
        L.append(H("477", autorep))
    ret = r2(base * f["retencion_pct"] / 100)
    if ret:
        L.append(H("4751", ret))
    total = r2(base + repercutida_por_proveedor + (f.get("base_importacion", 0) * 0) )
    a_pagar = r2(total - ret)
    L.append(H(s["cuenta"], a_pagar, tercero=f["proveedor_id"]))
    f.update(base=base, cuota_soportada=(cuota if op != "DUA" else r2(cuota + f["cuota_importacion"])) if not f.get("sin_autorrepercusion") else 0.0,
             cuota_deducible=cuota_deducible, retencion=ret, total=total, a_pagar=a_pagar)
    tipo = "COMPRA" if s["tipo"] == "MERCADERIAS" else ("INMOVILIZADO" if s["tipo"] == "INMOVILIZADO" else "GASTO")
    add(f["fecha_registro"], tipo, f["factura_id"], f"Fra. {f['num_factura_proveedor']} {s['nombre']}", L,
        f["usuario"], prio=3)
    # pago
    if f.get("duplicada"):
        f["fecha_pago"] = None
        continue
    if s["dias_pago"] == 0:
        fp = f["fecha_factura"]
    else:
        fp = f["fecha_factura"] + timedelta(days=s["dias_pago"] + int(rng.integers(0, 4)))
    fp = bday_fwd(max(fp, f["fecha_registro"]))
    f["fecha_pago"] = fp if fp <= END else None
    if f["fecha_pago"]:
        add(fp, "PAGO", f["factura_id"], f"Pago {f['num_factura_proveedor']} {s['nombre']}",
            [D(s["cuenta"], a_pagar, tercero=f["proveedor_id"]), H("572", a_pagar)], "tesoreria_auto", prio=7)

# variación de existencias (cierre mensual)
for (y, m) in MONTHS:
    py, pm = add_months(y, m, -1)
    L = []
    for c in CATS:
        delta = inv[(c, y, m)] - inv[(c, py, pm)]
        if delta > 0:
            L += [D("300", delta, cat=c), H("610", delta, cat=c)]
        elif delta < 0:
            L += [D("610", -delta, cat=c), H("300", -delta, cat=c)]
    add(last_day(y, m), "EXISTENCIAS", f"EX{y}{m:02d}", f"Variación de existencias {m:02d}/{y}", L,
        "control_jruiz", prio=8)

# periodificación seguro
for (y, m) in MONTHS:
    prima = 14_400 if y == 2025 else 15_120
    add(last_day(y, m), "PERIODIFICACION", f"PS{y}{m:02d}", f"Imputación seguro {m:02d}/{y}",
        [D("625", prima / 12, cc="ADM"), H("480", prima / 12)], "control_jruiz", prio=8)

# ----------------------------------------------------------------------------
# NÓMINAS
# ----------------------------------------------------------------------------
SAL = {"COM": 36_000, "LOG": 27_000, "ADM": 33_000, "DIR": 72_000}
IRPF = {"COM": 0.15, "LOG": 0.11, "ADM": 0.14, "DIR": 0.24}
SS_EMP, SS_TRAB = 0.32, 0.065

def fte_real(cc, y, m):
    base = {"COM": 8, "LOG": 12, "ADM": 6, "DIR": 2}[cc]
    if y == 2026 and cc == "COM" and m >= 7:   # S9: baja comercial no cubierta
        return 7
    if y == 2026 and cc == "LOG" and m >= 5:   # S5: incorporaciones adelantadas
        return 14
    return base

def fte_ppto(cc, m):
    base = {"COM": 8, "LOG": 12, "ADM": 6, "DIR": 2}[cc]
    if cc == "LOG" and m >= 9:
        return 14
    return base

plantilla = []
ss_month = {}
for (y, m) in MONTHS:
    L = []; tot_ss = tot_irpf = tot_neto = 0.0
    for cc, _ in CENTROS:
        fte = fte_real(cc, y, m)
        bruto = r2(fte * SAL[cc] * (1.03 if y == 2026 else 1) / 12 * rng.normal(1, 0.012))
        ss_e = r2(bruto * SS_EMP); ss_t = r2(bruto * SS_TRAB); irpf = r2(bruto * IRPF[cc])
        L += [D("640", bruto, cc=cc), D("642", ss_e, cc=cc)]
        tot_ss += ss_e + ss_t; tot_irpf += irpf; tot_neto += bruto - ss_t - irpf
        plantilla.append(dict(ejercicio=y, mes=m, centro_coste=cc, fte=fte, salario_bruto=bruto,
                              ss_empresa=ss_e, coste_total=r2(bruto + ss_e)))
    L += [H("476", tot_ss), H("4751", tot_irpf), H("465", tot_neto)]
    d = last_bday(y, m)
    add(d, "NOMINA", f"NOM{y}{m:02d}", f"Nóminas {m:02d}/{y}", L, "gestoria_nominas", prio=4)
    add(d, "PAGO", f"NOM{y}{m:02d}", f"Pago nóminas {m:02d}/{y}", [D("465", tot_neto), H("572", tot_neto)],
        "tesoreria_auto", prio=7)
    ss_month[(y, m)] = r2(tot_ss)

# ----------------------------------------------------------------------------
# AMORTIZACIÓN, PRÉSTAMO, COMISIONES, TRIBUTOS
# ----------------------------------------------------------------------------
AMORT = [("213", "2813", 80_000 * .12 / 12, "LOG"), ("216", "2816", 60_000 * .10 / 12, "ADM"),
         ("217", "2817", 45_000 * .25 / 12, "ADM"), ("218", "2818", 120_000 * .16 / 12, "LOG")]
for (y, m) in MONTHS:
    L = []
    for _, acc, q, cc in AMORT:
        L += [D("681", q, cc=cc), H(acc, q)]
    if (y, m) >= (2025, 10):
        L += [D("681", 8_400 * .25 / 12, cc="ADM"), H("2817", 8_400 * .25 / 12)]
    add(last_day(y, m), "AMORTIZACION", f"AM{y}{m:02d}", f"Amortización {m:02d}/{y}", L, "control_jruiz", prio=8)

loan = 500_000.0
for (y, m) in MONTHS:
    d = bday_fwd(date(y, m, 5))
    interest = r2(loan * 0.045 / 12)
    principal = r2(100_000 / 12) if m < 12 else r2(100_000 - 11 * r2(100_000 / 12))
    add(d, "FINANCIERO", f"PRE{y}{m:02d}", f"Cuota préstamo {m:02d}/{y}",
        [D("520", principal), D("662", interest, cc="ADM"), H("572", principal + interest)], "tesoreria_auto", prio=6)
    loan -= principal
    fee = r2(rng.uniform(300, 420))
    add(last_bday(y, m), "FINANCIERO", f"BAN{y}{m:02d}", f"Comisiones bancarias {m:02d}/{y}",
        [D("626", fee, cc="ADM"), H("572", fee)], "tesoreria_auto", prio=6)
# póliza de crédito estacional (campaña vuelta al cole): 5201
POLIZA = [(date(2025, 7, 15), 450_000, date(2025, 11, 17)), (date(2026, 7, 15), 400_000, date(2026, 11, 16))]
for (dd, imp, dr) in POLIZA:
    add(bday_fwd(dd), "FINANCIERO", f"POL{dd.year}", f"Disposición póliza de crédito campaña {dd.year}",
        [D("572", imp), H("5201", imp)], "tesoreria_auto", prio=1)
    if dr <= END:
        add(bday_fwd(dr), "FINANCIERO", f"POL{dd.year}", f"Reembolso póliza de crédito campaña {dd.year}",
            [D("5201", imp), H("572", imp)], "tesoreria_auto", prio=7)
    y, m = dd.year, dd.month
    while (y, m) <= (dr.year, dr.month) and last_day(y, m) <= END:
        it = r2(imp * 0.05 / 12)
        add(last_bday(y, m), "FINANCIERO", f"POLI{y}{m:02d}", f"Intereses póliza de crédito {m:02d}/{y}",
            [D("662", it, cc="ADM"), H("572", it)], "tesoreria_auto", prio=6)
        y, m = add_months(y, m, 1)
add(date(2025, 12, 31), "RECLASIFICACION", "RCL2025", "Reclasificación l/p a c/p préstamo",
    [D("170", 100_000), H("520", 100_000)], "control_jruiz", prio=8)
for y in (2025, 2026):
    add(date(y, 3, 16), "TRIBUTOS", f"IVTM{y}", f"Impuesto vehículos {y}", [D("631", 1_150, cc="LOG"), H("572", 1_150)],
        "conta_mgarcia")
add(date(2025, 10, 20), "TRIBUTOS", "IAE2025", "Impuesto Actividades Económicas 2025",
    [D("631", 4_800, cc="ADM"), H("572", 4_800)], "conta_mgarcia")

# ----------------------------------------------------------------------------
# APERTURA 2025
# ----------------------------------------------------------------------------
L = [D("213", 80_000), D("216", 60_000), D("217", 45_000), D("218", 120_000),
     H("2813", 28_000), H("2816", 30_000), H("2817", 25_000), H("2818", 50_000)]
for c in CATS:
    L.append(D("300", inv[(c, 2024, 12)], cat=c))
open_cli = 0.0
for cl in clients:
    sal = r2(cl["ventas_objetivo_2025"] / 12 * cl["dias_pago"] / 30 * (1.21 if cl["pais"] == "ES" else 1.0) * 0.9)
    open_cli += sal
    L.append(D("430", sal, tercero=cl["cliente_id"]))
    cl["saldo_apertura"] = sal
open_prov = 0.0
for s in SUP.values():
    if s["tipo"] != "MERCADERIAS":
        s["saldo_apertura"] = 0.0
        continue
    c = s["categoria"]
    mon = expected_units(c, 2025, 1) * CAT_INFO[c]["coste"] * s["cuota_categoria"]
    vat = 1.21 if s["regimen_iva"] in ("INTERIOR",) else 1.0
    sal = r2(mon * max(s["dias_pago"], 15) / 30 * vat)
    s["saldo_apertura"] = sal
    open_prov += sal
    L.append(H("400", sal, tercero=s["proveedor_id"]))
OPEN_IVA, OPEN_RET, OPEN_SS = 61_850.0, 38_420.0, ss_month[(2025, 1)]
L += [D("572", 520_000), H("4750", OPEN_IVA), H("4751", OPEN_RET), H("476", OPEN_SS),
      H("170", 400_000), H("520", 100_000), H("100", 300_000), H("112", 30_000), H("129", 180_000)]
plug = sum(l["debe"] for l in L) - sum(l["haber"] for l in L)
L.append(H("113", plug))
add(date(2025, 1, 1), "APERTURA", "AP2025", "Asiento de apertura 2025", L, "control_jruiz", prio=0)
for cl in clients:
    d = bday_fwd(date(2025, 1, 8) + timedelta(days=int(cl["dias_pago"] * 0.3)))
    add(d, "COBRO", "SALDO-INI", f"Cobro saldo inicial {cl['nombre']}",
        [D("572", cl["saldo_apertura"]), H("430", cl["saldo_apertura"], tercero=cl["cliente_id"])], "tesoreria_auto", prio=6)
for s in SUP.values():
    if s["saldo_apertura"]:
        d = bday_fwd(date(2025, 1, 5) + timedelta(days=int(max(s["dias_pago"], 15) * 0.6)))
        add(d, "PAGO", "SALDO-INI", f"Pago saldo inicial {s['nombre']}",
            [D("400", s["saldo_apertura"], tercero=s["proveedor_id"]), H("572", s["saldo_apertura"])], "tesoreria_auto", prio=7)
add(date(2025, 1, 30), "IMPUESTOS", "303-2024-4T", "Pago IVA 4T 2024", [D("4750", OPEN_IVA), H("572", OPEN_IVA)], "conta_mgarcia")
add(date(2025, 1, 20), "IMPUESTOS", "111-2024-4T", "Pago retenciones 4T 2024", [D("4751", OPEN_RET), H("572", OPEN_RET)], "conta_mgarcia")
add(last_bday(2025, 1), "SEG_SOCIAL", "SS2024-12", "Pago Seguridad Social 12/2024", [D("476", OPEN_SS), H("572", OPEN_SS)], "tesoreria_auto", prio=7)
for (y, m) in MONTHS:
    ny, nm = add_months(y, m, 1)
    d = last_bday(ny, nm)
    if d <= END:
        add(d, "SEG_SOCIAL", f"SS{y}-{m:02d}", f"Pago Seguridad Social {m:02d}/{y}",
            [D("476", ss_month[(y, m)]), H("476" if False else "572", ss_month[(y, m)])], "tesoreria_auto", prio=7)

# ----------------------------------------------------------------------------
# IVA (liquidación trimestral + modelo 303 presentado), retenciones (111/115), 349
# ----------------------------------------------------------------------------
QUARTERS = [(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2), (2026, 3)]

def in_q(d, y, q):
    return d.year == y and qtr(d) == q

def account_sum(cuenta, y, q, side):
    tot = 0.0
    for e in entries:
        if in_q(e["fecha"], y, q) and e["tipo"] not in ("LIQ_IVA",):
            for l in e["lines"]:
                if l["cuenta"] == cuenta:
                    tot += l[side] - l["haber" if side == "debe" else "debe"]
    return r2(tot)

e8 = max((s for s in sales if s["fecha"].year == 2026 and qtr(s["fecha"]) == 1 and s["cuota"] > 0),
         key=lambda s: s["fecha"])
GT_IVA.append(dict(codigo="E8", documento=e8["factura_id"], libro="modelo_303",
                   descripcion=f"Modelo 303 1T 2026 presentado sin la factura {e8['factura_id']} (cuota {e8['cuota']:.2f} €): "
                               "descuadre entre libro registro, contabilidad (saldo 4750) y declaración"))

m303 = []
comp = 0.0
for (y, q) in QUARTERS:
    rep = account_sum("477", y, q, "haber")
    sop = account_sum("472", y, q, "debe")
    res = r2(rep - sop)
    d = last_day(y, q * 3)
    L = [D("477", rep), H("472", sop)]
    if comp:
        L.append(H("4700", comp))
    net = r2(res - comp)
    if net >= 0:
        L.append(H("4750", net)); new_comp = 0.0
    else:
        L.append(D("4700", -net)); new_comp = -net
    add(d, "LIQ_IVA", f"303-{y}-{q}T", f"Liquidación IVA {q}T {y}", L, "conta_mgarcia", prio=9)
    # modelo 303 a partir de los libros registro
    em = [s for s in sales if in_q(s["fecha"], y, q)]
    rc = [f for f in recibidas if in_q(f["fecha_registro"], y, q)]
    row = dict(ejercicio=y, periodo=f"{q}T")
    for t in (21, 10, 4):
        row[f"base_{t}"] = r2(sum(l["base"] for s in em for l in s["lineas"] if l["tipo_iva"] == t))
        row[f"cuota_{t}"] = r2(sum(l["cuota"] for s in em for l in s["lineas"] if l["tipo_iva"] == t))
    row["base_adq_intracom"] = r2(sum(f["base"] for f in rc if f["tipo_operacion"] == "ADQ_INTRACOM"))
    row["cuota_adq_intracom"] = r2(sum(f["cuota_deducible"] for f in rc if f["tipo_operacion"] == "ADQ_INTRACOM"))
    row["base_isp"] = r2(sum(f["base"] for f in rc if f["tipo_operacion"] == "ISP_INTERIOR"))
    row["cuota_isp"] = r2(sum(f["cuota_deducible"] for f in rc if f["tipo_operacion"] == "ISP_INTERIOR"))
    if (y, q) == (2026, 1):
        for l in e8["lineas"]:
            row[f"base_{l['tipo_iva']}"] = r2(row[f"base_{l['tipo_iva']}"] - l["base"])
            row[f"cuota_{l['tipo_iva']}"] = r2(row[f"cuota_{l['tipo_iva']}"] - l["cuota"])
    row["total_devengado"] = r2(row["cuota_21"] + row["cuota_10"] + row["cuota_4"] + row["cuota_adq_intracom"] + row["cuota_isp"])
    row["cuota_deducible_interiores"] = r2(sum(f["cuota_deducible"] for f in rc if f["tipo_operacion"] in ("INTERIOR",)))
    row["cuota_deducible_importaciones"] = r2(sum(f["cuota_deducible"] for f in rc if f["tipo_operacion"] == "DUA"))
    row["cuota_deducible_intracom_isp"] = r2(row["cuota_adq_intracom"] + row["cuota_isp"])
    row["total_deducir"] = r2(row["cuota_deducible_interiores"] + row["cuota_deducible_importaciones"] + row["cuota_deducible_intracom_isp"])
    row["entregas_intracom_exentas"] = r2(sum(s["base"] for s in em if s["tipo_operacion"] == "ENTREGA_INTRACOM"))
    row["resultado"] = r2(row["total_devengado"] - row["total_deducir"])
    row["compensacion_periodos_anteriores"] = r2(comp)
    row["resultado_liquidacion"] = r2(row["resultado"] - comp)
    pay_date = date(y + 1, 1, 30) if q == 4 else bday_fwd(date(y, q * 3 + 1, 20))
    row["fecha_presentacion"] = pay_date
    if pay_date <= END:
        m303.append(row)
        if row["resultado_liquidacion"] > 0:
            add(pay_date, "IMPUESTOS", f"303-{y}-{q}T", f"Pago modelo 303 {q}T {y}",
                [D("4750", row["resultado_liquidacion"]), H("572", row["resultado_liquidacion"])], "conta_mgarcia")
    comp = new_comp
    # retenciones 111/115
    ret = r2(sum(l["haber"] for e in entries if in_q(e["fecha"], y, q) and e["tipo"] != "APERTURA"
                 for l in e["lines"] if l["cuenta"] == "4751"))
    rd = bday_fwd(date(y + (q == 4), (q * 3) % 12 + 1, 20))
    if rd <= END:
        add(rd, "IMPUESTOS", f"111-115-{y}-{q}T", f"Pago retenciones (111/115) {q}T {y}", [D("4751", ret), H("572", ret)],
            "conta_mgarcia")

m349 = []
for (y, q) in QUARTERS[:-1]:
    agg = defaultdict(float)
    for s in sales:
        if in_q(s["fecha"], y, q) and s["tipo_operacion"] == "ENTREGA_INTRACOM":
            agg[("E", s["cliente_id"])] += s["base"]
    for f in recibidas:
        if in_q(f["fecha_registro"], y, q) and f["tipo_operacion"] == "ADQ_INTRACOM" and not f.get("sin_autorrepercusion"):
            agg[("A", f["proveedor_id"])] += f["base"]
    for (clave, tid), b in sorted(agg.items()):
        t = CL.get(tid) or SUP.get(tid)
        m349.append(dict(ejercicio=y, periodo=f"{q}T", clave=clave, tercero_id=tid, nombre=t["nombre"],
                         nif_iva=t.get("nif_iva") if clave == "E" else t["nif"], pais=t["pais"], base_imponible=r2(b)))

# ----------------------------------------------------------------------------
# CIERRE 2025: aplicación resultado 2024, IS, regularización; aplicación resultado 2025
# ----------------------------------------------------------------------------
add(date(2025, 6, 30), "APLICACION_RESULTADO", "AR2024", "Aplicación del resultado 2024 (junta)",
    [D("129", 180_000), H("112", 18_000), H("113", 162_000)], "control_jruiz", prio=8)

def pyg_balance(y):
    bal = defaultdict(float)
    for e in entries:
        if e["fecha"].year == y and e["tipo"] != "REGULARIZACION":
            for l in e["lines"]:
                if l["cuenta"][0] in "67":
                    bal[l["cuenta"]] += l["debe"] - l["haber"]
    return bal

bal = pyg_balance(2025)
bai = -sum(bal.values())
is_q = r2(max(bai, 0) * 0.25)
if is_q:
    add(date(2025, 12, 31), "CIERRE_IS", "IS2025", "Impuesto sobre sociedades 2025", [D("630", is_q), H("4752", is_q)],
        "control_jruiz", prio=10)
    add(date(2026, 7, 24), "IMPUESTOS", "200-2025", "Pago Impuesto sobre Sociedades 2025 (modelo 200)",
        [D("4752", is_q), H("572", is_q)], "conta_mgarcia")
bal = pyg_balance(2025)
L = []
for acc, v in sorted(bal.items()):
    v = r2(v)
    if v > 0:
        L.append(H(acc, v))
    elif v < 0:
        L.append(D(acc, -v))
res25 = r2(-sum(bal.values()))
L.append(H("129", res25) if res25 >= 0 else D("129", -res25))
add(date(2025, 12, 31), "REGULARIZACION", "REG2025", "Regularización 2025", L, "control_jruiz", prio=11)
if res25 > 0:
    legal = r2(min(res25 * 0.10, 60_000 - 48_000))
    add(date(2026, 6, 30), "APLICACION_RESULTADO", "AR2025", "Aplicación del resultado 2025 (junta)",
        [D("129", res25), H("112", legal), H("113", res25 - legal)], "control_jruiz", prio=8)

# ----------------------------------------------------------------------------
# PRESUPUESTO 2026 (por drivers)
# ----------------------------------------------------------------------------
avg_price, avg_cost = {}, {}
for c in CATS:
    u = sum(l["unidades"] for s in sales if s["fecha"].year == 2025 for l in s["lineas"] if l["categoria"] == c)
    b = sum(l["base"] for s in sales if s["fecha"].year == 2025 for l in s["lineas"] if l["categoria"] == c)
    avg_price[c] = b / u
    avg_cost[c] = sum(COGS[(c, 2025, m)] for m in range(1, 13)) / sum(units_sold[(c, 2025, m)] for m in range(1, 13))

ppto, ppto_drv, ppto_pl = [], [], []

def P(m, cuenta, cc, cat, imp):
    ppto.append(dict(ejercicio=2026, mes=m, cuenta=cuenta, centro_coste=cc, categoria=cat, importe=r2(imp)))

ppto_sales = defaultdict(float)
for m in range(1, 13):
    for c in CATS:
        u = expected_units(c, 2026, m)
        pr = avg_price[c] * 1.025
        co = avg_cost[c] * 1.02
        ppto_drv.append(dict(ejercicio=2026, mes=m, categoria=c, unidades=round(u), precio_medio=round(pr, 4),
                             coste_unitario=round(co, 4), ventas=r2(u * pr), coste_ventas=r2(u * co)))
        P(m, "700", "COM", c, u * pr)
        P(m, "600", None, c, u * co)
        ppto_sales[m] += u * pr
    for cc, _ in CENTROS:
        fte = fte_ppto(cc, m)
        bruto = fte * SAL[cc] * 1.03 / 12
        ppto_pl.append(dict(ejercicio=2026, mes=m, centro_coste=cc, fte=fte, coste_medio_anual=SAL[cc] * 1.03))
        P(m, "640", cc, None, bruto)
        P(m, "642", cc, None, bruto * SS_EMP)
    P(m, "621", "LOG", None, 15_000 * 1.03)
    P(m, "624", "LOG", None, ppto_sales[m] * 0.024)
    P(m, "628", "LOG", None, 2_800 * ELEC_SEAS[m - 1] * 1.03 * 0.7)
    P(m, "628", "ADM", None, 2_800 * ELEC_SEAS[m - 1] * 1.03 * 0.3)
    P(m, "629", "ADM", None, 880 * 1.03)
    P(m, "629", "COM", None, 450)
    P(m, "623", "ADM", None, 2_200 * 1.03)
    P(m, "623", "LOG", None, 260)
    P(m, "622", "LOG", None, 850)
    P(m, "627", "COM", None, 3_500 * 1.03 + (18_000 if m == 6 else 0))
    P(m, "625", "ADM", None, 15_120 / 12)
    P(m, "626", "ADM", None, 360)
    if m == 3:
        P(m, "631", "LOG", None, 1_150)
    if m == 10:
        P(m, "631", "ADM", None, 4_900)
    for _, acc, q, cc in AMORT:
        P(m, "681", cc, None, q)
    P(m, "681", "ADM", None, 8_400 * .25 / 12)
    out = 400_000 - 100_000 / 12 * (m - 1)
    P(m, "662", "ADM", None, out * 0.045 / 12 + (400_000 * 0.05 / 12 if 7 <= m <= 11 else 0))

# ----------------------------------------------------------------------------
# EXPORTACIÓN
# ----------------------------------------------------------------------------
os.makedirs(GT, exist_ok=True)
entries.sort(key=lambda e: (e["fecha"], e["prio"], e["seq"]))
rows = []
num = defaultdict(int)
for gid, e in enumerate(entries, 1):
    num[e["fecha"].year] += 1
    for i, l in enumerate(e["lines"], 1):
        rows.append(dict(asiento_id=gid, ejercicio=e["fecha"].year, num_asiento=num[e["fecha"].year],
                         fecha=e["fecha"], fecha_contabilizacion=e["fecha_contab"], tipo_asiento=e["tipo"],
                         documento=e["doc"], concepto=e["concepto"], linea=i, cuenta=l["cuenta"],
                         tercero_id=l["tercero"], centro_coste=l["cc"], categoria=l["cat"],
                         debe=l["debe"], haber=l["haber"], usuario=e["usuario"]))
diario = pd.DataFrame(rows)
diario.to_csv(f"{OUT}/diario.csv", index=False)

pd.DataFrame([dict(cuenta=p[0], nombre=p[1], grupo=p[0][0], naturaleza=p[2], epigrafe_pyg=p[3], orden_pyg=p[4])
              for p in PLAN]).astype({"orden_pyg": "Int64"}).to_csv(f"{OUT}/plan_cuentas.csv", index=False)
pd.DataFrame(CENTROS, columns=["centro_coste", "nombre"]).to_csv(f"{OUT}/centros_coste.csv", index=False)
pd.DataFrame([dict(categoria=c, nombre=v["nombre"], tipo_iva=v["iva"]) for c, v in CAT_INFO.items()]
             ).to_csv(f"{OUT}/categorias.csv", index=False)
pd.DataFrame([{k: v for k, v in c.items() if k not in ("base_units", "g26", "moroso", "ventas_objetivo_2025", "saldo_apertura")}
              for c in clients]).to_csv(f"{OUT}/clientes.csv", index=False)
pd.DataFrame([{k: v for k, v in s.items() if k not in ("cuota_categoria", "saldo_apertura")} for s in SUP.values()]
             ).to_csv(f"{OUT}/proveedores.csv", index=False)

pd.DataFrame([dict(factura_id=s["factura_id"], fecha=s["fecha"], cliente_id=s["cliente_id"],
                   nif=CL[s["cliente_id"]]["nif"] or "", nif_iva=CL[s["cliente_id"]]["nif_iva"] or "",
                   pais=CL[s["cliente_id"]]["pais"], tipo_operacion=s["tipo_operacion"], base_imponible=s["base"],
                   cuota_iva=s["cuota"], total=s["total"], vencimiento=s["vencimiento"],
                   fecha_cobro=s["fecha_cobro"]) for s in sales]).to_csv(f"{OUT}/facturas_emitidas.csv", index=False)
pd.DataFrame([dict(factura_id=s["factura_id"], linea=i, **l) for s in sales for i, l in enumerate(s["lineas"], 1)]
             ).to_csv(f"{OUT}/facturas_emitidas_lineas.csv", index=False)
pd.DataFrame([dict(factura_id=f["factura_id"], num_factura_proveedor=f["num_factura_proveedor"],
                   fecha_factura=f["fecha_factura"], fecha_registro=f["fecha_registro"], proveedor_id=f["proveedor_id"],
                   nif=SUP[f["proveedor_id"]]["nif"], pais=SUP[f["proveedor_id"]]["pais"],
                   tipo_operacion=f["tipo_operacion"], base_imponible=r2(f["base"] + f.get("base_importacion", 0)),
                   cuota_soportada=f["cuota_soportada"], cuota_deducible=f["cuota_deducible"],
                   retencion_pct=f["retencion_pct"], retencion=f["retencion"], total_factura=f["total"],
                   ref_importacion=f.get("ref_importacion", ""), fecha_pago=f["fecha_pago"], usuario=f["usuario"])
              for f in recibidas]).to_csv(f"{OUT}/facturas_recibidas.csv", index=False)
pd.DataFrame([dict(factura_id=f["factura_id"], linea=i, cuenta=l["cuenta"], centro_coste=l["cc"], categoria=l["cat"],
                   descripcion=l["descripcion"], unidades=l["unidades"], coste_unitario=l["coste_unitario"],
                   base=l["base"], tipo_iva=l["tipo_iva"], cuota=l["cuota"])
              for f in recibidas for i, l in enumerate(f["lineas"], 1)]).astype({"unidades": "Int64"}).to_csv(f"{OUT}/facturas_recibidas_lineas.csv", index=False)
pd.DataFrame(m303).to_csv(f"{OUT}/modelo_303_presentado.csv", index=False)
pd.DataFrame(m349).to_csv(f"{OUT}/modelo_349_presentado.csv", index=False)
pd.DataFrame(plantilla).to_csv(f"{OUT}/plantilla_real.csv", index=False)
pd.DataFrame(ppto).to_csv(f"{OUT}/presupuesto_2026.csv", index=False)
pd.DataFrame(ppto_drv).to_csv(f"{OUT}/presupuesto_2026_drivers_ventas.csv", index=False)
pd.DataFrame(ppto_pl).to_csv(f"{OUT}/presupuesto_2026_plantilla.csv", index=False)
with open(f"{OUT}/empresa.json", "w", encoding="utf-8") as fh:
    json.dump(EMPRESA, fh, ensure_ascii=False, indent=2)

pd.DataFrame(GT_IVA).to_csv(f"{GT}/errores_iva_sembrados.csv", index=False)
GT_DESV = [
    dict(codigo="S1", desde="2026-06", tipo="Volumen (cliente)", cuentas="700", direccion="Desfavorable",
         descripcion="Pérdida del cliente clave C001 Papelerías Mediterráneo S.A. (~12 % de ventas 2025): deja de comprar desde junio 2026. Efecto secundario: sube el precio medio (era el cliente con más descuento)."),
    dict(codigo="S2", desde="2026-04", tipo="Precio de compra", cuentas="600/610 (PAP)", direccion="Desfavorable",
         descripcion="El proveedor de papel sube costes +9 % vs 2025 desde abril (presupuesto: +2 %). Margen PAP comprimido."),
    dict(codigo="S3", desde="2026-02", tipo="Mix / volumen", cuentas="700, 600 (TEC, PAP)", direccion="Ventas favorable / margen % desfavorable",
         descripcion="Plan de digitalización escolar: unidades TEC +30 % sobre presupuesto (categoría de margen bajo); PAP -4 %."),
    dict(codigo="S4", desde="2026-07", tipo="Precio de venta", cuentas="700 (ESC)", direccion="Favorable",
         descripcion="Subida de tarifa de material escolar del +5 % en campaña vuelta al cole (presupuesto: +2,5 %)."),
    dict(codigo="S5", desde="2026-05", tipo="Plantilla", cuentas="640/642 (LOG)", direccion="Desfavorable",
         descripcion="Dos incorporaciones en logística adelantadas a mayo (presupuesto: septiembre)."),
    dict(codigo="S6", desde="2026-03", tipo="Tarifa", cuentas="624 (LOG)", direccion="Desfavorable",
         descripcion="Nuevo contrato de transporte: del 2,4 % al 2,8 % sobre ventas."),
    dict(codigo="S7", desde="2026-06", tipo="Calendario (timing)", cuentas="627 (COM)", direccion="Favorable jun / desfavorable sep",
         descripcion="Campaña vuelta al cole presupuestada en junio (18.000 €) ejecutada en septiembre (18.600 €). Sin impacto relevante en el año."),
    dict(codigo="S8", desde="2026-02", tipo="No recurrente", cuentas="622 (LOG)", direccion="Desfavorable",
         descripcion="Reparación extraordinaria del motor de una carretilla: 6.800 € no presupuestados."),
    dict(codigo="S10", desde="2026-01", tipo="Error de corte (cut-off)", cuentas="600 (OFI)", direccion="Desfavorable 2026 / favorable 2025",
         descripcion="Factura de mercaderías de Ofiarchivo Levante del 31/12/2025 contabilizada el 02/01/2026 sin periodificar: el coste cae en enero 2026 en lugar de diciembre 2025. Coste unitario OFI de enero anormalmente alto."),
    dict(codigo="S9", desde="2026-07", tipo="Plantilla", cuentas="640/642 (COM)", direccion="Favorable",
         descripcion="Baja de un comercial no cubierta (8 -> 7 FTE)."),
]
pd.DataFrame(GT_DESV).to_csv(f"{GT}/desviaciones_sembradas.csv", index=False)

# ----------------------------------------------------------------------------
# VALIDACIONES
# ----------------------------------------------------------------------------
print("=" * 70)
chk = diario.groupby("asiento_id")[["debe", "haber"]].sum().round(2)
print(f"Asientos: {chk.shape[0]:,} | líneas: {len(diario):,} | descuadrados: {(abs(chk.debe - chk.haber) > 0.005).sum()}")
print(f"Total debe {diario.debe.sum():,.2f} | total haber {diario.haber.sum():,.2f}")
v700 = diario[diario.cuenta == "700"].eval("haber-debe").sum() - diario[(diario.cuenta == "700") & (diario.tipo_asiento == "REGULARIZACION")].eval("haber-debe").sum()
print(f"Ventas diario {v700:,.2f} vs libro emitidas {sum(s['base'] for s in sales):,.2f}")
bank = diario[diario.cuenta == "572"].sort_values(["fecha", "asiento_id"]).eval("debe-haber").cumsum()
print(f"Banco: mínimo {bank.min():,.2f} | final {bank.iloc[-1]:,.2f}")
print(f"Resultado 2025 (después de IS): {res25:,.2f} | IS: {is_q:,.2f}")
pl = diario[(diario.cuenta.str[0].isin(["6", "7"])) & (diario.tipo_asiento != "REGULARIZACION")].copy()
pl["mes"] = pd.to_datetime(pl.fecha).dt.month
pl["v"] = pl.haber - pl.debe
real26 = pl[(pl.ejercicio == 2026)].groupby("cuenta").v.sum()
pp = pd.DataFrame(ppto)
pp26 = pp[pp.mes <= 9].groupby("cuenta").importe.sum()
print("\nReal vs ppto ene-sep 2026 (PyG, + ingreso / - gasto):")
for acc in sorted(set(real26.index) | set(pp26.index)):
    r = real26.get(acc, 0.0)
    b = pp26.get(acc, 0.0) * (1 if acc.startswith("7") else -1)
    if acc in ("610",):
        b = 0.0
    print(f"  {acc} {PLAN_NAMES[acc][:38]:38s} real {r:14,.0f}  ppto {b:14,.0f}  desv {r - b:12,.0f}")
saldo4750 = diario[diario.cuenta == "4750"].eval("haber-debe").sum()
print(f"\nSaldo 4750 al cierre: {saldo4750:,.2f} (incluye 3T 2026 pendiente + descuadre E8)")
print("=" * 70)
