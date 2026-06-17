"""
Buscador de candidatos para Alibaba y Made in China.

Versión MVP 3:
- Busca candidatos usando resultados web de DuckDuckGo/DDGS.
- NO coloca páginas de búsqueda/listados como link recomendado.
- Solo acepta URLs que parezcan páginas de producto directo.
- Aplica filtros básicos para evitar recomendaciones claramente equivocadas
  (por ejemplo: zapatos deportivos vs tacones).
- Si no hay un producto directo confiable, deja LINK_RECOMENDADO vacío y coloca
  la búsqueda en URL_BUSQUEDA_REFERENCIA para revisión manual.

IMPORTANTE:
Esta capa sirve para validar el flujo con 20 productos. Para una versión robusta
se recomienda reemplazar la búsqueda por API/servicio de datos autorizado o un
proveedor de extracción que entregue datos estructurados de producto.
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
    from ddgs import DDGS
except Exception:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS
    except Exception:  # pragma: no cover
        DDGS = None


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "are", "was", "were",
    "product", "products", "factory", "supplier", "suppliers", "manufacturer",
    "manufacturers", "china", "chinese", "wholesale", "custom", "new", "hot",
    "sale", "high", "quality", "best", "cheap", "price", "buy", "online",
    "de", "la", "el", "los", "las", "para", "con", "por", "del", "un", "una",
    "set", "pcs", "piece", "pieces",
}

PLATFORM_CONFIG = {
    "Alibaba": {
        "domains": ["alibaba.com"],
        "fallback_search_url": "https://www.alibaba.com/trade/search?SearchText={q}",
    },
    "Made in China": {
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
    motivo_filtro: str = ""

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
            "motivo_filtro": self.motivo_filtro,
        }


def _normalizar(texto: Any) -> str:
    if texto is None:
        return ""
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("&", " and ")
    texto = re.sub(r"[^a-z0-9.+\-/\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _tokens(texto: Any) -> set[str]:
    texto = _normalizar(texto)
    raw_tokens = re.findall(r"[a-z0-9]+(?:[.+\-/][a-z0-9]+)*", texto)
    return {t for t in raw_tokens if len(t) >= 2 and t not in STOPWORDS}


def _tokens_especificaciones(texto: Any) -> set[str]:
    texto = _normalizar(texto)
    patrones = [
        r"\b\d+(?:\.\d+)?\s?(?:v|w|a|ah|mah|hz|kg|g|mm|cm|m|l|ml|oz|inch|in|gb|tb)\b",
        r"\b\d+(?:\.\d+)?\s?[x×*]\s?\d+(?:\.\d+)?(?:\s?[x×*]\s?\d+(?:\.\d+)?)?\b",
        r"\b[a-z]{1,8}\d{1,8}[a-z0-9\-/]*\b",
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
    if not texto:
        return []

    patron = re.compile(r"(?:US\$|USD|\$)\s*([0-9]{1,6}(?:[.,][0-9]{1,4})?)", flags=re.IGNORECASE)
    precios: list[float] = []
    for match in patron.findall(texto):
        try:
            precios.append(float(match.replace(",", "")))
        except ValueError:
            pass

    patron_fob = re.compile(r"(?:price|precio|fob)\D{0,20}([0-9]{1,6}(?:[.,][0-9]{1,4})?)", flags=re.IGNORECASE)
    for match in patron_fob.findall(texto):
        try:
            precios.append(float(match.replace(",", "")))
        except ValueError:
            pass

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

    # Tokens principales: los tokens del producto deben aparecer en el candidato.
    overlap = len(producto_tokens & candidato_tokens) / max(len(producto_tokens), 1)

    producto_specs = _tokens_especificaciones(producto)
    candidato_specs = _tokens_especificaciones(f"{title} {snippet}")
    spec_overlap = len(producto_specs & candidato_specs) / max(len(producto_specs), 1) if producto_specs else 0.0

    score = (overlap * 78) + (spec_overlap * 22)
    return min(score, 100.0)


def _score_final(score_producto: float, diferencia_precio: float | None) -> float:
    if diferencia_precio is None:
        return score_producto * 0.82
    diferencia_abs = abs(diferencia_precio)
    score_precio = max(0.0, 100.0 - min(diferencia_abs, 100.0))
    return (score_producto * 0.72) + (score_precio * 0.28)


def _link_pertenece_a_plataforma(link: str, platform: str) -> bool:
    if not link:
        return False
    netloc = urlparse(link).netloc.lower()
    return any(domain in netloc for domain in PLATFORM_CONFIG[platform]["domains"])


def _es_url_producto_valida(link: str, platform: str) -> bool:
    """Evita que se guarden páginas de búsqueda/listado como link recomendado."""
    if not _link_pertenece_a_plataforma(link, platform):
        return False

    parsed = urlparse(link)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    url = f"{netloc}{path}".lower()

    # Rechazos comunes de páginas de búsqueda/listado/categoría.
    patrones_rechazo = [
        "/trade/search", "/products", "/showroom/", "/catalog", "/category", "/supplier",
        "products-search", "product-list", "company-search", "offer-list", "search",
        "hot-china-products", "productdirectory",
    ]

    if platform == "Alibaba":
        if "/product-detail/" not in path:
            return False
        # Si por alguna razón viene mezclado con búsqueda, rechazar.
        return not any(p in path for p in ["/trade/search", "/catalog", "/products"])

    if platform == "Made in China":
        if any(p in url for p in ["products-search", "hot-china-products", "product-list", "company-search", "productdirectory"]):
            return False
        # Made-in-China usa varias estructuras para páginas de producto.
        aceptado = (
            "/product-detail" in path
            or "/product/" in path
            or re.search(r"/[^/]*product[^/]*\.html$", path) is not None
            or (".made-in-china.com" in netloc and path.endswith(".html") and "product" in path)
        )
        return bool(aceptado)

    return not any(p in url for p in patrones_rechazo)


def _hay_conflicto_producto(producto: str, texto_candidato: str) -> str:
    """Detecta contradicciones básicas. No reemplaza a una IA avanzada, pero evita errores obvios."""
    p = _normalizar(producto)
    c = _normalizar(texto_candidato)
    p_tokens = _tokens(p)
    c_tokens = _tokens(c)

    def contiene(tokens: set[str], palabras: set[str]) -> bool:
        return bool(tokens & palabras)

    # Zapatos deportivos no deben recomendar tacones/formales.
    deportivos = {"sport", "sports", "running", "runner", "athletic", "sneaker", "sneakers", "trainer", "trainers", "tennis"}
    tacones_formal = {"heel", "heels", "pump", "pumps", "stiletto", "elegant", "formal", "dress", "loafer", "loafers", "wedding"}
    if contiene(p_tokens, deportivos) and contiene(c_tokens, tacones_formal):
        return "Conflicto: el producto original parece deportivo y el candidato parece tacón/formal."

    # Tacones/formales no deben recomendar deportivos.
    if contiene(p_tokens, tacones_formal) and contiene(c_tokens, deportivos):
        return "Conflicto: el producto original parece formal/tacón y el candidato parece deportivo."

    # Niños vs adultos/mujer/hombre cuando el producto especifica niños.
    ninos = {"child", "children", "kid", "kids", "boy", "boys", "girl", "girls", "baby", "toddler", "infant"}
    adultos = {"women", "woman", "men", "man", "adult", "ladies", "lady"}
    if contiene(p_tokens, ninos) and contiene(c_tokens, adultos) and not contiene(c_tokens, ninos):
        return "Conflicto: el producto original es para niños y el candidato parece de adulto."

    # Pantalones no deben recomendar zapatos, calcetines, patines, etc.
    pantalones = {"pant", "pants", "trouser", "trousers", "leggings", "legging", "shorts"}
    calzado = {"shoe", "shoes", "sneaker", "sneakers", "heel", "heels", "boot", "boots", "sandal", "sandals", "sock", "socks", "skate", "skates"}
    if contiene(p_tokens, pantalones) and contiene(c_tokens, calzado) and not contiene(c_tokens, pantalones):
        return "Conflicto: el producto original es pantalón/ropa inferior y el candidato parece calzado/accesorio."

    # Calzado no debe recomendar ropa.
    ropa_inferior = pantalones | {"shirt", "shirts", "dress", "jacket", "coat", "hoodie", "legging", "leggings"}
    if contiene(p_tokens, calzado) and contiene(c_tokens, ropa_inferior) and not contiene(c_tokens, calzado):
        return "Conflicto: el producto original es calzado y el candidato parece ropa."

    # Especificaciones técnicas: si el producto trae voltaje/amperaje y el candidato trae otro diferente, penalizar.
    for unidad in ["v", "a", "w", "ah", "mah", "hz"]:
        patron = rf"\b(\d+(?:\.\d+)?)\s?{unidad}\b"
        p_vals = set(re.findall(patron, p))
        c_vals = set(re.findall(patron, c))
        if p_vals and c_vals and not (p_vals & c_vals):
            return f"Conflicto: especificación {unidad.upper()} diferente entre producto y candidato."

    return ""


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


def _construir_queries(producto_ingles: str, platform: str) -> list[str]:
    producto = str(producto_ingles or "").strip()
    producto_simple = " ".join(list(_tokens(producto))[:8]) or producto

    if platform == "Alibaba":
        return [
            f'site:alibaba.com/product-detail "{producto}"',
            f'site:alibaba.com/product-detail {producto_simple}',
        ]
    if platform == "Made in China":
        return [
            f'site:made-in-china.com "{producto}" "product-detail"',
            f'site:made-in-china.com {producto_simple} product-detail',
        ]
    return [producto]


def generar_url_busqueda(producto_ingles: str, platform: str) -> str:
    q = quote_plus(str(producto_ingles or "").strip())
    return PLATFORM_CONFIG[platform]["fallback_search_url"].format(q=q)


def buscar_candidatos(
    producto_ingles: str,
    total_unit: int | float | str,
    price: float | str,
    usar_made_in_china: bool = True,
    max_por_fuente: int = 8,
    pausa_segundos: float = 0.35,
) -> list[dict[str, Any]]:
    """Busca candidatos web y devuelve solo páginas de producto directo ordenadas por score."""
    plataformas = ["Alibaba"] + (["Made in China"] if usar_made_in_china else [])
    candidatos: list[Candidate] = []
    vistos: set[str] = set()

    for platform in plataformas:
        for query in _construir_queries(producto_ingles, platform):
            resultados = _buscar_web(query, max_results=max_por_fuente)

            for resultado in resultados:
                link = resultado.get("link", "")
                if link in vistos:
                    continue
                vistos.add(link)

                if not _es_url_producto_valida(link, platform):
                    continue

                title = resultado.get("title", "")
                snippet = resultado.get("snippet", "")
                texto_candidato = f"{title} {snippet}"
                conflicto = _hay_conflicto_producto(producto_ingles, texto_candidato)
                if conflicto:
                    # No se recomienda, pero tampoco se guarda como candidato para evitar aprobaciones erróneas.
                    continue

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


def _url_referencia_compuesta(producto_ingles: str, usar_made_in_china: bool) -> str:
    urls = [generar_url_busqueda(producto_ingles, "Alibaba")]
    if usar_made_in_china:
        urls.append(generar_url_busqueda(producto_ingles, "Made in China"))
    return " | ".join(urls)


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
            "LINK_RECOMENDADO": "",
            "PLATAFORMA_RESULTADO": "",
            "PRECIO_ENCONTRADO": "",
            "COINCIDENCIA_PRODUCTO": "Baja",
            "MOTIVO_SELECCION": "No se encontró una página directa de producto. La URL de búsqueda queda solo como referencia, no como recomendación.",
            "LINK_ALTERNATIVO_1": "",
            "LINK_ALTERNATIVO_2": "",
            "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(producto_ingles, usar_made_in_china),
        }

    # Si el mejor candidato es demasiado débil, NO lo ponemos como recomendado.
    mejor = candidatos[0]
    score_producto = float(mejor.get("score_producto") or 0)
    diferencia = mejor.get("diferencia_precio")
    precio = mejor.get("precio_detectado")

    if score_producto < 55:
        return {
            "LINK_RECOMENDADO": "",
            "PLATAFORMA_RESULTADO": "",
            "PRECIO_ENCONTRADO": "",
            "COINCIDENCIA_PRODUCTO": "Baja",
            "MOTIVO_SELECCION": "Se encontraron páginas directas, pero la coincidencia del producto fue baja. Revisar alternativas manualmente.",
            "LINK_ALTERNATIVO_1": mejor.get("link", ""),
            "LINK_ALTERNATIVO_2": candidatos[1]["link"] if len(candidatos) > 1 else "",
            "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(producto_ingles, usar_made_in_china),
        }

    alt1 = candidatos[1]["link"] if len(candidatos) > 1 else ""
    alt2 = candidatos[2]["link"] if len(candidatos) > 2 else ""

    if score_producto >= 75 and diferencia is not None and abs(float(diferencia)) <= 20:
        coincidencia = "Alta"
        motivo = "Página directa de producto, alta similitud y precio dentro del margen ±20%."
    elif score_producto >= 75 and precio is None:
        coincidencia = "Media"
        motivo = "Página directa de producto con alta similitud, pero no se pudo detectar precio. Revisar precio por cantidad."
    elif score_producto >= 60:
        coincidencia = "Media"
        motivo = "Página directa de producto posiblemente compatible. Revisar precio, cantidad y especificaciones."
    else:
        coincidencia = "Baja"
        motivo = "Página directa encontrada, pero la coincidencia es baja. Revisar antes de aprobar."

    return {
        "LINK_RECOMENDADO": mejor.get("link", ""),
        "PLATAFORMA_RESULTADO": mejor.get("platform", ""),
        "PRECIO_ENCONTRADO": "" if precio is None else precio,
        "COINCIDENCIA_PRODUCTO": coincidencia,
        "MOTIVO_SELECCION": motivo,
        "LINK_ALTERNATIVO_1": alt1,
        "LINK_ALTERNATIVO_2": alt2,
        "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(producto_ingles, usar_made_in_china),
    }
