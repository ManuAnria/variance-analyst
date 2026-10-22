"""
validador.py — Comprueba un informe generado por el LLM contra el paquete de hechos.

Cuatro controles:
  1. Existencia:  cada cifra del texto está en el paquete (no hay cifras inventadas ni calculadas).
  2. Valoración:  si la frase dice "favorable"/"desfavorable", coincide con el signo de la cifra.
  3. Dirección:   si la frase dice "por encima"/"por debajo" del presupuesto, coincide con la realidad.
  4. Cobertura:   los principales impulsores del puente del resultado aparecen en el informe.

Uso:  python validador.py salidas/informe_xxx.md
"""
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Campos cuyo signo sigue la convención "positivo = favorable"
CAMPOS_CON_VALORACION = ("desviacion", "efecto_", "importe")

PALABRAS_ENCIMA = ("por encima", "superior", "más que el presupuesto", "mayor que el presupuesto", "aumentado")
PALABRAS_DEBAJO = ("por debajo", "inferior", "menos que el presupuesto", "menor que el presupuesto")


# --------------------------------------------------------------------------- #
# 1. Las cifras del paquete de hechos
# --------------------------------------------------------------------------- #
@dataclass
class Hecho:
    valor: float
    campo: str
    ruta: str
    comparacion: str | None = None      # "por encima del presupuesto" / "por debajo..." (si la fila la tiene)

    @property
    def es_porcentaje(self) -> bool:
        return "pct" in self.campo or self.ruta.startswith("margen_bruto_pct")

    @property
    def es_fte(self) -> bool:
        return "fte" in self.campo

    @property
    def valoracion(self) -> str | None:
        if not self.campo.startswith(CAMPOS_CON_VALORACION) or abs(self.valor) < 500:
            return None
        return "favorable" if self.valor > 0 else "desfavorable"


def recorrer_hechos(nodo, ruta: str = "", comparacion: str | None = None) -> list[Hecho]:
    """Recorre el JSON entero y devuelve cada número con su campo, su ruta y la comparación de su fila."""
    hechos = []
    if isinstance(nodo, dict):
        comparacion = nodo.get("comparacion", comparacion)
        for clave, valor in nodo.items():
            if isinstance(valor, bool):
                continue
            if isinstance(valor, (int, float)):
                hechos.append(Hecho(float(valor), clave, f"{ruta}.{clave}".strip("."), comparacion))
            elif isinstance(valor, str):
                # Cifras dentro de textos interpretados por el motor, p. ej. "8 FTE-mes más que el presupuesto"
                for m in re.finditer(r"(\d+(?:,\d+)?)\s*(FTE)?", valor):
                    campo = "fte_texto" if m.group(2) else "texto"
                    hechos.append(Hecho(float(m.group(1).replace(",", ".")), campo,
                                        f"{ruta}.{clave}".strip("."), comparacion))
            else:
                hechos += recorrer_hechos(valor, f"{ruta}.{clave}".strip("."), comparacion)
    elif isinstance(nodo, list):
        for i, elemento in enumerate(nodo):
            hechos += recorrer_hechos(elemento, f"{ruta}[{i}]", None)
    return hechos


# --------------------------------------------------------------------------- #
# 2. Las cifras del informe
# --------------------------------------------------------------------------- #
@dataclass
class Cifra:
    texto: str
    valor: float
    es_porcentaje: bool
    es_fte: bool
    frase: str
    posicion: int                        # posición de la cifra dentro de la frase


PATRON_CIFRA = re.compile(
    r"(?P<num>[-−–+]?\d{1,3}(?:\.\d{3})+(?:,\d+)?|[-−–+]?\d+(?:[.,]\d+)?)"   # 1.234.567,8 | 49.6 | 5,9 | 263
    r"(?P<sufijo>\s*(?:%|€|FTE)?)"
)


def a_numero(texto: str) -> float:
    """Convierte el formato español (y el inglés que a veces usa el modelo) en número."""
    t = texto.replace("−", "-").replace("–", "-").replace("+", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):    # 7.370.400 o 1.234,5 -> separador de miles
        t = t.replace(".", "").replace(",", ".")
    else:                                                 # 5,9 o 49.6 -> decimal
        t = t.replace(",", ".")
    return float(t)


def partir_frases(texto: str) -> list[str]:
    """Divide en frases sin romper los separadores de miles (7.370.400) ni los decimales."""
    lineas = [l for l in texto.splitlines() if l.strip() and not l.lstrip().startswith(("#", "<!--"))]
    frases = []
    for linea in lineas:
        frases += [f.strip() for f in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿(])", linea) if f.strip()]
    return frases


def extraer_cifras(texto: str) -> list[Cifra]:
    cifras = []
    for frase in partir_frases(texto):
        frase_sin_lista = re.sub(r"^\s*(\d+\.|-|\*)\s+", "", frase)       # quita "1. " o "- " de las listas
        for m in PATRON_CIFRA.finditer(frase_sin_lista):
            sufijo = m.group("sufijo").strip()
            valor = a_numero(m.group("num"))
            # Se ignoran números sueltos pequeños sin unidad (meses, recuentos) y el año
            if not sufijo and (abs(valor) <= 31 or valor == 2026):
                continue
            cifras.append(Cifra(m.group(0).strip(), valor, sufijo == "%", sufijo == "FTE",
                                frase_sin_lista, m.start()))
    return cifras


# --------------------------------------------------------------------------- #
# 3. Los controles
# --------------------------------------------------------------------------- #
def buscar(cifra: Cifra, hechos: list[Hecho]) -> list[Hecho]:
    """Hechos del paquete que coinciden con la cifra (en valor absoluto: el texto puede omitir el signo)."""
    tolerancia = 0.05 if cifra.es_porcentaje else 1
    candidatos = [h for h in hechos if h.es_porcentaje == cifra.es_porcentaje]
    return [h for h in candidatos if abs(abs(h.valor) - abs(cifra.valor)) <= tolerancia]


