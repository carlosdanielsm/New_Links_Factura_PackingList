"""
Buscador de candidatos para Alibaba y Made in China.

Versión MVP 2:
- Busca candidatos usando resultados web de DuckDuckGo/DDGS.
- Prioriza Alibaba como fuente principal y Made in China como respaldo.
- No intenta evadir CAPTCHA ni automatizar acciones sensibles.
- Si no puede detectar el precio desde el resultado de búsqueda, deja el precio vacío
  y marca el registro para revisión.

IMPORTANTE:
Esta capa sirve para validar el flujo con 20 productos. Para una versión más robusta
se recomienda reemplazar la búsqueda por una API/servicio de datos autorizado.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse

try:
    from ddgs import DDGS  # paquete nuevo
except Exception:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS  # paquete anterior
    except Exception:  # pragma: no cover
        DDGS = None


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "are", "was", "were",
    "product", "products", "factory", "supplier", "suppliers", "manufacturer",
    "manufacturers", "china", "chinese", "wholesale", "custom", "new", "hot",
    "sale", "high", "quality", "best", "cheap", "price", "buy", "online",
    "de", "la", "el", "los", "las", "para", "con", "por", "del",
}

PLATFORM_CONFIG = {
    "Alibaba": {
        "query": 'site:alibaba.com/product-detail "{producto}"',
        "domains": ["alibaba.com"],
        "fallback_search_url": "https://www.alibaba.com/trade/search?SearchText={q}",
    },
    "Made in China": {
        "query": 'site:made-in-china.com/product "{producto}"',
        "domains": ["made-in-china.com"],
        "fallback_search_url": "https://www.made-in-china.com/products-search/hot-china-products/{q}.html",
    },
}


@dataclass
class Candidate:
    title: str
    link: str
    snippet: str
    platform: str
    precio_detectado: float | None
    score_producto: float
    diferencia_precio: float | None
    score_final: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "link": self.link,
            "snippet": self.snippet,
            "platform": self.platform,
            "precio_detectado": self.precio_detectado,
            "score_producto": round(self.score_producto, 2),
            "diferencia_precio": None if self.diferencia_precio is None else round(self.diferencia_precio, 2),
            "score_final": round(self.score_final, 2),
        }


def _normalizar(texto: Any) -> str:
    if texto is None:
        return ""
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9.+\-/\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _tokens(texto: Any) -> set[str]:
    texto = _normalizar(texto)
    raw_tokens = re.findall(r"[a-z0-9]+(?:[.+\-/][a-z0-9]+)*", texto)
    return {t for t in raw_tokens if len(t) >= 2 and t not in STOPWORDS}


def _tokens_especificaciones(texto: Any) -> set[str]:
    """Extrae tokens técnicos que ayudan a validar que sea el mismo producto."""
    texto = _normalizar(texto)
    patrones = [
        r"\b\d+(?:\.\d+)?\s?(?:v|w|a|ah|mah|hz|kg|g|mm|cm|m|l|ml|oz|inch|in|pcs|pc|gb|tb)\b",
        r"\b\d+(?:\.\d+)?\s?[x×*]\s?\d+(?:\.\d+)?(?:\s?[x×*]\s?\d+(?:\.\d+)?)?\b",
        r"\b[a-z]{1,6}\d{1,6}[a-z0-9\-/]*\b",
        r"\b\d{2,}\b",
    ]
    specs: set[str] = set()
    for patron in patrones:
        specs.update(match.replace(" ", "") for match in re.findall(patron, texto))
    return specs


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        number = float(str(value).replace(",", ""))
        if math.isnan(number):
            return None
        return number
    except Exception:
        return None


def _extraer_precios(texto: str) -> list[float]:
    """Intenta extraer precios visibles en snippets/resultados de búsqueda."""
    if not texto:
        return []

    # Captura precios con símbolos o palabras comunes. Ej: US$ 1.20, $0.40-$0.80, USD 3.5
    patron = re.compile(
        r"(?:US\$|USD|\$)\s*([0-9]{1,6}(?:[.,][0-9]{1,4})?)",
        flags=re.IGNORECASE,
    )
    precios: list[float] = []
    for match in patron.findall(texto):
        try:
            precios.append(float(match.replace(",", "")))
        except ValueError:
            pass

    # Algunos snippets traen textos tipo "FOB Price: 0.25-0.30 USD/Piece"
    patron_fob = re.compile(
        r"(?:price|precio|fob)\D{0,20}([0-9]{1,6}(?:[.,][0-9]{1,4})?)",
        flags=re.IGNORECASE,
    )
    for match in patron_fob.findall(texto):
        try:
            precios.append(float(match.replace(",", "")))
        except ValueError:
            pass

    # Limpieza: evita falsos positivos demasiado altos o cero.
    return [p for p in precios if 0 < p < 100000]


def _seleccionar_precio_mas_cercano(precios: list[float], price_objetivo: Any) -> float | None:
    if not precios:
        return None
    objetivo = _to_float(price_objetivo)
    if objetivo is None or objetivo <= 0:
        return precios[0]
    return min(precios, key=lambda p: abs(p - objetivo))


def _diferencia_porcentual(price_objetivo: Any, precio_encontrado: Any) -> float | None:
    objetivo = _to_float(price_objetivo)
    encontrado = _to_float(precio_encontrado)
    if objetivo is None or encontrado is None or objetivo == 0:
        return None
    return ((encontrado - objetivo) / objetivo) * 100


def _score_texto(producto: str, title: str, snippet: str) -> float:
    producto_tokens = _tokens(producto)
    candidato_tokens = _tokens(f"{title} {snippet}")

    if not producto_tokens:
        return 0.0

    overlap = len(producto_tokens & candidato_tokens) / max(len(producto_tokens), 1)

    producto_specs = _tokens_especificaciones(producto)
    candidato_specs = _tokens_especificaciones(f"{title} {snippet}")

    if producto_specs:
        spec_overlap = len(producto_specs & candidato_specs) / max(len(producto_specs), 1)
    else:
        spec_overlap = 0.0

    # Peso alto al overlap de palabras y extra a especificaciones técnicas.
    score = (overlap * 75) + (spec_overlap * 25)
    return min(score, 100.0)


def _score_final(score_producto: float, diferencia_precio: float | None) -> float:
    if diferencia_precio is None:
        # Sin precio todavía puede ser buen candidato, pero requiere revisión.
        return score_producto * 0.85

    diferencia_abs = abs(diferencia_precio)
    # 100 si la diferencia es 0, 0 si diferencia >= 100%.
    score_precio = max(0.0, 100.0 - min(diferencia_abs, 100.0))
    return (score_producto * 0.70) + (score_precio * 0.30)


def _link_pertenece_a_plataforma(link: str, platform: str) -> bool:
    if not link:
        return False
    netloc = urlparse(link).netloc.lower()
    domains = PLATFORM_CONFIG[platform]["domains"]
    return any(domain in netloc for domain in domains)


def _buscar_web(query: str, max_results: int = 8) -> list[dict[str, str]]:
    if DDGS is None:
        return []

    try:
        with DDGS() as ddgs:
            try:
                results = list(ddgs.text(query, max_results=max_results))
            except TypeError:
                results = list(ddgs.text(query, max_results))
    except Exception:
        return []

    salida = []
    for result in results:
        title = result.get("title") or ""
        link = result.get("href") or result.get("url") or ""
        body = result.get("body") or result.get("snippet") or ""
        if link:
            salida.append({"title": title, "link": link, "snippet": body})
    return salida


def generar_url_busqueda(producto_ingles: str, platform: str) -> str:
    q = quote_plus(str(producto_ingles or "").strip())
    return PLATFORM_CONFIG[platform]["fallback_search_url"].format(q=q)


def buscar_candidatos(
    producto_ingles: str,
    total_unit: int | float | str,
    price: float | str,
    usar_made_in_china: bool = True,
    max_por_fuente: int = 6,
    pausa_segundos: float = 0.4,
) -> list[dict[str, Any]]:
    """Busca candidatos web y devuelve una lista ordenada por score."""
    plataformas = ["Alibaba"] + (["Made in China"] if usar_made_in_china else [])
    candidatos: list[Candidate] = []
    vistos: set[str] = set()

    for platform in plataformas:
        query = PLATFORM_CONFIG[platform]["query"].format(producto=producto_ingles)
        resultados = _buscar_web(query, max_results=max_por_fuente)

        for resultado in resultados:
            link = resultado.get("link", "")
            if link in vistos or not _link_pertenece_a_plataforma(link, platform):
                continue
            vistos.add(link)

            title = resultado.get("title", "")
            snippet = resultado.get("snippet", "")
            texto_candidato = f"{title} {snippet}"
            precios = _extraer_precios(texto_candidato)
            precio_detectado = _seleccionar_precio_mas_cercano(precios, price)
            diferencia = _diferencia_porcentual(price, precio_detectado)
            score_producto = _score_texto(producto_ingles, title, snippet)
            score_total = _score_final(score_producto, diferencia)

            candidatos.append(
                Candidate(
                    title=title,
                    link=link,
                    snippet=snippet,
                    platform=platform,
                    precio_detectado=precio_detectado,
                    score_producto=score_producto,
                    diferencia_precio=diferencia,
                    score_final=score_total,
                )
            )

        time.sleep(pausa_segundos)

    candidatos.sort(key=lambda c: c.score_final, reverse=True)
    return [c.to_dict() for c in candidatos]


def construir_resultado_para_excel(
    producto_ingles: str,
    total_unit: int | float | str,
    price: float | str,
    usar_made_in_china: bool = True,
) -> dict[str, Any]:
    """Devuelve una fila lista para rellenar columnas nuevas del Excel."""
    candidatos = buscar_candidatos(
        producto_ingles=producto_ingles,
        total_unit=total_unit,
        price=price,
        usar_made_in_china=usar_made_in_china,
    )

    if not candidatos:
        return {
            "LINK_RECOMENDADO": generar_url_busqueda(producto_ingles, "Alibaba"),
            "PLATAFORMA_RESULTADO": "Alibaba",
            "PRECIO_ENCONTRADO": "",
            "COINCIDENCIA_PRODUCTO": "Baja",
            "MOTIVO_SELECCION": "No se encontraron productos directos. Se deja URL de búsqueda para revisión manual.",
            "LINK_ALTERNATIVO_1": generar_url_busqueda(producto_ingles, "Made in China") if usar_made_in_china else "",
            "LINK_ALTERNATIVO_2": "",
        }

    mejor = candidatos[0]
    alt1 = candidatos[1]["link"] if len(candidatos) > 1 else ""
    alt2 = candidatos[2]["link"] if len(candidatos) > 2 else ""

    score_producto = mejor.get("score_producto") or 0
    diferencia = mejor.get("diferencia_precio")
    precio = mejor.get("precio_detectado")

    if score_producto >= 70 and diferencia is not None and abs(float(diferencia)) <= 20:
        coincidencia = "Alta"
        motivo = "Producto muy compatible y precio dentro del margen ±20%."
    elif score_producto >= 65 and precio is None:
        coincidencia = "Media"
        motivo = "Producto compatible, pero no se pudo detectar precio desde el resultado. Revisar precio."
    elif score_producto >= 45:
        coincidencia = "Media"
        motivo = "Producto posiblemente compatible. Revisar precio, cantidad y especificaciones."
    else:
        coincidencia = "Baja"
        motivo = "Coincidencia baja. Revisar manualmente antes de aprobar."

    return {
        "LINK_RECOMENDADO": mejor.get("link", ""),
        "PLATAFORMA_RESULTADO": mejor.get("platform", ""),
        "PRECIO_ENCONTRADO": "" if precio is None else precio,
        "COINCIDENCIA_PRODUCTO": coincidencia,
        "MOTIVO_SELECCION": motivo,
        "LINK_ALTERNATIVO_1": alt1,
        "LINK_ALTERNATIVO_2": alt2,
    }
