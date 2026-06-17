import pandas as pd

COLUMNAS_NUEVAS = [
    "LINK_RECOMENDADO",
    "PLATAFORMA_RESULTADO",
    "PRECIO_ENCONTRADO",
    "DIFERENCIA_PRECIO",
    "COINCIDENCIA_PRODUCTO",
    "MOTIVO_SELECCION",
    "LINK_ALTERNATIVO_1",
    "LINK_ALTERNATIVO_2",
    "ESTADO_REVISION",
    "APROBADO_POR_USUARIO",
    "FECHA_REVISION",
]


def validar_columnas(df: pd.DataFrame, columnas_obligatorias: list[str]) -> list[str]:
    """Devuelve las columnas obligatorias que no existen en el Excel."""
    columnas_actuales = [str(col).strip() for col in df.columns]
    return [col for col in columnas_obligatorias if col not in columnas_actuales]


def preparar_dataframe_resultados(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas nuevas sin reemplazar las columnas originales."""
    resultado = df.copy()
    for columna in COLUMNAS_NUEVAS:
        if columna not in resultado.columns:
            resultado[columna] = ""

    resultado["ESTADO_REVISION"] = "Pendiente"
    resultado["MOTIVO_SELECCION"] = "Pendiente de conectar buscador real"
    return resultado
