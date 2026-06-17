# Buscador IA de Links de Productos - MVP v3

Sistema interno en Streamlit para cargar un Excel de productos, buscar candidatos y exportar un Excel final con columnas nuevas.

## Cambios de v3

- Ya no se colocan páginas de búsqueda/listado como `LINK_RECOMENDADO`.
- Se filtran URLs de Alibaba para aceptar principalmente `/product-detail/`.
- Se filtran URLs de Made in China para evitar `products-search`, `hot-china-products`, `product-list`, etc.
- Si no hay una página directa confiable, `LINK_RECOMENDADO` queda vacío y se llena `URL_BUSQUEDA_REFERENCIA` solo como apoyo manual.
- Se agregan filtros básicos para evitar errores obvios, por ejemplo: zapatos deportivos vs tacones/formales, niños vs adultos, pantalones vs calzado.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

También puedes ejecutar `ejecutar_app.bat` en Windows.

## Flujo recomendado de prueba

1. Subir el Excel.
2. Seleccionar `Primeros 20 productos`.
3. Presionar `Buscar links automáticamente`.
4. Revisar principalmente `LINK_RECOMENDADO`.
5. Si el link recomendado está vacío, revisar `URL_BUSQUEDA_REFERENCIA` manualmente.
6. Aprobar solo productos realmente correctos.
7. Descargar el Excel final.

## Limitaciones actuales

- Esta versión usa búsqueda web por DDGS. No abre producto por producto para extraer datos internos.
- El precio puede quedar vacío si no aparece en el resultado de búsqueda.
- Todavía no calcula con total precisión los rangos de precio por cantidad cuando esa información solo aparece dentro de la página de Alibaba.
- Para una versión robusta se recomienda conectar una API/servicio de datos autorizado o un extractor estructurado de páginas de producto.
