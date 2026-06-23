"""
Buscador de candidatos para Alibaba y Made in China.

Versión MVP 6:
- Mantiene la lógica práctica de la V4: encuentra páginas directas de producto,
  evita páginas de búsqueda/listado y valida precio contra el margen configurado.
- Mejora la referencia del producto usando el título del LINKS ORIGINAL cuando se
  puede leer.
- Si no puede leer el link original, vuelve automáticamente al comportamiento de
  la V4 usando DESCRIPTION NUEVA INGLES.
- No agrega muchas columnas de diagnóstico: solo TITULO_LINK_ORIGINAL para validar
  qué entendió del link original.

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
from html import unescape
from typing import Any
from urllib.parse import quote_plus, urlparse

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

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
    "set", "pcs", "piece", "pieces", "alibaba", "made", "com",
}

# Diccionario simple para que un título leído en español desde Alibaba pueda ayudar
# a buscar/comparar candidatos en inglés. No intenta traducir todo, solo términos de producto.
SINONIMOS = {
    "zapato": ["shoe", "shoes"],
    "zapatos": ["shoe", "shoes"],
    "calzado": ["shoe", "shoes", "footwear"],
    "deportivo": ["sport", "sports", "running", "athletic", "sneaker", "sneakers"],
    "deportivos": ["sport", "sports", "running", "athletic", "sneaker", "sneakers"],
    "tenis": ["sneaker", "sneakers", "tennis", "shoe", "shoes"],
    "tacon": ["heel", "heels"],
    "tacones": ["heel", "heels"],
    "elegante": ["formal", "dress"],
    "elegantes": ["formal", "dress"],
    "sandalia": ["sandal", "sandals"],
    "sandalias": ["sandal", "sandals"],
    "bota": ["boot", "boots"],
    "botas": ["boot", "boots"],
    "pantalon": ["pant", "pants", "trouser", "trousers"],
    "pantalones": ["pant", "pants", "trouser", "trousers"],
    "licra": ["leggings", "legging"],
    "leggins": ["leggings", "legging"],
    "nino": ["child", "children", "kid", "kids", "boy", "boys"],
    "ninos": ["child", "children", "kid", "kids", "boy", "boys"],
    "nina": ["girl", "girls", "child", "children", "kid", "kids"],
    "ninas": ["girl", "girls", "child", "children", "kid", "kids"],
    "bebe": ["baby", "infant", "toddler"],
    "mujer": ["women", "woman", "ladies"],
    "mujeres": ["women", "woman", "ladies"],
    "hombre": ["men", "man"],
    "hombres": ["men", "man"],
    "cargador": ["charger", "adapter", "power", "supply"],
    "bateria": ["battery"],
    "baterias": ["battery", "batteries"],
    "iones": ["ion", "ions"],
    "litio": ["lithium", "li-ion"],
    "bicicleta": ["bike", "bicycle", "e-bike"],
    "electrica": ["electric"],
    "electrico": ["electric"],
    "moto": ["motorcycle", "scooter"],
    "scooter": ["scooter"],
    "corazon": ["heart"],
    "corazones": ["heart", "hearts"],
    "estampado": ["print", "printed", "pattern"],
    "impreso": ["print", "printed"],
    "cintura": ["waist"],
    "elastica": ["elastic"],
    "elastico": ["elastic"],
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
    score_vs_excel: float
    score_vs_original: float
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
            "score_vs_excel": round(self.score_vs_excel, 2),
            "score_vs_original": round(self.score_vs_original, 2),
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


def _limpiar_titulo(titulo: Any) -> str:
    texto = unescape(str(titulo or "")).strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s*[-|]\s*(Alibaba\.com|Made-in-China\.com|Made in China).*$", "", texto, flags=re.IGNORECASE)
    return texto[:350]


def _expandir_con_sinonimos(texto: Any) -> str:
    normal = _normalizar(texto)
    tokens = re.findall(r"[a-z0-9]+(?:[.+\-/][a-z0-9]+)*", normal)
    extras: list[str] = []
    for token in tokens:
        extras.extend(SINONIMOS.get(token, []))
    if extras:
        return f"{normal} {' '.join(extras)}"
    return normal


def _tokens(texto: Any) -> set[str]:
    texto = _expandir_con_sinonimos(texto)
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

    salida: list[float] = []
    for precio in precios:
        if 0 < precio < 100000 and precio not in salida:
            salida.append(precio)
    return salida


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


def _score_texto(producto: str, title: str, snippet: str = "") -> float:
    producto_tokens = _tokens(producto)
    candidato_tokens = _tokens(f"{title} {snippet}")
    if not producto_tokens:
        return 0.0

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


def _detectar_plataforma(link: str) -> str:
    netloc = urlparse(str(link or "")).netloc.lower()
    if "alibaba.com" in netloc:
        return "Alibaba"
    if "made-in-china.com" in netloc:
        return "Made in China"
    return ""


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

    if platform == "Alibaba":
        if "/product-detail/" not in path:
            return False
        return not any(p in path for p in ["/trade/search", "/catalog", "/products"])

    if platform == "Made in China":
        if any(p in url for p in ["products-search", "hot-china-products", "product-list", "company-search", "productdirectory"]):
            return False
        aceptado = (
            "/product-detail" in path
            or "/product/" in path
            or re.search(r"/[^/]*product[^/]*\.html$", path) is not None
            or (".made-in-china.com" in netloc and path.endswith(".html") and "product" in path)
        )
        return bool(aceptado)

    return False


def _hay_conflicto_producto(producto: str, texto_candidato: str) -> str:
    """Detecta contradicciones básicas. No reemplaza a una IA avanzada, pero evita errores obvios."""
    p = _normalizar(producto)
    c = _normalizar(texto_candidato)
    p_tokens = _tokens(p)
    c_tokens = _tokens(c)

    def contiene(tokens: set[str], palabras: set[str]) -> bool:
        return bool(tokens & palabras)

    deportivos = {"sport", "sports", "running", "runner", "athletic", "sneaker", "sneakers", "trainer", "trainers", "tennis"}
    tacones_formal = {"heel", "heels", "pump", "pumps", "stiletto", "elegant", "formal", "dress", "loafer", "loafers", "wedding"}
    if contiene(p_tokens, deportivos) and contiene(c_tokens, tacones_formal):
        return "Conflicto: el producto original parece deportivo y el candidato parece tacón/formal."
    if contiene(p_tokens, tacones_formal) and contiene(c_tokens, deportivos):
        return "Conflicto: el producto original parece formal/tacón y el candidato parece deportivo."

    ninos = {"child", "children", "kid", "kids", "boy", "boys", "girl", "girls", "baby", "toddler", "infant"}
    adultos = {"women", "woman", "men", "man", "adult", "ladies", "lady"}
    if contiene(p_tokens, ninos) and contiene(c_tokens, adultos) and not contiene(c_tokens, ninos):
        return "Conflicto: el producto original es para niños y el candidato parece de adulto."

    pantalones = {"pant", "pants", "trouser", "trousers", "leggings", "legging", "shorts"}
    calzado = {"shoe", "shoes", "sneaker", "sneakers", "heel", "heels", "boot", "boots", "sandal", "sandals", "sock", "socks", "skate", "skates"}
    if contiene(p_tokens, pantalones) and contiene(c_tokens, calzado) and not contiene(c_tokens, pantalones):
        return "Conflicto: el producto original es pantalón/ropa inferior y el candidato parece calzado/accesorio."

    ropa = pantalones | {"shirt", "shirts", "dress", "jacket", "coat", "hoodie", "legging", "leggings"}
    if contiene(p_tokens, calzado) and contiene(c_tokens, ropa) and not contiene(c_tokens, calzado):
        return "Conflicto: el producto original es calzado y el candidato parece ropa."

    for unidad in ["v", "a", "w", "ah", "mah", "hz"]:
        patron = rf"\b(\d+(?:\.\d+)?)\s?{unidad}\b"
        p_vals = set(re.findall(patron, p))
        c_vals = set(re.findall(patron, c))
        if p_vals and c_vals and not (p_vals & c_vals):
            return f"Conflicto: especificación {unidad.upper()} diferente entre producto y candidato."

    return ""


def analizar_link_original(link_original: str, price: Any = None) -> dict[str, Any]:
    """Lee de forma básica el link original y extrae un título.

    Si Alibaba/Made-in-China bloquea o no devuelve título, la app vuelve al modo V4.
    """
    link_original = str(link_original or "").strip()
    if not link_original.startswith(("http://", "https://")):
        return {"title": "", "price": None, "status": "Sin link original válido"}

    if requests is None:
        return {"title": "", "price": None, "status": "No se pudo leer: falta requests"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    try:
        resp = requests.get(link_original, headers=headers, timeout=10, allow_redirects=True)
        status_code = getattr(resp, "status_code", None)
        if status_code and status_code >= 400:
            return {"title": "", "price": None, "status": f"No se pudo leer: HTTP {status_code}"}
        html = resp.text or ""
    except Exception as exc:
        return {"title": "", "price": None, "status": f"No se pudo leer: {exc}"}

    html_sample = html[:400000]
    title = ""
    meta_patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<h1[^>]*>(.*?)</h1>',
        r'<title[^>]*>(.*?)</title>',
    ]
    for patron in meta_patterns:
        match = re.search(patron, html_sample, flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = _limpiar_titulo(re.sub(r"<[^>]+>", " ", match.group(1)))
            if title:
                break

    text_for_price = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_sample, flags=re.IGNORECASE | re.DOTALL)
    text_for_price = re.sub(r"<[^>]+>", " ", text_for_price)
    text_for_price = unescape(re.sub(r"\s+", " ", text_for_price))[:50000]
    precios = _extraer_precios(text_for_price)
    precio = _seleccionar_precio_mas_cercano(precios, price)

    return {
        "title": title,
        "price": precio,
        "status": "Leído correctamente" if title else "Link leído, pero sin título claro",
    }


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


def _tokens_para_query(texto: str, limite: int = 10) -> str:
    # Specs primero porque son críticas: 72V, 5A, modelos, tallas, etc.
    specs = list(_tokens_especificaciones(texto))
    tokens = list(_tokens(texto))
    ordenados: list[str] = []
    for token in specs + tokens:
        if token not in ordenados:
            ordenados.append(token)
    return " ".join(ordenados[:limite])


def _construir_queries(producto_excel: str, titulo_original: str, platform: str) -> list[str]:
    excel = str(producto_excel or "").strip()
    original = str(titulo_original or "").strip()
    excel_simple = _tokens_para_query(excel, limite=8) or excel
    original_simple = _tokens_para_query(original, limite=10) or original
    combinado_simple = _tokens_para_query(f"{original} {excel}", limite=12) or excel_simple

    queries: list[str] = []
    if platform == "Alibaba":
        if original:
            queries.append(f'site:alibaba.com/product-detail "{original}"')
            queries.append(f'site:alibaba.com/product-detail {original_simple}')
        # Fallback tipo V4 para que no se quede sin resultados.
        if excel:
            queries.append(f'site:alibaba.com/product-detail "{excel}"')
            queries.append(f'site:alibaba.com/product-detail {excel_simple}')
        if combinado_simple and combinado_simple not in [excel_simple, original_simple]:
            queries.append(f'site:alibaba.com/product-detail {combinado_simple}')
    elif platform == "Made in China":
        if original:
            queries.append(f'site:made-in-china.com "{original}" product')
            queries.append(f'site:made-in-china.com {original_simple} product')
        if excel:
            queries.append(f'site:made-in-china.com "{excel}" product')
            queries.append(f'site:made-in-china.com {excel_simple} product')
        if combinado_simple and combinado_simple not in [excel_simple, original_simple]:
            queries.append(f'site:made-in-china.com {combinado_simple} product')
    else:
        queries.append(original or excel)

    salida: list[str] = []
    for q in queries:
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in salida:
            salida.append(q)
    return salida


def generar_url_busqueda(producto_ingles: str, platform: str) -> str:
    q = quote_plus(str(producto_ingles or "").strip())
    return PLATFORM_CONFIG[platform]["fallback_search_url"].format(q=q)


def buscar_candidatos(
    producto_ingles: str,
    total_unit: int | float | str,
    price: float | str,
    link_original: str = "",
    usar_titulo_original: bool = True,
    usar_made_in_china: bool = True,
    max_por_fuente: int = 8,
    pausa_segundos: float = 0.35,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Busca candidatos web y devuelve páginas de producto directo ordenadas por score."""
    original_info = analizar_link_original(link_original, price=price) if usar_titulo_original else {"title": "", "price": None, "status": "No usado"}
    titulo_original = str(original_info.get("title") or "").strip()

    plataformas = ["Alibaba"] + (["Made in China"] if usar_made_in_china else [])
    candidatos: list[Candidate] = []
    vistos: set[str] = set()

    for platform in plataformas:
        for query in _construir_queries(producto_ingles, titulo_original, platform):
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

                # Mantener filtros anti-error de la V4, pero también validar contra título original si existe.
                conflicto_excel = _hay_conflicto_producto(producto_ingles, texto_candidato)
                conflicto_original = _hay_conflicto_producto(titulo_original, texto_candidato) if titulo_original else ""
                if conflicto_excel or conflicto_original:
                    continue

                precios = _extraer_precios(texto_candidato)
                precio_detectado = _seleccionar_precio_mas_cercano(precios, price)
                diferencia = _diferencia_porcentual(price, precio_detectado)

                score_vs_excel = _score_texto(producto_ingles, title, snippet)
                score_vs_original = _score_texto(titulo_original, title, snippet) if titulo_original else 0.0

                if titulo_original:
                    # El título original pesa más, pero no bloquea totalmente al Excel si no hay buena lectura/traducción.
                    score_producto = max(
                        (score_vs_original * 0.65) + (score_vs_excel * 0.35),
                        score_vs_excel * 0.88,
                    )
                else:
                    score_producto = score_vs_excel

                score_total = _score_final(score_producto, diferencia)

                candidatos.append(
                    Candidate(
                        title=title,
                        link=link,
                        snippet=snippet,
                        platform=platform,
                        precio_detectado=precio_detectado,
                        score_producto=score_producto,
                        score_vs_excel=score_vs_excel,
                        score_vs_original=score_vs_original,
                        diferencia_precio=diferencia,
                        score_final=score_total,
                    )
                )

            time.sleep(pausa_segundos)

    candidatos.sort(key=lambda c: c.score_final, reverse=True)
    return [c.to_dict() for c in candidatos], original_info


