# Proveedor IA

MVP en Next.js + React para cargar una hoja de cálculo y buscar productos
similares en Alibaba y Made-in-China mediante la Responses API de OpenAI.

## Requisitos

- Node.js 20 o superior.
- Una cuenta de API de OpenAI con facturación o saldo activo.
- Un archivo `.xlsx` con estas columnas:
  - `DESCRIPTION NUEVA ESPAÑOL`
  - `DESCRIPTION NUEVA INGLES`
  - `TOTAL UNIT`
  - `PRICE`
  - `LINKS ORIGINAL`

## Configuración

### Instalación sencilla en Windows

Descomprime el proyecto y haz doble clic en `INSTALAR-Y-EJECUTAR.bat`. El
asistente solicita la API key de forma oculta, crea `.env.local`, instala las
dependencias e inicia el servidor.

### Configuración manual

1. Instala dependencias:

   ```powershell
   npm install
   ```

2. Copia `.env.example` como `.env.local` y añade la clave:

   ```text
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-5.4-mini
   ```

3. Inicia el proyecto:

   ```powershell
   npm run dev
   ```

4. Abre `http://localhost:3000`.

## Alcance del MVP

- La hoja se lee en el navegador y no se sube completa al servidor.
- Se busca una fila a la vez para controlar costos y revisar calidad.
- La clave permanece en el servidor.
- Los resultados se pueden exportar a un nuevo Excel.
- El puntaje es orientativo: precio, MOQ y especificaciones deben confirmarse
  con el proveedor antes de comprar.
