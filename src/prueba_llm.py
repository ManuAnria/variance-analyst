import json

from hechos import construir_hechos
from llm import generar

hechos = construir_hechos(2026, 9)

r = generar(
    sistema="Eres un analista financiero. Responde solo con datos del JSON que se te proporciona.",
    mensaje=f"Datos:\n{json.dumps(hechos, ensure_ascii=False)}\n\n"
            "¿Cuál es la desviación del resultado antes de impuestos y cuál es la partida "
            "de otros gastos con mayor desviación?",
)
print(r.texto)
print(f"\n[{r.modelo}] {r.tokens_entrada} tokens entrada, {r.tokens_salida} salida, {r.segundos:.0f} s")