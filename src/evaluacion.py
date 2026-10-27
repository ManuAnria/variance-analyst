"""
evaluacion.py — ¿Encuentra el informe las causas REALES de la desviación?

El validador comprueba que el informe sea fiel a los datos. La evaluación comprueba algo distinto:
que identifique las causas que sabemos que existen, porque las sembramos al generar la contabilidad
(datos/../ground_truth/desviaciones_sembradas.csv, que el modelo nunca ve).

Cada causa se da por identificada si UNA misma frase del informe contiene una palabra de cada grupo
de su criterio. Son reglas simples y deterministas: cualquiera puede revisar por qué una causa
cuenta o no cuenta (a diferencia de usar otro LLM como juez).

Uso:  python evaluacion.py salidas/informe_xxx.md [otro_informe.md ...]
"""
import sys
from pathlib import Path

from validador import normalizar, partir_frases

# código: (descripción, [grupo1, grupo2, ...])  — cada grupo es una lista de alternativas, sin tildes
CRITERIOS = {
    "S1":  ("Pérdida del cliente clave Papelerías Mediterráneo desde junio",
            [["mediterraneo"], ["no ha", "dejo", "dejado", "sin compras", "ninguna compra", "ningun", "0 €",
                                "perdida", "perdido", "cero", "no realizo", "no compro"]]),
    "S2":  ("Subida del coste de compra del papel desde abril",
            [["coste", "costo"], ["papel"]]),
    "S3":  ("Mix hacia tecnología educativa (más tablets)",
            [["mix"], ["tecnolog"]]),
    "S4":  ("Subida de precio de venta del material escolar",
            [["precio"], ["escolar"]]),
    "S5":  ("Incorporaciones adelantadas en Logística",
            [["plantilla", "fte", "incorporac", "personas"], ["logistica"]]),
    "S6":  ("Nuevo contrato de transporte (tarifa más cara)",
            [["tarifa", "contrato", "por euro vendido"], ["transport"]]),
    "S7":  ("Campaña de publicidad desplazada de junio a septiembre (calendario)",
            [["publicidad", "campana"], ["junio", "calendario", "desfase", "desplaz", "traslad", "retras"]]),
    "S8":  ("Reparación extraordinaria en febrero",
            [["reparac"], ["febrero", "extraordinari", "puntual"]]),
    "S9":  ("Baja de un comercial no cubierta",
            [["plantilla", "fte", "baja", "personas"], ["comercial"]]),
    "S10": ("Error de corte: factura de diciembre 2025 contabilizada en enero 2026",
            [["factura", "contabiliz", "corte"], ["diciembre", "31/12", "2025", "periodific", "ejercicio anterior"]]),
}


def frase_que_identifica(frases: list[str], grupos: list[list[str]]) -> str | None:
    """Primera frase que contiene al menos una palabra de cada grupo."""
    for f in frases:
        fn = normalizar(f)
        if all(any(palabra in fn for palabra in grupo) for grupo in grupos):
            return f
    return None


def evaluar(texto: str) -> dict:
    # Solo se evalúa lo que escribe el modelo: se excluye la tabla del puente, que genera el código
    texto = texto.split("## Puente del resultado")[0]
    frases = partir_frases(texto)
    return {codigo: (desc, frase_que_identifica(frases, grupos)) for codigo, (desc, grupos) in CRITERIOS.items()}


def imprimir(nombre: str, resultado: dict) -> None:
    aciertos = sum(1 for _, frase in resultado.values() if frase)
    print(f"\n{nombre}: {aciertos} de {len(resultado)} causas identificadas")
    for codigo, (desc, frase) in resultado.items():
        marca = "✔" if frase else "✘"
        print(f"  {marca} {codigo:<4} {desc}")
        if frase:
            print(f"         «{frase[:110]}{'…' if len(frase) > 110 else ''}»")


if __name__ == "__main__":
    for ruta in sys.argv[1:]:
        imprimir(Path(ruta).name, evaluar(Path(ruta).read_text(encoding="utf-8")))
