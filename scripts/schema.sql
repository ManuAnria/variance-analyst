-- =============================================================================
-- Grafilia Distribución S.L. (empresa ficticia) — esquema PostgreSQL / Supabase
-- Carga: \copy <tabla> FROM 'datos/<tabla>.csv' WITH (FORMAT csv, HEADER true)
-- (ground_truth/ NO se carga en la base que verá el LLM: es la clave de evaluación)
-- =============================================================================

-- ---------- Maestros ----------
CREATE TABLE plan_cuentas (
    cuenta        text PRIMARY KEY,
    nombre        text NOT NULL,
    grupo         text NOT NULL,
    naturaleza    text NOT NULL CHECK (naturaleza IN ('A','P','PN','G','I')),
    epigrafe_pyg  text,
    orden_pyg     int
);
CREATE TABLE centros_coste (centro_coste text PRIMARY KEY, nombre text NOT NULL);
CREATE TABLE categorias   (categoria text PRIMARY KEY, nombre text NOT NULL, tipo_iva numeric NOT NULL);

CREATE TABLE clientes (
    cliente_id text PRIMARY KEY, nombre text, tipo text, pais char(2),
    nif text, nif_iva text, descuento numeric, dias_pago int
);
CREATE TABLE proveedores (
    proveedor_id text PRIMARY KEY, nombre text, pais char(2), nif text,
    tipo text, regimen_iva text, actividad text, cuenta text, dias_pago int, categoria text
);

-- ---------- Libros registro de IVA ----------
CREATE TABLE facturas_emitidas (
    factura_id text PRIMARY KEY, fecha date, cliente_id text REFERENCES clientes,
    nif text, nif_iva text, pais char(2), tipo_operacion text,
    base_imponible numeric(14,2), cuota_iva numeric(14,2), total numeric(14,2),
    vencimiento date, fecha_cobro date
);
CREATE TABLE facturas_emitidas_lineas (
    factura_id text REFERENCES facturas_emitidas, linea int, categoria text REFERENCES categorias,
    unidades int, precio_unitario numeric(12,3), base numeric(14,2), tipo_iva numeric, cuota numeric(14,2),
    PRIMARY KEY (factura_id, linea)
);
CREATE TABLE facturas_recibidas (
    factura_id text PRIMARY KEY, num_factura_proveedor text, fecha_factura date, fecha_registro date,
    proveedor_id text REFERENCES proveedores, nif text, pais char(2), tipo_operacion text,
    base_imponible numeric(14,2), cuota_soportada numeric(14,2), cuota_deducible numeric(14,2),
    retencion_pct numeric, retencion numeric(14,2), total_factura numeric(14,2),
    ref_importacion text, fecha_pago date, usuario text
);
CREATE TABLE facturas_recibidas_lineas (
    factura_id text REFERENCES facturas_recibidas, linea int, cuenta text, centro_coste text,
    categoria text, descripcion text, unidades int, coste_unitario numeric(12,4),
    base numeric(14,2), tipo_iva numeric, cuota numeric(14,2),
    PRIMARY KEY (factura_id, linea)
);

-- ---------- Libro diario ----------
CREATE TABLE diario (
    asiento_id            int,
    ejercicio             int,
    num_asiento           int,
    fecha                 date,
    fecha_contabilizacion date,
    tipo_asiento          text,
    documento             text,
    concepto              text,
    linea                 int,
    cuenta                text REFERENCES plan_cuentas,
    tercero_id            text,     -- cliente_id / proveedor_id (subcuenta auxiliar)
    centro_coste          text,
    categoria             text,
    debe                  numeric(14,2) DEFAULT 0,
    haber                 numeric(14,2) DEFAULT 0,
    usuario               text,
    PRIMARY KEY (asiento_id, linea)
);
CREATE INDEX ix_diario_cuenta_fecha ON diario (cuenta, fecha);

-- ---------- Declaraciones presentadas ----------
CREATE TABLE modelo_303_presentado (
    ejercicio int, periodo text,
    base_21 numeric, cuota_21 numeric, base_10 numeric, cuota_10 numeric, base_4 numeric, cuota_4 numeric,
    base_adq_intracom numeric, cuota_adq_intracom numeric, base_isp numeric, cuota_isp numeric,
    total_devengado numeric, cuota_deducible_interiores numeric, cuota_deducible_importaciones numeric,
    cuota_deducible_intracom_isp numeric, total_deducir numeric, entregas_intracom_exentas numeric,
    resultado numeric, compensacion_periodos_anteriores numeric, resultado_liquidacion numeric,
    fecha_presentacion date,
    PRIMARY KEY (ejercicio, periodo)
);
CREATE TABLE modelo_349_presentado (
    ejercicio int, periodo text, clave char(1), tercero_id text, nombre text,
    nif_iva text, pais char(2), base_imponible numeric
);

