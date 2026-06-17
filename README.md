# Buscador IA de Links de Productos - MVP v4

Aplicación interna en Streamlit para cargar un Excel de productos, buscar posibles links y exportar un Excel final con nuevas columnas.

## Cambios de la v4

- Mantiene el filtro de la v3 para evitar guardar páginas de búsqueda/listado como `LINK_RECOMENDADO`.
- Agrega control estricto de precio: si el precio detectado está fuera del margen configurado, el sistema **no** lo coloca como `LINK_RECOMENDADO`; lo deja como alternativa para revisión manual.
- El margen se controla desde el panel izquierdo, por defecto ±20%.
- Agrega estado `Revisar por precio` cuando hay producto similar pero precio lejano.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Uso recomendado

1. Subir el Excel original.
2. Seleccionar `Primeros 20 productos`.
3. Presionar `Buscar links automáticamente`.
4. Revisar especialmente:
   - `LINK_RECOMENDADO`
   - `PRECIO_ENCONTRADO`
   - `DIFERENCIA_PRECIO`
   - `ESTADO_REVISION`
   - `MOTIVO_SELECCION`
5. Aprobar solo productos correctos.
6. Descargar el Excel final.

## Nota

Esta versión usa resultados web como MVP. No evade CAPTCHA y no garantiza lectura completa de todos los rangos de precio de Alibaba. La siguiente mejora recomendada es conectar una fuente de datos estructurada/API o un extractor autorizado que permita leer precios por cantidad desde la ficha del producto.
