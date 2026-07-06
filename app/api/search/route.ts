import OpenAI from "openai";
import { NextResponse } from "next/server";
import { z } from "zod";

export const runtime = "nodejs";
export const maxDuration = 120;

const requestSchema = z.object({
  descriptionEs: z.string().max(4000),
  descriptionEn: z.string().max(4000),
  totalUnits: z.string().max(100),
  targetPrice: z.string().max(100),
  originalLink: z.string().max(2000),
});

const resultSchema = {
  type: "object",
  properties: {
    summary: { type: "string" },
    warnings: {
      type: "array",
      items: { type: "string" },
    },
    candidates: {
      type: "array",
      maxItems: 5,
      items: {
        type: "object",
        properties: {
          title: { type: "string" },
          url: { type: "string" },
          marketplace: {
            type: "string",
            enum: ["Alibaba", "Made-in-China"],
          },
          supplier: { type: "string" },
          listedPrice: { type: "string" },
          minimumOrder: { type: "string" },
          score: { type: "integer", minimum: 0, maximum: 100 },
          confidence: {
            type: "string",
            enum: ["alta", "media", "baja"],
          },
          matches: {
            type: "array",
            items: { type: "string" },
          },
          differences: {
            type: "array",
            items: { type: "string" },
          },
          rationale: { type: "string" },
        },
        required: [
          "title",
          "url",
          "marketplace",
          "supplier",
          "listedPrice",
          "minimumOrder",
          "score",
          "confidence",
          "matches",
          "differences",
          "rationale",
        ],
        additionalProperties: false,
      },
    },
  },
  required: ["summary", "warnings", "candidates"],
  additionalProperties: false,
} as const;

function isAllowedCandidate(candidate: { url?: string }) {
  try {
    const hostname = new URL(candidate.url ?? "").hostname.toLowerCase();
    return (
      hostname === "alibaba.com" ||
      hostname.endsWith(".alibaba.com") ||
      hostname === "made-in-china.com" ||
      hostname.endsWith(".made-in-china.com")
    );
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(
      { error: "Falta configurar OPENAI_API_KEY en .env.local." },
      { status: 503 },
    );
  }

  const parsed = requestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Los datos del producto no son válidos." },
      { status: 400 },
    );
  }

  const product = parsed.data;
  if (!product.descriptionEs && !product.descriptionEn && !product.originalLink) {
    return NextResponse.json(
      { error: "La fila no contiene información suficiente para buscar." },
      { status: 400 },
    );
  }

  try {
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const response = await client.responses.create({
      model: process.env.OPENAI_MODEL || "gpt-5.4-mini",
      store: false,
      reasoning: { effort: "low" },
      tools: [
        {
          type: "web_search",
          search_context_size: "low",
          filters: {
            allowed_domains: ["alibaba.com", "made-in-china.com"],
          },
        },
      ],
      tool_choice: "auto",
      text: {
        format: {
          type: "json_schema",
          name: "supplier_product_candidates",
          strict: true,
          schema: resultSchema,
        },
      },
      input: [
        {
          role: "system",
          content:
            "Eres analista de compras internacionales. Busca productos reales y actualmente visibles solo en Alibaba y Made-in-China. Compara identidad, función, material, dimensiones, especificaciones, cantidad mínima y precio. No inventes datos: usa 'No visible' cuando la página no los muestre. El precio objetivo puede no indicar moneda o si es unitario; señálalo como advertencia. Devuelve como máximo cinco candidatos, ordenados por similitud técnica. Una URL debe apuntar a una ficha concreta del producto, no a una búsqueda, categoría o página principal. Asigna confianza baja si faltan especificaciones decisivas. El puntaje es una ayuda, no una afirmación de equivalencia.",
        },
        {
          role: "user",
          content: `Producto de referencia:
- Descripción en español: ${product.descriptionEs || "No disponible"}
- Descripción en inglés: ${product.descriptionEn || "No disponible"}
- Unidades solicitadas: ${product.totalUnits || "No disponible"}
- Precio objetivo: ${product.targetPrice || "No disponible"}
- Enlace original para identificar el producto: ${product.originalLink || "No disponible"}

Busca alternativas lo más parecidas posible y explica coincidencias y diferencias verificables.`,
        },
      ],
    });

    const result = JSON.parse(response.output_text);
    result.candidates = Array.isArray(result.candidates)
      ? result.candidates.filter(isAllowedCandidate)
      : [];

    return NextResponse.json(result);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Error desconocido de búsqueda.";
    console.error("OpenAI product search failed:", message);
    return NextResponse.json(
      { error: "No se pudo completar la búsqueda. Revisa la clave, saldo y conexión." },
      { status: 502 },
    );
  }
}
