"""
experimento.py — Repite la generación del informe varias veces y resume los resultados.

Una sola ejecución no basta: con la misma configuración, el modelo no escribe dos veces lo mismo.
Este script ejecuta N informes, evalúa cada uno contra las causas reales y guarda todo en
salidas/experimentos.csv (una fila por ejecución), que es de donde sale la tabla del README.

Uso:  python experimento.py 3          -> 3 ejecuciones con el modelo configurado en el .env
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from evaluacion import evaluar
from informe import generar_informe

RUTA_CSV = Path(__file__).resolve().parent.parent / "salidas" / "experimentos.csv"


def ejecutar_experimento(n: int) -> pd.DataFrame:
    filas = []
    for i in range(1, n + 1):
        print(f"\n{'=' * 30} Ejecución {i} de {n} {'=' * 30}")
        m = generar_informe(2026, 9)
        causas = evaluar(m["ruta"].read_text(encoding="utf-8"))
        identificadas = [codigo for codigo, (_, frase) in causas.items() if frase]
        filas.append({
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "modelo": m["modelo"], "prompt": m["prompt"],
            "informe": m["ruta"].name, "errores_narrativa": m["errores_narrativa"],
            "errores_hallazgos": m["errores_hallazgos"], "mencionados": round(m["mencionados"], 2),
            "cuantificados": round(m["cuantificados"], 2), "causas_identificadas": len(identificadas),
            "causas_falladas": " ".join(c for c in causas if c not in identificadas),
            "consultas_agente": m["consultas_agente"],
            "minutos": round((m["segundos_narrativa"] + m["segundos_agente"]) / 60, 1),
        })
        # Guardar tras cada ejecución: si se interrumpe, no se pierde lo ya hecho
        pd.DataFrame([filas[-1]]).to_csv(RUTA_CSV, mode="a", header=not RUTA_CSV.exists(), index=False)

    return pd.DataFrame(filas)


def resumen(df: pd.DataFrame) -> pd.DataFrame:
    """Media, mínimo y máximo por modelo y versión del prompt (mediana para el tiempo: un apagón de pantalla
    o un ordenador suspendido dispara una ejecución y distorsiona la media)."""
    metricas = ["errores_narrativa", "mencionados", "cuantificados", "causas_identificadas"]
    tabla = df.groupby(["modelo", "prompt"])[metricas].agg(["mean", "min", "max"]).round(2)
    tabla[("minutos", "mediana")] = df.groupby(["modelo", "prompt"]).minutos.median()
    tabla[("ejecuciones", "n")] = df.groupby(["modelo", "prompt"]).size()
    return tabla


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ejecutar_experimento(n)
    print("\n=== RESUMEN DE TODAS LAS EJECUCIONES (salidas/experimentos.csv) ===")
    print(resumen(pd.read_csv(RUTA_CSV)).to_string())
