from datetime import datetime

import pandas as pd
import streamlit as st

from procesador_excel import validar_columnas, preparar_dataframe_resultados
from evaluador import calcular_diferencia_porcentual, determinar_estado
from exportador_excel import generar_excel_bytes
from buscador_links import construir_resultado_para_excel

st.set_page_config(
    page_title="Buscador IA de Links de Productos",
    page_icon="🔎",
    layout="wide",
)

COLUMNAS_OBLIGATORIAS = [
    "DESCRIPTION NUEVA ESPAÑOL",
    "DESCRIPTION NUEVA INGLES",
    "TOTAL UNIT",
    "PRICE",
    "LINKS ORIGINAL",
]

st.title("🔎 Buscador IA de Links de Productos")
st.caption("MVP interno: carga Excel, busca páginas directas de producto, revisa resultados, aprueba links y exporta un Excel final.")

with st.sidebar:
    st.header("Configuración")
    modo_procesamiento = st.radio(
        "Cantidad a procesar",
        ["Primeros 20 productos", "Todos los productos"],
        index=0,
    )
    margen_precio = st.slider(
        "Margen para alta coincidencia",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
        help="Si el precio encontrado está dentro de este margen y el producto coincide, se marca como alta coincidencia.",
    )
    usar_made_in_china = st.checkbox(
        "Usar Made in China como respaldo",
        value=True,
        help="Primero busca en Alibaba. Si no hay buen resultado, también trae candidatos desde Made in China.",
    )
    st.info(
        "Esta versión usa búsqueda web de candidatos y filtra páginas de búsqueda/listado. No evade CAPTCHA ni hace scraping agresivo. "
        "Si no detecta página directa o precio, deja el producto para revisión."
    )

archivo = st.file_uploader("Subir Excel", type=["xlsx"])

if archivo is None:
    st.warning("Sube un archivo Excel para iniciar.")
    st.stop()

try:
    df_original = pd.read_excel(archivo)
except Exception as exc:
    st.error(f"No se pudo leer el Excel: {exc}")
    st.stop()

faltantes = validar_columnas(df_original, COLUMNAS_OBLIGATORIAS)
if faltantes:
    st.error("El archivo no contiene todas las columnas obligatorias.")
    st.write("Columnas faltantes:", faltantes)
    st.write("Columnas detectadas:", list(df_original.columns))
    st.stop()

limite = 20 if modo_procesamiento == "Primeros 20 productos" else len(df_original)
df_base = df_original.head(limite).copy()

if (
    "df_resultados" not in st.session_state
    or st.session_state.get("archivo_nombre") != archivo.name
    or st.session_state.get("limite") != limite
):
    st.session_state.df_resultados = preparar_dataframe_resultados(df_base)
    st.session_state.archivo_nombre = archivo.name
    st.session_state.limite = limite

st.subheader("Productos cargados")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Productos en archivo", len(df_original))
col2.metric("Productos en esta prueba", len(st.session_state.df_resultados))
col3.metric("Margen alta coincidencia", f"±{margen_precio}%")
col4.metric("Aprobados", int(st.session_state.df_resultados["APROBADO_POR_USUARIO"].eq("Sí").sum()))

st.divider()

st.subheader("Búsqueda automática")
st.write(
    "Primero prueba con los 20 productos. El sistema buscará páginas directas de producto. Las páginas de búsqueda/listado no se guardan como recomendación."
)

busq1, busq2 = st.columns([1, 3])
with busq1:
    ejecutar_busqueda = st.button("Buscar links automáticamente", use_container_width=True)
with busq2:
    st.warning(
        "Para 600 productos puede demorar. Si solo se encuentra una página de búsqueda, el link recomendado quedará vacío y se enviará a revisión.",
        icon="⚠️",
    )

if ejecutar_busqueda:
    df = st.session_state.df_resultados.copy()
    total = len(df)
    progress = st.progress(0)
    status = st.empty()

    for pos, idx in enumerate(df.index, start=1):
        producto = df.at[idx, "DESCRIPTION NUEVA INGLES"]
        total_unit = df.at[idx, "TOTAL UNIT"]
        price = df.at[idx, "PRICE"]

        status.write(f"Buscando {pos}/{total}: {producto}")
        try:
            resultado = construir_resultado_para_excel(
                producto_ingles=producto,
                total_unit=total_unit,
                price=price,
                usar_made_in_china=usar_made_in_china,
            )
            for columna, valor in resultado.items():
                df.at[idx, columna] = valor

            diferencia = calcular_diferencia_porcentual(df.at[idx, "PRICE"], df.at[idx, "PRECIO_ENCONTRADO"])
            df.at[idx, "DIFERENCIA_PRECIO"] = diferencia
            df.at[idx, "ESTADO_REVISION"] = determinar_estado(
                coincidencia=df.at[idx, "COINCIDENCIA_PRODUCTO"],
                diferencia_porcentual=diferencia,
                margen=margen_precio,
                link=df.at[idx, "LINK_RECOMENDADO"],
            )
        except Exception as exc:
            df.at[idx, "ESTADO_REVISION"] = "No encontrado"
            df.at[idx, "MOTIVO_SELECCION"] = f"Error en búsqueda: {exc}"

        progress.progress(pos / total)

    st.session_state.df_resultados = df
    status.empty()
    st.success("Búsqueda terminada. Revisa la tabla antes de exportar.")

st.divider()

