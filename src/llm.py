"""
llm.py — Acceso al modelo de lenguaje, independiente del proveedor.

Configuración en el archivo .env de la raíz del proyecto:
    PROVEEDOR_LLM=ollama          # ollama | anthropic
    MODELO_LLM=qwen2.5-7b-16k
"""
import os
import time
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class RespuestaLLM:
    texto: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    segundos: float


def crear_cliente(proveedor: str) -> anthropic.Anthropic:
    if proveedor == "ollama":
        return anthropic.Anthropic(base_url="http://localhost:11434", api_key="ollama")
    if proveedor == "anthropic":
        return anthropic.Anthropic()          # usa ANTHROPIC_API_KEY del .env
    raise ValueError(f"Proveedor desconocido: {proveedor}")


def generar(sistema: str, mensaje: str, max_tokens: int = 2000) -> RespuestaLLM:
    """Envía instrucciones (sistema) y un mensaje al modelo configurado y devuelve su respuesta.
    La temperatura y la ventana de contexto del modelo local se fijan en el Modelfile."""
    proveedor = os.getenv("PROVEEDOR_LLM", "ollama")
    modelo = os.getenv("MODELO_LLM", "qwen2.5-7b-16k")
    cliente = crear_cliente(proveedor)

    inicio = time.perf_counter()
    r = cliente.messages.create(
        model=modelo,
        max_tokens=max_tokens,
        system=sistema,
        messages=[{"role": "user", "content": mensaje}],
    )
    texto = "".join(bloque.text for bloque in r.content if bloque.type == "text")

    return RespuestaLLM(texto=texto, modelo=modelo, tokens_entrada=r.usage.input_tokens,
                        tokens_salida=r.usage.output_tokens, segundos=time.perf_counter() - inicio)