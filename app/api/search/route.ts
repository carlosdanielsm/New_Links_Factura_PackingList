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

type CandidateResult = {
  title: string;
  url: string;
  marketplace: "Alibaba" | "Made-in-China";
  supplier: string;
  listedPrice: string;
  minimumOrder: string;
  score: number;
  confidence: "alta" | "media" | "baja";
  matches: string[];
  differences: string[];
  rationale: string;
};

type SupplierSearchResult = {
  summary: string;
  warnings: string[];
  candidates: CandidateResult[];
};

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

function normalizeNumberToken(value: string) {
  const token = value.replace(/[^\d.,]/g, "");
  const lastDot = token.lastIndexOf(".");
  const lastComma = token.lastIndexOf(",");

  if (lastDot >= 0 && lastComma >= 0) {
    const decimalSeparator = lastDot > lastComma ? "." : ",";
    const thousandsSeparator = decimalSeparator === "." ? "," : ".";
    return Number(token.replaceAll(thousandsSeparator, "").replace(decimalSeparator, "."));
  }

  if (lastComma >= 0) {
    const decimals = token.length - lastComma - 1;
    return Number(token.replaceAll(".", "").replace(",", decimals <= 2 ? "." : ""));
  }

  return Number(token.replaceAll(",", ""));
}

function extractNumbers(value: string) {
  return Array.from(value.matchAll(/\d+(?:[.,]\d+)*/g))
    .map((match) => normalizeNumberToken(match[0]))
    .filter((number) => Number.isFinite(number) && number > 0 && number < 100000);
}

function pickClosestPrice(listedPrice: string, targetPrice: number) {
  const prices = extractNumbers(listedPrice);
  if (!prices.length) return undefined;

  return prices.reduce((closest, price) =>
    Math.abs(price - targetPrice) < Math.abs(closest - targetPrice) ? price : closest,
  );
}

function priceScoreFromRatio(ratio: number) {
  if (ratio <= 0.1) return 100;
  if (ratio <= 0.25) return 90;
  if (ratio <= 0.5) return 70;
  if (ratio <= 1) return 45;
  if (ratio <= 2) return 20;
  return 5;
}

function rerankByTargetPrice(
  candidates: CandidateResult[],
  targetPriceText: string,
) {
  const targetPrice = extractNumbers(targetPriceText)[0];
  if (!targetPrice) return candidates;

  return candidates
    .map((candidate) => {
      const candidatePrice = pickClosestPrice(candidate.listedPrice, targetPrice);

      if (!candidatePrice) {
        const score = Math.min(75, Math.round(candidate.score * 0.75));
        return {
          ...candidate,
          score,
          confidence: candidate.confidence === "alta" ? "media" : candidate.confidence,
          differences: [
            ...candidate.differences,
            "No se pudo comparar el precio porque el precio publicado no es visible o no es numérico.",
          ],
          rationale: `${candidate.rationale} Precio objetivo: ${targetPriceText}. Precio publicado no comparable, por eso se limita el puntaje.`,
        };
      }

      const differenceRatio = Math.abs(candidatePrice - targetPrice) / targetPrice;
      const direction = candidatePrice > targetPrice ? "por encima" : "por debajo";
      const differencePercent = Math.round(differenceRatio * 100);
      const priceScore = priceScoreFromRatio(differenceRatio);
      let score = Math.round(candidate.score * 0.55 + priceScore * 0.45);

      if (differenceRatio > 1.5) score = Math.min(score, 45);
      else if (differenceRatio > 0.75) score = Math.min(score, 62);
      else if (differenceRatio > 0.35) score = Math.min(score, 78);

      const priceNote =
        `Precio comparable aprox. ${candidatePrice}; está ${differencePercent}% ${direction} del objetivo ${targetPrice}.`;

      return {
        ...candidate,
        score,
        differences:
          differenceRatio > 0.35
            ? [...candidate.differences, priceNote]
            : candidate.differences,
        matches:
          differenceRatio <= 0.25
            ? [...candidate.matches, priceNote]
            : candidate.matches,
        rationale: `${candidate.rationale} ${priceNote}`,
      };
    })
    .sort((a, b) => b.score - a.score);
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
            "Eres analista de compras internacionales. Busca productos reales y actualmente visibles solo en Alibaba y Made-in-China. Compara identidad, función, material, dimensiones, especificaciones, cantidad mínima y precio. No inventes datos: usa 'No visible' cuando la página no los muestre. El precio objetivo es un criterio principal: prioriza candidatos con precio unitario visible lo más cercano posible al objetivo, idealmente dentro de ±25%. Si un candidato supera el objetivo por más de 35%, no debe quedar arriba salvo que no existan opciones mejores. Si supera el objetivo por más del 100%, inclúyelo sólo como alternativa débil y explica la diferencia. El precio objetivo puede no indicar moneda o si es unitario; señálalo como advertencia. Devuelve como máximo cinco candidatos, ordenados por similitud técnica y cercanía de precio. Una URL debe apuntar a una ficha concreta del producto, no a una búsqueda, categoría o página principal. Asigna confianza baja si faltan especificaciones decisivas o si el precio no es comparable. El puntaje es una ayuda, no una afirmación de equivalencia.",
        },
        {
          role: "user",
          content: `Producto de referencia:
- Descripción en español: ${product.descriptionEs || "No disponible"}
- Descripción en inglés: ${product.descriptionEn || "No disponible"}
- Unidades solicitadas: ${product.totalUnits || "No disponible"}
- Precio objetivo: ${product.targetPrice || "No disponible"}
- Enlace original para identificar el producto: ${product.originalLink || "No disponible"}

Busca alternativas lo más parecidas posible, pero descarta o baja de prioridad las opciones con precio muy lejano al objetivo. Explica coincidencias y diferencias verificables.`,
        },
      ],
    });

    const result = JSON.parse(response.output_text) as SupplierSearchResult;
    result.candidates = Array.isArray(result.candidates)
      ? rerankByTargetPrice(
          result.candidates.filter(isAllowedCandidate),
          product.targetPrice,
        )
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