def _url_referencia_compuesta(referencia: str, usar_made_in_china: bool) -> str:
    urls = [generar_url_busqueda(referencia, "Alibaba")]
    if usar_made_in_china:
        urls.append(generar_url_busqueda(referencia, "Made in China"))
    return " | ".join(urls)


def _precio_dentro_margen(diferencia: Any, margen_precio: float) -> bool:
    try:
        return abs(float(diferencia)) <= float(margen_precio)
    except (TypeError, ValueError):
        return False


def _tiene_precio_fuera_margen(candidato: dict[str, Any], margen_precio: float) -> bool:
    precio = candidato.get("precio_detectado")
    diferencia = candidato.get("diferencia_precio")
    if precio in [None, ""] or diferencia in [None, ""]:
        return False
    return not _precio_dentro_margen(diferencia, margen_precio)


def _primer_candidato_recomendable(candidatos: list[dict[str, Any]], margen_precio: float) -> dict[str, Any] | None:
    """
    Devuelve un candidato que realmente pueda ir en LINK_RECOMENDADO.

    Reglas:
    - Debe tener buena coincidencia de producto.
    - Si tiene precio detectado, debe estar dentro del margen configurado.
    - Si no tiene precio detectado, puede recomendarse como media para revisión.
    """
    for candidato in candidatos:
        score_producto = float(candidato.get("score_producto") or 0)
        precio = candidato.get("precio_detectado")
        diferencia = candidato.get("diferencia_precio")

        if score_producto < 70:
            continue

        if precio not in [None, ""] and diferencia not in [None, ""]:
            if _precio_dentro_margen(diferencia, margen_precio):
                return candidato
            continue

        return candidato

    return None