def palabra_mas_cercana(frase: str, posicion: int, grupos: dict[str, tuple[str, ...]]) -> str | None:
    """De varias palabras clave, devuelve el grupo de la que aparece más cerca de la cifra en la frase."""
    mejor, distancia = None, None
    f = frase.lower()
    for etiqueta, palabras in grupos.items():
        for p in palabras:
            for m in re.finditer(re.escape(p), f):
                if p == "favorable" and f[max(0, m.start() - 3):m.start()] == "des":
                    continue                                   # "desfavorable" no cuenta como "favorable"
                d = abs(m.start() - posicion)
                if distancia is None or d < distancia:
                    mejor, distancia = etiqueta, d
    return mejor


@dataclass
class Resultado:
    cifras_revisadas: int = 0
    no_encontradas: list = field(default_factory=list)
    unidad_incorrecta: list = field(default_factory=list)
    valoracion_incorrecta: list = field(default_factory=list)
    direccion_incorrecta: list = field(default_factory=list)
    signo_invertido: list = field(default_factory=list)
    impulsores_citados: list = field(default_factory=list)
    impulsores_omitidos: list = field(default_factory=list)

    @property
    def errores(self) -> int:
        return (len(self.no_encontradas) + len(self.unidad_incorrecta) + len(self.valoracion_incorrecta)
                + len(self.direccion_incorrecta) + len(self.signo_invertido))

    @property
    def cobertura(self) -> float:
        total = len(self.impulsores_citados) + len(self.impulsores_omitidos)
        return len(self.impulsores_citados) / total if total else 1.0


def validar(texto: str, paquete: dict) -> Resultado:
    hechos = recorrer_hechos(paquete)
    res = Resultado()

    for c in extraer_cifras(texto):
        res.cifras_revisadas += 1
        coincidencias = buscar(c, hechos)
        detalle = f"«{c.texto}» en: {c.frase}"

        # Control 1: existencia
        if not coincidencias:
            res.no_encontradas.append(detalle)
            continue

        # Unidad: si el texto dice FTE, la cifra tiene que ser un dato de plantilla
        if c.es_fte and not any(h.es_fte for h in coincidencias):
            res.unidad_incorrecta.append(f"{detalle}  -> en el paquete es un importe en €, no FTE")

        # Signo explícito contrario al del paquete (solo campos con valoración)
        con_valoracion = [h for h in coincidencias if h.valoracion]
        if c.texto.lstrip()[0] in "-−–+" and con_valoracion:
            if all((h.valor > 0) != (c.valor > 0) for h in con_valoracion):
                res.signo_invertido.append(f"{detalle}  -> en el paquete: {con_valoracion[0].valor:+,.0f}")

        # Control 2: valoración (favorable / desfavorable) — solo si la cifra no es ambigua
        valoraciones = {h.valoracion for h in con_valoracion}
        if len(valoraciones) == 1:
            dicha = palabra_mas_cercana(c.frase, c.posicion,
                                        {"favorable": ("favorable",), "desfavorable": ("desfavorable",)})
            correcta = valoraciones.pop()
            if dicha and dicha != correcta:
                res.valoracion_incorrecta.append(f"{detalle}  -> dice «{dicha}», es «{correcta}»")

        # Control 3: dirección (por encima / por debajo del presupuesto)
        comparaciones = {h.comparacion for h in coincidencias if h.comparacion}
        if len(comparaciones) == 1:
            correcta = comparaciones.pop()
            dicha = palabra_mas_cercana(c.frase, c.posicion,
                                        {"por encima del presupuesto": PALABRAS_ENCIMA,
                                         "por debajo del presupuesto": PALABRAS_DEBAJO})
            if dicha and "en línea" not in correcta and dicha != correcta:
                res.direccion_incorrecta.append(f"{detalle}  -> dice «{dicha}», es «{correcta}»")

    # Control 4: cobertura de los principales impulsores
    valores_texto = {abs(c.valor) for c in extraer_cifras(texto) if not c.es_porcentaje}
    for imp in paquete.get("puente_resultado", {}).get("principales_impulsores", []):
        citado = any(abs(abs(imp["importe"]) - v) <= 1 for v in valores_texto)
        (res.impulsores_citados if citado else res.impulsores_omitidos).append(
            f"{imp['concepto']} ({imp['importe']:+,} €)")

    return res


# --------------------------------------------------------------------------- #
# 4. Informe del validador
# --------------------------------------------------------------------------- #
def imprimir(res: Resultado) -> None:
    print(f"Cifras revisadas: {res.cifras_revisadas}   Errores: {res.errores}   "
          f"Cobertura de impulsores: {res.cobertura:.0%}")
    secciones = [("Cifras que no están en el paquete", res.no_encontradas),
                 ("Unidad incorrecta", res.unidad_incorrecta),
                 ("Signo invertido", res.signo_invertido),
                 ("Valoración incorrecta (favorable/desfavorable)", res.valoracion_incorrecta),
                 ("Dirección incorrecta (por encima/por debajo)", res.direccion_incorrecta),
                 ("Impulsores principales omitidos", res.impulsores_omitidos)]
    for titulo, lista in secciones:
        if lista:
            print(f"\n{titulo} ({len(lista)}):")
            for linea in lista:
                print(f"  - {linea}")


if __name__ == "__main__":
    ruta_informe = Path(sys.argv[1])
    paquete = json.loads((RAIZ / "salidas" / "hechos_desviaciones.json").read_text(encoding="utf-8"))
    imprimir(validar(ruta_informe.read_text(encoding="utf-8"), paquete))
