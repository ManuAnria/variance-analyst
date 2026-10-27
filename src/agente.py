"""
agente.py — Agente que investiga las desviaciones usando herramientas (drill-down).

El bucle de un agente:
    1. El modelo recibe la tarea y la lista de herramientas disponibles.
    2. Si necesita datos, en lugar de responder pide una herramienta ("tool_use").
    3. El código ejecuta la herramienta y le devuelve el resultado ("tool_result").
    4. Se repite hasta que el modelo responde con texto, o hasta el límite de rondas.

Todo lo que el agente consulta queda registrado (traza) para auditar de dónde sale cada hallazgo.
"""
import json
import os
import time
from dataclasses import dataclass, field

from herramientas import HERRAMIENTAS, ejecutar
from llm import crear_cliente

MAX_RONDAS = 6          # límite de seguridad: un agente sin límite puede entrar en bucle

SISTEMA_AGENTE = """Eres un analista de control de gestión de Grafilia Distribución S.L. que investiga las causas
de las desviaciones del resultado frente al presupuesto (enero a septiembre de 2026).

Dispones de herramientas para consultar los datos. Úsalas: no respondas sin haber consultado los datos.
- Para una desviación de VOLUMEN de ventas, consulta las ventas por cliente.
- Para una desviación de COSTE UNITARIO de compra, consulta el coste unitario mes a mes; si un mes es anómalo,
  consulta las facturas de compra de ese mes y compara la fecha de factura con la de contabilización.

REGLAS
1. Usa ÚNICAMENTE cifras que aparezcan en los resultados de las herramientas o en la tarea. No calcules nada.
2. Si un resultado contiene "siguiente_paso", HAZ esa consulta antes de responder.
3. Usa los campos ya interpretados ("situacion", "alertas") tal como vienen: no los reinterpretes.
4. Escribe los importes en formato español: punto de miles y coma decimal (473.744 €; 6,89 €).
5. Si los datos no permiten concluir, dilo ("no concluyente"). No inventes causas.
6. Haz como máximo 6 consultas.

Cuando termines, responde con este formato (Markdown, en español):
## Hallazgos de la investigación
- **<impulsor investigado>**: <qué has encontrado>. Evidencia: <cifras de las herramientas que lo demuestran>.
"""


@dataclass
class ResultadoAgente:
    texto: str
    traza: list = field(default_factory=list)      # [{herramienta, argumentos, resultado}, ...]
    rondas: int = 0
    segundos: float = 0.0


def bloques_a_dict(contenido) -> list[dict]:
    """Convierte la respuesta del modelo en el formato que hay que devolverle en la conversación."""
    bloques = []
    for b in contenido:
        if b.type == "text":
            bloques.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            bloques.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return bloques


def tarea_desde_hechos(hechos: dict, n: int = 3) -> str:
    """La tarea: investigar los n mayores impulsores desfavorables del puente del resultado."""
    desfavorables = [i for i in hechos["puente_resultado"]["principales_impulsores"]
                     if i["valoracion"] == "desfavorable"][:n]
    lineas = "\n".join(f"- {i['concepto']}: efecto desfavorable de {i['importe_texto']}" for i in desfavorables)
    return f"Investiga la causa de estos impulsores desfavorables del resultado:\n{lineas}"


def investigar(tarea: str, cliente=None, modelo: str | None = None) -> ResultadoAgente:
    proveedor = os.getenv("PROVEEDOR_LLM", "ollama")
    # Se puede usar un modelo distinto para el agente (MODELO_AGENTE en el .env); si no, el mismo del informe
    modelo = modelo or os.getenv("MODELO_AGENTE") or os.getenv("MODELO_LLM", "qwen2.5-7b-16k")
    cliente = cliente or crear_cliente(proveedor)

    mensajes = [{"role": "user", "content": tarea}]
    res = ResultadoAgente(texto="")
    inicio = time.perf_counter()

    for ronda in range(1, MAX_RONDAS + 1):
        r = cliente.messages.create(model=modelo, max_tokens=1500, system=SISTEMA_AGENTE,
                                    messages=mensajes, tools=HERRAMIENTAS)
        res.rondas = ronda
        mensajes.append({"role": "assistant", "content": bloques_a_dict(r.content)})

        peticiones = [b for b in r.content if b.type == "tool_use"]
        if not peticiones:                                   # el modelo ya ha respondido con texto
            res.texto = "".join(b.text for b in r.content if b.type == "text")
            break

        resultados = []
        for p in peticiones:                                 # puede pedir varias herramientas a la vez
            salida = ejecutar(p.name, p.input)
            res.traza.append({"herramienta": p.name, "argumentos": p.input, "resultado": salida})
            print(f"  [ronda {ronda}] {p.name}({p.input})")
            resultados.append({"type": "tool_result", "tool_use_id": p.id,
                               "content": json.dumps(salida, ensure_ascii=False)})
        mensajes.append({"role": "user", "content": resultados})
    else:
        res.texto = "## Hallazgos de la investigación\n- Investigación interrumpida: se alcanzó el límite de rondas."

    res.segundos = time.perf_counter() - inicio
    return res


if __name__ == "__main__":
    # Prueba rápida del agente, sin generar el informe completo:  python agente.py
    from hechos import construir_hechos
    from validador import validar

    hechos = construir_hechos(2026, 9)
    tarea = tarea_desde_hechos(hechos)
    print(tarea, "\n")
    r = investigar(tarea)
    print(f"\n{r.texto}\n\n[{r.rondas} rondas, {len(r.traza)} consultas, {r.segundos:.0f} s]")
    control = validar(r.texto, hechos, adicionales=[t["resultado"] for t in r.traza])
    print(f"Cifras revisadas: {control.cifras_revisadas}   Errores: {control.errores}")
    for linea in control.no_encontradas:
        print(f"  - {linea}")
