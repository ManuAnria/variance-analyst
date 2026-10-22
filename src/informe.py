"""
informe.py — Genera el comentario de desviaciones con el modelo de lenguaje.

    hechos (motor de cálculo)  +  supuestos del presupuesto  ->  LLM  ->  informe en Markdown

Uso:  python informe.py        -> salidas/informe_<modelo>_<fecha-hora>.md
"""
from datetime import datetime
from pathlib import Path

from hechos import construir_hechos, guardar_hechos
from llm import generar
from prompts import SISTEMA, VERSION_PROMPT, mensaje_usuario
from validador import imprimir, validar

RAIZ = Path(__file__).resolve().parent.parent


def tabla_puente(hechos: dict) -> str:
    """Tabla Markdown del puente del resultado, generada por el código (las cifras no pasan por el modelo)."""
    puente = hechos["puente_resultado"]
    filas = ["| Impulsor | Importe | Valoración |", "|---|---:|---|"]
    for imp in puente["principales_impulsores"]:
        filas.append(f"| {imp['concepto']} | {imp['importe_texto']} | {imp['valoracion']} |")
    resto = puente["resto"]
    filas.append(f"| Resto ({resto['numero_efectos']} efectos menores) | {resto['importe_texto']} | {resto['valoracion']} |")
    filas.append(f"| **Desviación del resultado antes de impuestos** | **{puente['desviacion_resultado_texto']}** | "
                 f"**{'favorable' if puente['desviacion_resultado'] > 0 else 'desfavorable'}** |")
    return "\n".join(filas)


def generar_informe(ejercicio: int, mes_hasta: int) -> Path:
    # 1. Hechos calculados por el motor (y copia para trazabilidad)
    hechos = construir_hechos(ejercicio, mes_hasta)
    guardar_hechos(hechos)

    # 2. Contexto: los supuestos del presupuesto en lenguaje natural
    supuestos = (RAIZ / "datos" / "supuestos_presupuesto_2026.md").read_text(encoding="utf-8")

    # 3. Llamada al modelo
    r = generar(SISTEMA, mensaje_usuario(hechos, supuestos), max_tokens=2500)

    # 4. Control de calidad: el validador revisa SOLO el texto del modelo (la tabla la genera el código)
    control = validar(r.texto, hechos)
    informe_completo = (r.texto.rstrip() + "\n\n## Puente del resultado\n"
                        "*Tabla calculada por el motor; las cifras no pasan por el modelo de lenguaje.*\n\n"
                        + tabla_puente(hechos) + "\n")

    # 5. Guardar el informe con su "ficha técnica" al principio
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_modelo = r.modelo.replace(":", "-").replace("/", "-")
    ruta = RAIZ / "salidas" / f"informe_{nombre_modelo}_{marca}.md"

    cabecera = (
        f"<!-- modelo: {r.modelo} | prompt: {VERSION_PROMPT} | periodo: {ejercicio} meses 1-{mes_hasta} | "
        f"tokens: {r.tokens_entrada} entrada / {r.tokens_salida} salida | {r.segundos:.0f} s | "
        f"errores: {control.errores} | impulsores mencionados: {control.cobertura_mencion:.0%} | "
        f"cuantificados: {control.cobertura_cuantificada:.0%} -->\n\n"
    )
    ruta.write_text(cabecera + informe_completo, encoding="utf-8")

    print(informe_completo)
    print(f"\n[{r.modelo}] {r.tokens_entrada} tokens entrada, {r.tokens_salida} salida, {r.segundos:.0f} s")
    print(f"Informe guardado en {ruta}\n")
    print("=== CONTROL DE CALIDAD ===")
    imprimir(control)
    return ruta


if __name__ == "__main__":
    generar_informe(2026, 9)
