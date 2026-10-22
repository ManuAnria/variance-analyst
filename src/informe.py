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


def generar_informe(ejercicio: int, mes_hasta: int) -> Path:
    # 1. Hechos calculados por el motor (y copia para trazabilidad)
    hechos = construir_hechos(ejercicio, mes_hasta)
    guardar_hechos(hechos)

    # 2. Contexto: los supuestos del presupuesto en lenguaje natural
    supuestos = (RAIZ / "datos" / "supuestos_presupuesto_2026.md").read_text(encoding="utf-8")

    # 3. Llamada al modelo
    r = generar(SISTEMA, mensaje_usuario(hechos, supuestos), max_tokens=2500)

    # 4. Control de calidad: el validador revisa el texto contra el paquete de hechos
    control = validar(r.texto, hechos)

    # 5. Guardar el informe con su "ficha técnica" al principio
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_modelo = r.modelo.replace(":", "-").replace("/", "-")
    ruta = RAIZ / "salidas" / f"informe_{nombre_modelo}_{marca}.md"

    cabecera = (
          f"tokens: {r.tokens_entrada} entrada / {r.tokens_salida} salida | {r.segundos:.0f} s | "
          f"errores: {control.errores} | cobertura: {control.cobertura:.0%} -->\n\n"
    )
    ruta.write_text(cabecera + r.texto, encoding="utf-8")

    print(r.texto)
    print(f"\n[{r.modelo}] {r.tokens_entrada} tokens entrada, {r.tokens_salida} salida, {r.segundos:.0f} s")
    print(f"Informe guardado en {ruta}\n")
    print("=== CONTROL DE CALIDAD ===")
    imprimir(control)
    return ruta


if __name__ == "__main__":
    generar_informe(2026, 9)