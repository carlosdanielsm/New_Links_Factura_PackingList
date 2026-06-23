# Buscador IA de Links de Productos - MVP V6

Versión interna de prueba para buscar links de productos tomando como base un Excel.

## Qué cambia en V6

Esta versión vuelve a la lógica práctica de la V4, pero agrega una mejora:

- Intenta leer el título del `LINKS ORIGINAL`.
- Usa ese título como referencia principal para buscar productos similares.
- Usa `DESCRIPTION NUEVA INGLES` como apoyo y como respaldo si no se puede leer el título original.
- Mantiene los filtros de V4:
  - evita páginas de búsqueda/listado;
  - acepta páginas directas de producto;
  - valida precio contra el margen configurado;
  - si el precio está fuera del margen, deja el link como alternativa y no como recomendado.

Para no cargar tanto la tabla, solo agrega una columna extra de diagnóstico:

- `TITULO_LINK_ORIGINAL`

Esta columna sirve para verificar qué producto entendió el sistema desde el link original.

## Uso

1. Descomprimir el ZIP.
2. Abrir PowerShell o CMD dentro de la carpeta.
3. Ejecutar:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Si no existe el entorno virtual:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Prueba recomendada

1. Subir el Excel.
2. Procesar primeros 20 productos.
3. Mantener activo `Usar título del link original como referencia`.
4. Revisar:
   - `TITULO_LINK_ORIGINAL`
   - `LINK_RECOMENDADO`
   - `LINK_ALTERNATIVO_1`
   - `LINK_ALTERNATIVO_2`
   - `MOTIVO_SELECCION`
5. Confirmar si el recomendado se parece al producto real del link original.

## Nota

Esta versión no evade CAPTCHA ni hace scraping agresivo. Usa búsqueda web y lectura básica de metadatos del link original.
