"""
validador.py — Comprueba un informe generado por el LLM contra el paquete de hechos.

Cuatro controles:
  1. Existencia:  cada cifra del texto está en el paquete (no hay cifras inventadas ni calculadas).
  2. Valoración:  si la frase dice "favorable"/"desfavorable", coincide con el signo de la cifra.
  3. Dirección:   si la frase dice "por encima"/"por debajo" del presupuesto, coincide con la realidad.
  4. Cobertura:   los principales impulsores del puente del resultado aparecen en el informe,
                  distinguiendo si solo se mencionan o si además se cuantifican.

Uso:  python validador.py salidas/informe_xxx.md
"""
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Campos cuyo signo sigue la convención "positivo = favorable"
CAMPOS_CON_VALORACION = ("desviacion", "efecto_", "importe")

PALABRAS_ENCIMA = ("por encima", "superior", "más que el presupuesto", "mayor que el presupuesto", "aumentado")
PALABRAS_DEBAJO = ("por debajo", "inferior", "menos que el presupuesto", "menor que el presupuesto")

# Palabras que identifican cada tipo de impulsor del puente (sin tildes, en minúscula)
CLAVES_TIPO = {
    "volumen": ("volumen",),
    "mix": ("mix",),
    "precio": ("precio",),
    "coste_unitario": ("coste unitario", "coste de compra", "costes de compra", "coste unitario de compra"),
    "plantilla": ("plantilla",),
    "coste_medio": ("coste medio",),
    "tarifa": ("tarifa",),
    "actividad": ("actividad",),
    "gasto": (),                       # partidas de gasto: basta con nombrar la cuenta
}
PALABRAS_VACIAS = {"material", "de", "del", "y", "la", "el", "los", "las"}


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


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: 'Logística' -> 'logistica'."""
    sin_tildes = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def raiz_objeto(objeto: str | None) -> str | None:
    """Palabra que identifica el objeto: 'Material de oficina' -> 'oficina', 'Transportes' -> 'transport'."""
    if not objeto:
        return None
    palabras = [p for p in re.findall(r"[a-z]+", normalizar(objeto)) if p not in PALABRAS_VACIAS]
    p = palabras[0]
    if p.endswith("es") and len(p) > 6:
        return p[:-2]                                  # reparaciones -> reparacion, transportes -> transport
    return p[:-1] if p.endswith("s") else p            # libros -> libro


def menciona(frase: str, impulsor: dict) -> bool:
    """La frase habla del impulsor: contiene una palabra de su tipo y el nombre de su objeto."""
    f = normalizar(frase)
    claves = CLAVES_TIPO.get(impulsor["tipo"], ())
    raiz = raiz_objeto(impulsor.get("objeto"))
    tiene_tipo = not claves or any(c in f for c in claves)
    tiene_objeto = raiz is None or raiz in f
    return tiene_tipo and tiene_objeto


@dataclass
class Resultado:
    cifras_revisadas: int = 0
    no_encontradas: list = field(default_factory=list)
    unidad_incorrecta: list = field(default_factory=list)
    valoracion_incorrecta: list = field(default_factory=list)
    direccion_incorrecta: list = field(default_factory=list)
    signo_invertido: list = field(default_factory=list)
    impulsores_cuantificados: list = field(default_factory=list)     # mencionado y con su importe
    impulsores_sin_importe: list = field(default_factory=list)       # mencionado, pero sin importe
    impulsores_omitidos: list = field(default_factory=list)

    @property
    def errores(self) -> int:
        return (len(self.no_encontradas) + len(self.unidad_incorrecta) + len(self.valoracion_incorrecta)
                + len(self.direccion_incorrecta) + len(self.signo_invertido))

    @property
    def _total_impulsores(self) -> int:
        return len(self.impulsores_cuantificados) + len(self.impulsores_sin_importe) + len(self.impulsores_omitidos)

    @property
    def cobertura_mencion(self) -> float:
        menc = len(self.impulsores_cuantificados) + len(self.impulsores_sin_importe)
        return menc / self._total_impulsores if self._total_impulsores else 1.0

    @property
    def cobertura_cuantificada(self) -> float:
        return len(self.impulsores_cuantificados) / self._total_impulsores if self._total_impulsores else 1.0


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

    # Control 4: cobertura de los principales impulsores (mencionado / cuantificado)
    frases = partir_frases(texto)
    for imp in paquete.get("puente_resultado", {}).get("principales_impulsores", []):
        etiqueta = f"{imp['concepto']} ({imp['importe_texto']}, {imp['valoracion']})"
        frases_que_lo_citan = [f for f in frases if menciona(f, imp)]
        if not frases_que_lo_citan:
            res.impulsores_omitidos.append(etiqueta)
        elif any(abs(abs(c.valor) - abs(imp["importe"])) <= 1
                 for c in extraer_cifras("\n".join(frases_que_lo_citan)) if not c.es_porcentaje):
            res.impulsores_cuantificados.append(etiqueta)
        else:
            res.impulsores_sin_importe.append(etiqueta)

    return res


# --------------------------------------------------------------------------- #
# 4. Informe del validador
# --------------------------------------------------------------------------- #
def imprimir(res: Resultado) -> None:
    print(f"Cifras revisadas: {res.cifras_revisadas}   Errores: {res.errores}   "
          f"Impulsores mencionados: {res.cobertura_mencion:.0%}   "
          f"cuantificados: {res.cobertura_cuantificada:.0%}")
    secciones = [("Cifras que no están en el paquete", res.no_encontradas),
                 ("Unidad incorrecta", res.unidad_incorrecta),
                 ("Signo invertido", res.signo_invertido),
                 ("Valoración incorrecta (favorable/desfavorable)", res.valoracion_incorrecta),
                 ("Dirección incorrecta (por encima/por debajo)", res.direccion_incorrecta),
                 ("Impulsores mencionados sin su importe", res.impulsores_sin_importe),
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