-- ---------- Presupuesto y drivers ----------
CREATE TABLE presupuesto_2026 (
    ejercicio int, mes int, cuenta text REFERENCES plan_cuentas, centro_coste text, categoria text,
    importe numeric(14,2)   -- positivo tanto para ingresos como para gastos
);
CREATE TABLE presupuesto_2026_drivers_ventas (
    ejercicio int, mes int, categoria text, unidades int, precio_medio numeric, coste_unitario numeric,
    ventas numeric, coste_ventas numeric
);
CREATE TABLE presupuesto_2026_plantilla (
    ejercicio int, mes int, centro_coste text, fte numeric, coste_medio_anual numeric
);
CREATE TABLE plantilla_real (
    ejercicio int, mes int, centro_coste text, fte numeric,
    salario_bruto numeric, ss_empresa numeric, coste_total numeric
);

-- =============================================================================
-- VISTAS
-- =============================================================================

-- Libro mayor con saldo acumulado por cuenta (y tercero)
CREATE VIEW v_mayor AS
SELECT d.cuenta, p.nombre AS cuenta_nombre, d.tercero_id, d.fecha, d.asiento_id, d.num_asiento,
       d.documento, d.concepto, d.debe, d.haber,
       SUM(d.debe - d.haber) OVER (PARTITION BY d.cuenta, d.tercero_id
                                   ORDER BY d.fecha, d.asiento_id, d.linea) AS saldo_acumulado
FROM diario d JOIN plan_cuentas p USING (cuenta);

-- Balance de sumas y saldos mensual (acumulado desde la apertura)
CREATE VIEW v_sumas_saldos AS
WITH mov AS (
    SELECT cuenta, date_trunc('month', fecha)::date AS mes,
           SUM(debe) AS debe, SUM(haber) AS haber
    FROM diario GROUP BY 1, 2
)
SELECT m.cuenta, p.nombre, m.mes, m.debe AS debe_mes, m.haber AS haber_mes,
       SUM(m.debe)  OVER w AS sumas_debe,
       SUM(m.haber) OVER w AS sumas_haber,
       SUM(m.debe - m.haber) OVER w AS saldo
FROM mov m JOIN plan_cuentas p USING (cuenta)
WINDOW w AS (PARTITION BY m.cuenta ORDER BY m.mes);

-- PyG mensual real (excluye regularización). importe > 0 = ingreso o gasto según naturaleza
CREATE VIEW v_pyg_real AS
SELECT d.ejercicio, EXTRACT(month FROM d.fecha)::int AS mes, d.cuenta, p.nombre AS cuenta_nombre,
       p.epigrafe_pyg, p.orden_pyg, p.naturaleza, d.centro_coste, d.categoria,
       SUM(CASE WHEN p.naturaleza = 'I' THEN d.haber - d.debe ELSE d.debe - d.haber END) AS importe
FROM diario d JOIN plan_cuentas p USING (cuenta)
WHERE p.naturaleza IN ('I','G') AND d.tipo_asiento <> 'REGULARIZACION'
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9;

-- Real vs presupuesto 2026, misma convención de signo.
-- Nota: el presupuesto de coste de ventas está en la 600; compárese a nivel de epígrafe (600+610).
CREATE VIEW v_real_vs_ppto_2026 AS
WITH r AS (
    SELECT mes, cuenta, centro_coste, categoria, SUM(importe) AS real
    FROM v_pyg_real WHERE ejercicio = 2026 AND cuenta <> '630' GROUP BY 1, 2, 3, 4
), b AS (
    SELECT mes, cuenta, centro_coste, categoria, SUM(importe) AS ppto
    FROM presupuesto_2026 GROUP BY 1, 2, 3, 4
)
SELECT COALESCE(r.mes, b.mes) AS mes, COALESCE(r.cuenta, b.cuenta) AS cuenta, p.nombre AS cuenta_nombre,
       p.epigrafe_pyg, p.naturaleza,
       COALESCE(r.centro_coste, b.centro_coste) AS centro_coste,
       COALESCE(r.categoria, b.categoria) AS categoria,
       COALESCE(r.real, 0) AS real, COALESCE(b.ppto, 0) AS ppto,
       CASE WHEN p.naturaleza = 'I' THEN COALESCE(r.real, 0) - COALESCE(b.ppto, 0)
            ELSE COALESCE(b.ppto, 0) - COALESCE(r.real, 0) END AS desviacion_favorable
FROM r FULL JOIN b
  ON r.mes = b.mes AND r.cuenta = b.cuenta
 AND r.centro_coste IS NOT DISTINCT FROM b.centro_coste
 AND r.categoria IS NOT DISTINCT FROM b.categoria
JOIN plan_cuentas p ON p.cuenta = COALESCE(r.cuenta, b.cuenta)
WHERE COALESCE(r.mes, b.mes) <= 9;   -- datos reales hasta septiembre

-- Drivers reales de ventas (unidades, precio y coste medio por categoría y mes)
CREATE VIEW v_drivers_ventas_real AS
SELECT EXTRACT(year FROM f.fecha)::int AS ejercicio, EXTRACT(month FROM f.fecha)::int AS mes,
       l.categoria, SUM(l.unidades) AS unidades, SUM(l.base) AS ventas,
       SUM(l.base) / NULLIF(SUM(l.unidades), 0) AS precio_medio
FROM facturas_emitidas f JOIN facturas_emitidas_lineas l USING (factura_id)
GROUP BY 1, 2, 3;