def construir_resultado_para_excel(
    producto_ingles: str,
    total_unit: int | float | str,
    price: float | str,
    link_original: str = "",
    usar_titulo_original: bool = True,
    usar_made_in_china: bool = True,
    margen_precio: float = 20,
) -> dict[str, Any]:
    """Devuelve una fila lista para rellenar columnas nuevas del Excel."""
    candidatos, original_info = buscar_candidatos(
        producto_ingles=producto_ingles,
        total_unit=total_unit,
        price=price,
        link_original=link_original,
        usar_titulo_original=usar_titulo_original,
        usar_made_in_china=usar_made_in_china,
    )

    titulo_original = str(original_info.get("title") or "").strip()
    referencia_busqueda = titulo_original or producto_ingles

    if not candidatos:
        return {
            "TITULO_LINK_ORIGINAL": titulo_original,
            "LINK_RECOMENDADO": "",
            "PLATAFORMA_RESULTADO": "",
            "PRECIO_ENCONTRADO": "",
            "COINCIDENCIA_PRODUCTO": "Baja",
            "MOTIVO_SELECCION": "No se encontró una página directa de producto. Se mantiene la búsqueda de referencia como apoyo manual.",
            "LINK_ALTERNATIVO_1": "",
            "LINK_ALTERNATIVO_2": "",
            "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(referencia_busqueda, usar_made_in_china),
        }

    mejor_global = candidatos[0]
    recomendado = _primer_candidato_recomendable(candidatos, margen_precio)

    enlaces_alternativos = []
    for candidato in candidatos:
        link = candidato.get("link", "")
        if link and link not in enlaces_alternativos:
            if recomendado is None or link != recomendado.get("link", ""):
                enlaces_alternativos.append(link)
        if len(enlaces_alternativos) >= 2:
            break

    alt1 = enlaces_alternativos[0] if len(enlaces_alternativos) > 0 else ""
    alt2 = enlaces_alternativos[1] if len(enlaces_alternativos) > 1 else ""

    if recomendado is None:
        precio_mejor = mejor_global.get("precio_detectado")
        diferencia_mejor = mejor_global.get("diferencia_precio")
        score_mejor = float(mejor_global.get("score_producto") or 0)

        if _tiene_precio_fuera_margen(mejor_global, margen_precio):
            motivo = (
                f"Se encontraron productos directos, pero el mejor precio detectado "
                f"está fuera del margen ±{margen_precio}%. "
                f"Precio detectado: {precio_mejor}; diferencia: {round(float(diferencia_mejor), 2)}%. "
                "Se deja como alternativa, no como link recomendado."
            )
            coincidencia = "Baja"
        elif score_mejor < 70:
            motivo = "Se encontraron páginas directas, pero la coincidencia del producto fue insuficiente. Revisar alternativas manualmente."
            coincidencia = "Baja"
        else:
            motivo = "Se encontraron candidatos, pero ninguno cumple simultáneamente producto y precio. Revisar alternativas manualmente."
            coincidencia = "Baja"

        return {
            "TITULO_LINK_ORIGINAL": titulo_original,
            "LINK_RECOMENDADO": "",
            "PLATAFORMA_RESULTADO": "",
            "PRECIO_ENCONTRADO": "" if precio_mejor in [None, ""] else precio_mejor,
            "COINCIDENCIA_PRODUCTO": coincidencia,
            "MOTIVO_SELECCION": motivo,
            "LINK_ALTERNATIVO_1": mejor_global.get("link", ""),
            "LINK_ALTERNATIVO_2": alt1 if alt1 != mejor_global.get("link", "") else alt2,
            "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(referencia_busqueda, usar_made_in_china),
        }

    score_producto = float(recomendado.get("score_producto") or 0)
    score_original = float(recomendado.get("score_vs_original") or 0)
    diferencia = recomendado.get("diferencia_precio")
    precio = recomendado.get("precio_detectado")

    if precio not in [None, ""] and diferencia not in [None, ""] and _precio_dentro_margen(diferencia, margen_precio):
        coincidencia = "Alta"
        motivo = f"Página directa de producto, similitud suficiente y precio dentro del margen ±{margen_precio}%."
    elif score_producto >= 70 and precio in [None, ""]:
        coincidencia = "Media"
        motivo = "Página directa de producto con similitud suficiente, pero no se pudo detectar precio. Revisar precio por cantidad antes de aprobar."
    else:
        coincidencia = "Media"
        motivo = "Página directa de producto posiblemente compatible. Revisar precio, cantidad y especificaciones."

    if titulo_original:
        motivo += f" Referencia usada: título del link original. Coincidencia con título original: {round(score_original, 2)}%."
    else:
        motivo += " Referencia usada: DESCRIPTION NUEVA INGLES, porque no se pudo leer título claro del link original."

    return {
        "TITULO_LINK_ORIGINAL": titulo_original,
        "LINK_RECOMENDADO": recomendado.get("link", ""),
        "PLATAFORMA_RESULTADO": recomendado.get("platform", ""),
        "PRECIO_ENCONTRADO": "" if precio in [None, ""] else precio,
        "COINCIDENCIA_PRODUCTO": coincidencia,
        "MOTIVO_SELECCION": motivo,
        "LINK_ALTERNATIVO_1": alt1,
        "LINK_ALTERNATIVO_2": alt2,
        "URL_BUSQUEDA_REFERENCIA": _url_referencia_compuesta(referencia_busqueda, usar_made_in_china),
    }