st.subheader("Acciones")
accion1, accion2, accion3 = st.columns([1, 1, 2])

with accion1:
    if st.button("Aprobar todos los de alta coincidencia", use_container_width=True):
        df = st.session_state.df_resultados.copy()
        mascara = df["ESTADO_REVISION"].eq("Alta coincidencia")
        df.loc[mascara, "APROBADO_POR_USUARIO"] = "Sí"
        df.loc[mascara, "FECHA_REVISION"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.df_resultados = df
        st.success(f"Se aprobaron {int(mascara.sum())} productos de alta coincidencia.")

with accion2:
    if st.button("Limpiar aprobaciones", use_container_width=True):
        df = st.session_state.df_resultados.copy()
        df["APROBADO_POR_USUARIO"] = ""
        df["FECHA_REVISION"] = ""
        st.session_state.df_resultados = df
        st.success("Aprobaciones limpiadas.")

with accion3:
    st.write("También puedes editar manualmente cualquier campo antes de descargar el Excel final.")

st.divider()

st.subheader("Tabla de revisión")
st.write(
    "Edita `LINK_RECOMENDADO`, `PRECIO_ENCONTRADO`, `COINCIDENCIA_PRODUCTO` y `APROBADO_POR_USUARIO` según corresponda. No apruebes URLs de búsqueda/listado. "
    "El sistema recalculará diferencia y estado."
)

columnas_visibles = [
    "DESCRIPTION NUEVA ESPAÑOL",
    "DESCRIPTION NUEVA INGLES",
    "TOTAL UNIT",
    "PRICE",
    "LINKS ORIGINAL",
    "LINK_RECOMENDADO",
    "PLATAFORMA_RESULTADO",
    "PRECIO_ENCONTRADO",
    "DIFERENCIA_PRECIO",
    "COINCIDENCIA_PRODUCTO",
    "MOTIVO_SELECCION",
    "LINK_ALTERNATIVO_1",
    "LINK_ALTERNATIVO_2",
    "URL_BUSQUEDA_REFERENCIA",
    "ESTADO_REVISION",
    "APROBADO_POR_USUARIO",
    "FECHA_REVISION",
]

edited_df = st.data_editor(
    st.session_state.df_resultados[columnas_visibles],
    use_container_width=True,
    num_rows="fixed",
    height=560,
    column_config={
        "APROBADO_POR_USUARIO": st.column_config.SelectboxColumn(
            "APROBADO_POR_USUARIO",
            options=["", "Sí", "No"],
        ),
        "COINCIDENCIA_PRODUCTO": st.column_config.SelectboxColumn(
            "COINCIDENCIA_PRODUCTO",
            options=["", "Alta", "Media", "Baja"],
        ),
        "PLATAFORMA_RESULTADO": st.column_config.SelectboxColumn(
            "PLATAFORMA_RESULTADO",
            options=["", "Alibaba", "Made in China", "Manual"],
        ),
        "PRECIO_ENCONTRADO": st.column_config.NumberColumn(
            "PRECIO_ENCONTRADO",
            min_value=0.0,
            step=0.01,
            format="%.2f",
        ),
        "PRICE": st.column_config.NumberColumn(
            "PRICE",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            disabled=True,
        ),
        "TOTAL UNIT": st.column_config.NumberColumn(
            "TOTAL UNIT",
            min_value=0,
            step=1,
            disabled=True,
        ),
        "LINKS ORIGINAL": st.column_config.LinkColumn("LINKS ORIGINAL"),
        "LINK_RECOMENDADO": st.column_config.LinkColumn("LINK_RECOMENDADO"),
        "LINK_ALTERNATIVO_1": st.column_config.LinkColumn("LINK_ALTERNATIVO_1"),
        "LINK_ALTERNATIVO_2": st.column_config.LinkColumn("LINK_ALTERNATIVO_2"),
        "URL_BUSQUEDA_REFERENCIA": st.column_config.TextColumn("URL_BUSQUEDA_REFERENCIA"),
    },
)

# Recalcular diferencia, estado y fecha de revisión.
df_recalculado = edited_df.copy()
for idx, row in df_recalculado.iterrows():
    diferencia = calcular_diferencia_porcentual(row.get("PRICE"), row.get("PRECIO_ENCONTRADO"))
    df_recalculado.at[idx, "DIFERENCIA_PRECIO"] = diferencia
    df_recalculado.at[idx, "ESTADO_REVISION"] = determinar_estado(
        coincidencia=row.get("COINCIDENCIA_PRODUCTO"),
        diferencia_porcentual=diferencia,
        margen=margen_precio,
        link=row.get("LINK_RECOMENDADO"),
    )
    if row.get("APROBADO_POR_USUARIO") in ["Sí", "No"] and not row.get("FECHA_REVISION"):
        df_recalculado.at[idx, "FECHA_REVISION"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

st.session_state.df_resultados = df_recalculado

st.divider()
st.subheader("Resumen")
resumen = st.session_state.df_resultados["ESTADO_REVISION"].value_counts(dropna=False).reset_index()
resumen.columns = ["Estado", "Cantidad"]
st.dataframe(resumen, use_container_width=True, hide_index=True)

excel_bytes = generar_excel_bytes(st.session_state.df_resultados)
nombre_salida = f"resultado_links_productos_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

st.download_button(
    label="Descargar Excel final",
    data=excel_bytes,
    file_name=nombre_salida,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
