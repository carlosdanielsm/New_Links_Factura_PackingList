# Buscador IA de Links de Productos - MVP interno v2

Esta versión permite probar el flujo completo con búsqueda básica de candidatos.

## Qué hace

- Permite subir un Excel `.xlsx`.
- Valida columnas obligatorias:
  - `DESCRIPTION NUEVA ESPAÑOL`
  - `DESCRIPTION NUEVA INGLES`
  - `TOTAL UNIT`
  - `PRICE`
  - `LINKS ORIGINAL`
- Permite procesar primeros 20 productos o todos.
- Busca candidatos web para Alibaba como fuente principal.
- Usa Made in China como respaldo opcional.
- Llena columnas nuevas:
  - `LINK_RECOMENDADO`
  - `PLATAFORMA_RESULTADO`
  - `PRECIO_ENCONTRADO`
  - `DIFERENCIA_PRECIO`
  - `COINCIDENCIA_PRODUCTO`
  - `MOTIVO_SELECCION`
  - `LINK_ALTERNATIVO_1`
  - `LINK_ALTERNATIVO_2`
  - `ESTADO_REVISION`
  - `APROBADO_POR_USUARIO`
  - `FECHA_REVISION`
- Permite editar resultados manualmente.
- Permite aprobar uno por uno o aprobar todos los de alta coincidencia.
- Exporta un Excel final.

## Importante

Esta versión no evade CAPTCHA ni hace scraping agresivo de Alibaba.

La búsqueda usa resultados web. Por eso:

- Puede encontrar links útiles sin abrir manualmente cada producto.
- Puede no detectar todos los precios.
- Si no detecta precio, deja el registro para revisión.
- Sirve para validar la lógica con 20 productos antes de escalar a 600.

Para una versión productiva más robusta, conviene reemplazar `buscador_links.py` por una API o proveedor autorizado de datos.

## Instalación en Windows

1. Instalar Python 3.11 o superior.
2. Abrir CMD o PowerShell dentro de esta carpeta.
3. Ejecutar:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

También puedes ejecutar:

```bash
ejecutar_app.bat
```

## Flujo recomendado de prueba

1. Subir el Excel.
2. Seleccionar `Primeros 20 productos`.
3. Presionar `Buscar links automáticamente`.
4. Revisar los links recomendados.
5. Aprobar manualmente o usar `Aprobar todos los de alta coincidencia`.
6. Descargar el Excel final.

## Qué revisar en la prueba de 20 productos

- Si el link recomendado corresponde al mismo producto.
- Si la plataforma es correcta.
- Si el precio se detectó o quedó vacío.
- Si el estado asignado tiene sentido.
- Cuántos productos quedan en alta, media, baja o pendiente.

