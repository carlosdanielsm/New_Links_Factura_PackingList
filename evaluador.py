import math
from typing import Any


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        number = float(value)
        if math.isnan(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def calcular_diferencia_porcentual(precio_objetivo: Any, precio_encontrado: Any) -> float | str:
    """Calcula la diferencia porcentual contra PRICE."""
    objetivo = _to_float(precio_objetivo)
    encontrado = _to_float(precio_encontrado)

    if objetivo is None or encontrado is None or objetivo == 0:
        return ""

    return round(((encontrado - objetivo) / objetivo) * 100, 2)


def determinar_estado(coincidencia: Any, diferencia_porcentual: Any, margen: float, link: Any) -> str:
    """Determina el estado de revisión según coincidencia, precio y existencia de link."""
    link_valido = isinstance(link, str) and link.strip().startswith(("http://", "https://"))
    if not link_valido:
        return "Pendiente"

    coincidencia_texto = str(coincidencia or "").strip().lower()
    try:
        diferencia = abs(float(diferencia_porcentual))
    except (TypeError, ValueError):
        diferencia = None

    if coincidencia_texto == "alta" and diferencia is not None and diferencia <= margen:
        return "Alta coincidencia"
    if coincidencia_texto in ["alta", "media"]:
        return "Media coincidencia"
    if coincidencia_texto == "baja":
        return "Baja coincidencia"
    return "Revisar manualmente"
